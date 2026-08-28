"""Kütüphane — Hafıza ekranının okuduğu iki disk deposu.

Bu modülün var olma sebebi ölçülmüş bir boşluk: `Store()` varsayılanı
`:memory:` (`gozcu/store.py:62`) ve koşu bitince epizot/risk/aksiyon
kayıtlarının hepsi süreçle birlikte gidiyor. `_SESSION` de tek — geçmiş bir
koşuya `_run_or_404` üzerinden erişmek mümkün değil. Yani "daha önce analiz
edilenler" diye bir liste, diske YAZILMADIĞI sürece üretilemez.

Testler `library_dir`'i `tmp_path`'e yamalıyor; `_output_dir_for` ile aynı
gerekçe (`gozcu/ui/server.py:727`) — ad kasıtlı ayrı bir fonksiyon.
"""

import json

import pytest

from gozcu.memory import library


@pytest.fixture(autouse=True)
def _tmp_library(monkeypatch, tmp_path):
    """Her test kendi kütüphanesinde koşar — gerçek `var/library` kirlenmez."""
    monkeypatch.setattr(library, "library_dir", lambda: tmp_path / "library")


# =============================================================================
# Belgeler — operatörün dışarıdan yüklediği referans dosyaları
# =============================================================================

def test_saved_document_is_listed_with_its_real_size():
    data = "raf yükleme talimatı".encode("utf-8")
    saved = library.save_document("talimat.md", data)

    listed = library.list_documents()
    assert [d.id for d in listed] == [saved.id]
    # Boyut diskten okunuyor, çağıranın iddiasından değil.
    assert listed[0].size == len(data)
    assert listed[0].name == "talimat.md"


def test_document_content_survives_the_round_trip():
    data = "yangın tüpü altı ayda bir".encode("utf-8")
    saved = library.save_document("protokol.txt", data)

    assert library.read_document(saved.id) == data


def test_deleting_a_document_removes_it_from_disk_and_from_the_list():
    saved = library.save_document("gecici.txt", b"x")

    assert library.delete_document(saved.id) is True
    assert library.list_documents() == []
    # İkinci silme YALAN SÖYLEMİYOR: yok olan bir belge için `False`.
    assert library.delete_document(saved.id) is False


def test_unknown_document_id_reads_as_none():
    assert library.read_document("boyle-bir-kimlik-yok") is None


def test_the_uploaded_name_cannot_escape_the_library():
    """`../../PWNED.txt` kütüphane dizininin DIŞINA yazamamalı.

    `server._safe_upload_name` ile aynı arıza: `multipart` `filename`'i
    istemcinin yazdığı ham metin ve bir kez koşu dizininden çıktı (ölçüldü).
    Burada ayrıca `id`'nin kendisi bir yol bileşeni — kimliği uydurulmuş bir
    istek `read_document("../../../etc/passwd")` diyebilir.
    """
    saved = library.save_document("../../PWNED.txt", b"zarar")

    stored = library.documents_dir().resolve()
    assert stored in library.document_path(saved.id).resolve().parents
    assert library.list_documents()[0].name == "PWNED.txt"


def test_a_forged_document_id_cannot_read_outside_the_library():
    assert library.read_document("../../../secrets") is None
    assert library.delete_document("../../../secrets") is False


def test_document_context_lists_only_embedded_documents_in_order():
    """§3e: prompt parçası yalnız `embedded=True` belgeleri, numaralı, isim
    isim listeler — `list_documents()`'ın sırasıyla (en yeni önce)."""
    older = library.save_document("vardiya.xlsx", b"x")
    newer = library.save_document("yangin-talimati.md", b"y")
    library.mark_embedded(older.id, True)
    library.mark_embedded(newer.id, True)

    context = library.document_context()

    lines = context.splitlines()
    assert lines[0] == "YÜKLÜ BELGELER (search_documents aracıyla erişilebilir):"
    assert lines[1:] == ['1. "yangin-talimati.md"', '2. "vardiya.xlsx"']


def test_document_context_is_empty_when_nothing_is_embedded():
    """Belge hiç yoksa ya da hiçbiri gömülmemişse boş dize — arıza değil."""
    assert library.document_context() == ""

    library.save_document("henuz-gomulmemis.txt", b"z")
    assert library.document_context() == ""


# =============================================================================
# Raporlar — koşu bitince yazılan `PipelineOutput`
# =============================================================================

_PAYLOAD = {"summary": "Raf çöktü.", "events": [], "risk": "Kritik",
            "actions": ["Hattı durdur."]}


def test_saved_report_keeps_the_four_contract_keys():
    saved = library.save_report("run-1", _PAYLOAD, source_name="raf.mp4")

    read = library.read_report(saved.id)
    # Şartnamenin dört anahtarı ZARARSIZ geçmeli — kütüphane bir sarmalayıcı,
    # çıktı sözleşmesinin ikinci bir yazımı değil.
    assert read["payload"] == _PAYLOAD


def test_report_listing_carries_the_headline_fields_without_the_body():
    """Liste satırı gövdeyi TAŞIMIYOR: on koşuluk bir kütüphanede her satırın
    tam `detail` ağacını tele koymak ekranı gereksiz megabaytlarla açardı."""
    library.save_report("run-1", _PAYLOAD, source_name="raf.mp4")

    row = library.list_reports()[0]
    assert row.run_id == "run-1"
    assert row.source_name == "raf.mp4"
    assert row.risk == "Kritik"
    assert not hasattr(row, "payload")


def test_reports_come_back_newest_first():
    library.save_report("eski", _PAYLOAD)
    library.save_report("yeni", _PAYLOAD)

    assert [r.run_id for r in library.list_reports()] == ["yeni", "eski"]


def test_a_corrupt_report_file_does_not_take_down_the_listing():
    """Bozuk tek dosya bütün ekranı düşürmemeli — `memory._episode`'un
    "bozuk tek nokta aramayı düşürmemeli" kuralının aynısı."""
    library.save_report("saglam", _PAYLOAD)
    (library.reports_dir() / "bozuk.json").write_text("{ bu json değil",
                                                      encoding="utf-8")

    assert [r.run_id for r in library.list_reports()] == ["saglam"]


def test_deleting_a_report_removes_it_from_disk_and_from_the_list():
    saved = library.save_report("run-1", _PAYLOAD)

    assert library.delete_report(saved.id) is True
    assert library.list_reports() == []
    assert library.read_report(saved.id) is None
    # İkinci silme YALAN SÖYLEMİYOR — belgedeki kuralın aynısı.
    assert library.delete_report(saved.id) is False


def test_a_forged_report_id_cannot_delete_outside_the_library():
    """Kimlik bir YOL BİLEŞENİ ve URL'den geliyor.

    `read_report` zaten `_valid_id`'den geçiyordu; silme yolu onsuz
    bırakılsaydı `DELETE /api/library/reports/../../../bir-sey` kütüphanenin
    dışındaki bir dosyayı silebilirdi — okumaktan çok daha kötü bir sonuç.
    """
    outside = library.library_dir().parent / "dokunulmamali.json"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("{}", encoding="utf-8")

    assert library.delete_report("../dokunulmamali") is False
    assert library.delete_report("../../../secrets") is False
    assert outside.exists()


def test_report_written_without_a_run_is_still_readable_as_json():
    saved = library.save_report("run-1", _PAYLOAD)
    raw = json.loads(
        (library.reports_dir() / f"{saved.id}.json").read_text(encoding="utf-8"))
    assert raw["run_id"] == "run-1"
