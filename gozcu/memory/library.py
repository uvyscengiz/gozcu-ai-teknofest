"""Kütüphane — Hafıza ekranının iki disk deposu.

Burada iki ayrı soru var ve ikisi ayrı dizinde duruyor:

1. **`documents/`** — operatörün DIŞARIDAN yüklediği referans belgeleri.
   Talimat, prosedür, vardiya notu. Sisteme insan koyuyor.
2. **`reports/`** — koşu bitince yazılan `PipelineOutput`. Sisteme sistem
   koyuyor.

**Neden diske ve neden yeni bir modül.** `Store()` varsayılanı `:memory:`
(`gozcu/store.py:62`): koşu biter bitmez epizot, risk, aksiyon ve devir
kayıtlarının hepsi süreçle birlikte gidiyor. `gozcu/ui/server.py` de tek bir
`_SESSION` tutuyor ve `_run_or_404` aktif koşu dışındaki her kimliği
reddediyor. Yani "daha önce analiz edilenler" diye bir liste, koşu bitişinde
diske YAZILMADIĞI sürece hiçbir yerden üretilemezdi — ekran her açılışta boş
kalırdı ve boşluğun sebebi görünmezdi.

**Qdrant'ın yerine geçmiyor.** Epizodik hafıza (`gozcu/memory.py`) ajanın
emsal aradığı vektör indeksi; burası operatörün gözüyle baktığı dosya
dolabı. İkisi ayrı sorulara cevap veriyor ve biri diğerinden türetilemez.

**Dizin ortamdan geliyor** (`GOZCU_LIBRARY_DIR`), varsayılanı depo kökünde
`var/library`. `library_dir` kasıtlı ayrı bir fonksiyon: testler onu kendi
`tmp_path`'lerine yamalıyor — `server._output_dir_for` ile aynı gerekçe.
"""

import json
import time
import uuid
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from gozcu.core.config import LIBRARY_DIR

#: Kimlik olarak kabul edilen biçim. Kimlik bir YOL BİLEŞENİ olarak
#: kullanılıyor (`documents/{id}/`, `reports/{id}.json`), yani uydurulmuş bir
#: kimlik dizinin dışını okuyabilir. `server._safe_upload_name` yüklenen
#: dosya adı için aynı arızayı kapatıyor; burada ayrıca kimliğin kendisi
#: güvenilmez, çünkü URL'den geliyor.
_ID_CHARS = set("0123456789abcdef")

#: `_now`'ın son verdiği damga — bkz. oradaki gerekçe.
_last_stamp = 0.0


def _now() -> float:
    """Sıralanabilir bir zaman damgası — aynı değeri İKİ KEZ vermez.

    Liste "en yeni önce" sıralanıyor ve damga tek anahtar. Windows'ta
    `time.time()` çözünürlüğü ~15,6 ms: arka arkaya iki yükleme aynı damgayı
    alıyor ve sıralama o iki satır için rastgeleye düşüyor. Ölçülmemiş bir
    sıra değil, YANLIŞ bir sıra üretir — kullanıcı en son yüklediği belgeyi
    ikinci sırada görür.

    Süreç yeniden başlayınca sayaç sıfırlanıyor ve damga yine duvar saatine
    oturuyor: garanti süreç İÇİ, dosyalar arası sıralama gerçek zamandan
    geliyor.
    """
    global _last_stamp
    _last_stamp = max(time.time(), _last_stamp + 1e-6)
    return _last_stamp


class Document(BaseModel):
    """Yüklenmiş bir referans belgesinin defter satırı."""

    model_config = ConfigDict(extra="forbid")

    id: str
    #: Yüklenirken kullanılan dosya adı — yol bileşenleri atılmış hâliyle.
    name: str
    #: Diskteki gerçek boyut. Çağıranın iddiası değil, `stat()` sonucu.
    size: int
    uploaded_at: float
    #: Belge epizodik hafızaya gömülebildi mi. `False` bir arıza DEĞİL,
    #: ölçülmüş bir durum: gömme kademesi bozukken belge yine saklanıyor ve
    #: liste bunu damgalıyor — "gömüldü" diye göstermek, ajan onu emsal
    #: olarak hiç bulamazken bulacağını sanmak olurdu.
    embedded: bool = False


class Report(BaseModel):
    """Bir koşu raporunun defter satırı — GÖVDESİZ.

    Liste satırı `payload`'ı taşımıyor: on koşuluk bir kütüphanede her satırın
    tam `detail` ağacını tele koymak ekranı gereksiz megabaytlarla açardı.
    Gövde `read_report` ile ayrıca isteniyor.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    run_id: str
    created_at: float
    #: Analiz edilen videonun adı; bilinmiyorsa `None` — uydurulmuş bir ad
    #: yerine boş bir hücre.
    source_name: str | None = None
    #: Çıktı sözleşmesinin `risk`'i, liste satırında rozet olarak gösteriliyor.
    risk: str | None = None
    #: `summary`'nin ta kendisi (kırpılmadan) — ekran kendi kırpıyor.
    summary: str | None = None


def library_dir() -> Path:
    """Kütüphanenin kökü. **Testler bunu yamalıyor** — bkz. modül başlığı."""
    return LIBRARY_DIR


def documents_dir() -> Path:
    path = library_dir() / "documents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def reports_dir() -> Path:
    path = library_dir() / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_name(raw: str | None) -> str:
    """Yüklenen dosyanın adını tek bir yol bileşenine indirger.

    `server._safe_upload_name`'in ikizi değil, kardeşi: orası koşu dizinine
    hapsediyor ve boş adı `video.mp4`'e düşürüyor; burada varsayılan bir
    belge adı gerekiyor. Ortak kural aynı — `Path(...).name` yol
    bileşenlerini atıyor, `".."` ve gömülü `NUL` ayrıca eleniyor.
    """
    name = Path((raw or "").replace("\x00", "")).name
    return "belge" if name in ("", ".", "..") else name


def _valid_id(raw: str | None) -> str | None:
    """Kimliği doğrular; uydurulmuşsa `None`.

    Kimlik bir yol bileşeni olarak kullanılıyor. `"../../../etc/passwd"`
    doğrulanmadan geçseydi `read_document` kütüphanenin dışını okurdu.
    Beyaz liste kullanılıyor, kara liste değil: `..` elemek yetmez, mutlak
    yol ve sürücü harfi (`C:\\`) de girer.
    """
    text = str(raw or "")
    if not text or len(text) != 32 or not set(text) <= _ID_CHARS:
        return None
    return text


# =============================================================================
# Belgeler
# =============================================================================

def document_path(doc_id: str) -> Path:
    """Belgenin dizini — var olduğu iddiası YOK, yalnız yolu verir."""
    return documents_dir() / str(doc_id)


def _meta_path(doc_id: str) -> Path:
    return document_path(doc_id) / "meta.json"


def content_path(doc_id: str) -> Path:
    """Belgenin ham içeriğini taşıyan dosya — **kamusal sözleşme.**

    `embed_document` bir dosya YOLU istiyor (MarkItDown bayt değil yol
    alıyor), yani yükleme ucu bu bilgiyi kütüphaneden almak zorunda.
    Alt çizgili ad dosya içi çağıranlar için duruyor; dışarıdan uzanılan
    özel bir ayrıntı olmasın diye asıl ad bu.
    """
    return document_path(doc_id) / "content"


#: Dosya içi çağıranların kullandığı eski ad — aynı fonksiyon.
_content_path = content_path


def save_document(filename: str | None, data: bytes) -> Document:
    """Belgeyi kütüphaneye yazar ve defter satırını döner.

    Dosya, adının yanında DEĞİL kendi dizininde duruyor: iki operatör aynı
    `talimat.md` adını yüklediğinde ikincisi birincisini ezerdi. İçerik
    `content` adıyla saklanıp gerçek ad `meta.json`'a yazılıyor — böylece
    dosya adı bir daha hiçbir yol hesabına girmiyor.
    """
    doc_id = uuid.uuid4().hex
    folder = document_path(doc_id)
    folder.mkdir(parents=True, exist_ok=True)
    _content_path(doc_id).write_bytes(data)

    record = Document(id=doc_id, name=_safe_name(filename),
                      # Boyut diskten okunuyor: `len(data)` ile ölçülen aynı
                      # sayı olsa da, listeleme her zaman `stat()` diyor ve
                      # iki yolun tek kaynağı olması gerekiyor.
                      size=_content_path(doc_id).stat().st_size,
                      uploaded_at=_now())
    _write_meta(record)
    return record


def _write_meta(record: Document) -> None:
    _meta_path(record.id).write_text(
        record.model_dump_json(), encoding="utf-8")


def list_documents() -> list[Document]:
    """Yüklenmiş belgeler, en YENİSİ önce.

    Okunamayan tek bir `meta.json` bütün listeyi düşürmüyor — atlanıyor.
    `memory._episode`'un "bozuk tek nokta aramayı düşürmemeli" kuralı.
    """
    records = []
    for folder in documents_dir().iterdir():
        if not folder.is_dir():
            continue
        record = _read_meta(folder.name)
        if record is not None:
            records.append(record)
    return sorted(records, key=lambda r: r.uploaded_at, reverse=True)


def document_context() -> str:
    """Gömülü belge listesini prompt parçası olarak döndürür (§3e).

    Yalnız `embedded: True` olan belgeler listelenir. Belge yoksa boş dize.
    """
    docs = [d for d in list_documents() if d.embedded]
    if not docs:
        return ""
    lines = ["YÜKLÜ BELGELER (search_documents aracıyla erişilebilir):"]
    for i, doc in enumerate(docs, 1):
        lines.append(f'{i}. "{doc.name}"')
    return "\n".join(lines)


def _read_meta(doc_id: str) -> Document | None:
    checked = _valid_id(doc_id)
    if checked is None:
        return None
    try:
        raw = json.loads(_meta_path(checked).read_text(encoding="utf-8"))
        record = Document(**raw)
    except Exception:  # noqa: BLE001 — bozuk tek satır listeyi düşürmez
        return None
    # Boyut her okumada diskten TAZELENİYOR: `meta.json`'daki sayı yazıldığı
    # andaki gerçekti, dosya sonradan değiştiyse defter yalan söylerdi.
    try:
        record.size = _content_path(checked).stat().st_size
    except OSError:
        return None
    return record


def read_document(doc_id: str) -> bytes | None:
    """Belgenin içeriği; kimlik uydurulmuşsa ya da belge yoksa `None`."""
    checked = _valid_id(doc_id)
    if checked is None:
        return None
    try:
        return _content_path(checked).read_bytes()
    except OSError:
        return None


def delete_document(doc_id: str) -> bool:
    """Belgeyi siler. Zaten yoksa `False` — silme YALAN SÖYLEMİYOR."""
    checked = _valid_id(doc_id)
    if checked is None:
        return False
    folder = document_path(checked)
    if not folder.is_dir():
        return False
    for child in folder.iterdir():
        child.unlink(missing_ok=True)
    folder.rmdir()
    return True


def mark_embedded(doc_id: str, embedded: bool) -> Document | None:
    """Gömme sonucunu deftere işler.

    Gömme yüklemeden AYRI bir adım ve ayrı başarısızlık: belge diske yazıldı
    ama vektör yazılamadıysa satır kalmalı, yalnız damgası düşmeli.
    """
    record = _read_meta(doc_id)
    if record is None:
        return None
    record.embedded = embedded
    _write_meta(record)
    return record


# =============================================================================
# Raporlar
# =============================================================================

def save_report(run_id: str, payload: dict,
                source_name: str | None = None) -> Report:
    """Koşu raporunu diske yazar ve defter satırını döner.

    `payload` şartnamenin dört anahtarını taşıyan `PipelineOutput` sözlüğü ve
    buradan **değiştirilmeden** geçiyor: kütüphane bir sarmalayıcı, çıktı
    sözleşmesinin ikinci bir yazımı değil. Manşet alanları (`risk`,
    `summary`) satıra KOPYALANIYOR ki liste on dosyanın tamamını açmak
    zorunda kalmasın.
    """
    report_id = uuid.uuid4().hex
    record = Report(id=report_id, run_id=str(run_id), created_at=_now(),
                    source_name=source_name,
                    risk=payload.get("risk"), summary=payload.get("summary"))
    body = {**record.model_dump(), "payload": payload}
    (reports_dir() / f"{report_id}.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def _read_report_file(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — bozuk tek dosya listeyi düşürmez
        return None


def list_reports() -> list[Report]:
    """Yazılmış raporlar, en YENİSİ önce — gövdeleri olmadan."""
    records = []
    for path in reports_dir().glob("*.json"):
        body = _read_report_file(path)
        if body is None:
            continue
        try:
            records.append(Report(**{k: v for k, v in body.items()
                                     if k in Report.model_fields}))
        except Exception:  # noqa: BLE001 — eksik alanlı eski dosya atlanır
            continue
    return sorted(records, key=lambda r: r.created_at, reverse=True)


def read_report(report_id: str) -> dict | None:
    """Raporun tam gövdesi (`payload` dâhil); yoksa `None`."""
    path = _report_path(report_id)
    return _read_report_file(path) if path is not None and path.is_file() else None


def _report_path(report_id: str) -> Path | None:
    """Raporun dosya yolu; kimlik uydurulmuşsa `None`.

    Okuma ve silme AYNI doğrulamadan geçsin diye ayrı bir fonksiyon: silme
    yolu `_valid_id`'siz bırakılsaydı `DELETE .../reports/../../../bir-sey`
    kütüphanenin dışındaki bir dosyayı silebilirdi — okumaktan çok daha kötü
    bir sonuç ve iki yolun ayrışması bunun tipik yolu.
    """
    checked = _valid_id(report_id)
    return None if checked is None else reports_dir() / f"{checked}.json"


def delete_report(report_id: str) -> bool:
    """Raporu siler. Zaten yoksa `False` — belgedeki kuralın aynısı.

    **Geri dönüşü yok ve bu bilerek basit tutuldu:** bir "çöp kutusu"
    katmanı, kütüphaneyi silinmiş sanılan dosyalarla doldururdu. Onay
    ekranda alınıyor (`js/memory.js`, iki adımlı tuş), burada değil — sunucu
    tarafı bir teyit sorusu HTTP'de yalnızca ikinci bir uç demek olurdu.
    """
    path = _report_path(report_id)
    if path is None or not path.is_file():
        return False
    path.unlink()
    return True
