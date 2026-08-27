"""Testlerin ortak yardımcıları."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_library(monkeypatch, tmp_path):
    """Hiçbir test GERÇEK kütüphaneye yazmasın — **autouse, yani kaçış yok.**

    Ölçülmüş arıza: `gozcu/library.py` eklendiği gün tam takım bir kez
    koşturuldu ve depo kökündeki `var/library/reports/` dizinine **14 rapor**
    düştü. Kaynağı `tests/test_server.py`'nin gerçek koşuları: `_work`
    bitişte `_archive_report`'u çağırıyor ve o dosya kütüphaneyi
    yamalamıyordu. Düşen kayıtlardan biri `PWNED.txt` adını taşıyordu (yol
    kaçışı testinin yüklediği dosya) — yani Hafıza ekranı, hiç yapılmamış
    analizleri "geçmiş rapor" diye listeliyordu.

    Yama tek tek test dosyalarına bırakılamaz: kütüphaneye yazan yol
    `_work`'ün İÇİNDE ve onu dolaylı olarak tetikleyen her yeni test aynı
    sızıntıyı geri getirir. `autouse` bu yüzden burada, çağrı yerinde değil.
    """
    from gozcu import library

    monkeypatch.setattr(library, "library_dir", lambda: tmp_path / "library")


@pytest.fixture
def gated(monkeypatch):
    """Onay kapısını AÇAR — `halt_production_line` yeniden kapılanır.

    Kapı 26 Ağustos'ta varsayılan olarak boşaltıldı (araçlar mock; olmayan
    bir eylemi kapılamak ajanı araç çağırmaktan alıkoyuyordu). Makine
    silinmedi ve gerçek saha sistemlerine bağlanan bir kurulumda geri
    gelmeli — bu fixture onu sınayan testleri ayakta tutuyor.

    İki modülde birden yamalanıyor: `supervisor` adı içeri **import ederek**
    bağlıyor, yani yalnız `registry`'yi yamalamak onu etkilemez.
    """
    from gozcu.agents import supervisor
    from gozcu.tools import registry

    gate = frozenset({"halt_production_line"})
    monkeypatch.setattr(registry, "NEEDS_APPROVAL", gate)
    monkeypatch.setattr(supervisor, "NEEDS_APPROVAL", gate)
    return gate
