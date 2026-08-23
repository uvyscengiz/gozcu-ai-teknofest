# Görev 02 — Olay deposu (`gozcu/store.py`)

**Sahip:** `uvyscengiz` · **Gün:** 23 Ağustos · **Süre:** ~2 saat
**Bağımlılık:** [01](01-sozlesme.md)

## Bağlam

Sistemdeki bütün ajanlar birbirine bu depo üzerinden konuşuyor. Ajan sınırlarını
hiçbir şey serbest metin olarak geçmiyor — her devir buraya yazılan tipli bir
kayıt. Bunun üç getirisi var: şartnamenin istediği *bağlam yönetimi* ve *çok
adımlı karar zincirleri* için somut kanıt, her sınırda bir test noktası, ve
**açıklanabilirlik** — `devir` tablosu arayüzde çizilince "sistem neden böyle
karar verdi" sorusunun cevabı ekranda görünür oluyor.

SQLite, tek dosya, kurulum yok. Testlerde `Store(":memory:")`.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/test_models.py -v     # Görev 01 yeşil olmalı
```

## Bağımlı olduğun imzalar

`gozcu/models.py` (Görev 01) içindeki bütün tipler. Bu görevde kullanacakların:
`Gozlem`, `Yorum`, `Epizot`, `RiskDegerlendirme`, `Devir`, `AksiyonKaydi`,
`Duzeltme`, `DiyalogSatiri`.

## Ne yapacaksın

`gozcu/store.py` — model başına bir tablo, iç içe yapılar JSON sütununda.

Üreteceğin arayüz:

```python
Store(db_path: str | Path = ":memory:")

kaydet_gozlem(g) -> int          gozlemler() -> list[Gozlem]
kaydet_yorum(y) -> int           yorumlar() -> list[Yorum]
epizot_ac(e) -> int              epizot_guncelle(epizot_id, **alanlar) -> None
acik_epizot() -> Epizot | None   epizotlar() -> list[Epizot]
kaydet_risk(r) -> int            riskler() -> list[RiskDegerlendirme]
kaydet_devir(d) -> int           devirler() -> list[Devir]
kaydet_aksiyon(a) -> int         aksiyonlar() -> list[AksiyonKaydi]
aksiyon_durumu(aksiyon_id, durum) -> None
kaydet_duzeltme(d) -> int        duzeltmeler(epizot_id) -> list[Duzeltme]
kaydet_diyalog(s) -> int         diyalog() -> list[DiyalogSatiri]
kaydet_embedding(epizot_id, vektor) -> None
embeddingler() -> list[tuple[int, list[float]]]
```

## Adımlar

### 1. Başarısız testi yaz — `tests/test_store.py`

```python
from gozcu.models import Devir, Epizot, Gozlem, Sinyaller
from gozcu.store import Store


def test_acik_epizot_returns_only_the_open_one():
    s = Store(":memory:")
    kapali = s.epizot_ac(Epizot(baslangic_ts=0.0, faz="sonuc", ozet_tr="a",
                                on_risk="Düşük", durum="kapali"))
    acik = s.epizot_ac(Epizot(baslangic_ts=10.0, faz="baslangic", ozet_tr="b",
                              on_risk="Kritik", durum="acik"))
    assert s.acik_epizot().id == acik != kapali


def test_epizot_guncelle_persists_and_roundtrips():
    s = Store(":memory:")
    eid = s.epizot_ac(Epizot(baslangic_ts=1.0, faz="baslangic", ozet_tr="x",
                             on_risk="Orta"))
    s.epizot_guncelle(eid, durum="kapali", bitis_ts=9.0, faz="sonuc")
    e = s.epizotlar()[0]
    assert (e.durum, e.bitis_ts, e.faz) == ("kapali", 9.0, "sonuc")


def test_devir_ledger_preserves_insertion_order():
    s = Store(":memory:")
    for hedef in ("yorumlayici", "sentezleyici", "risk_analisti"):
        s.kaydet_devir(Devir(ts=1.0, kaynak_ajan="yonlendirici",
                             hedef_ajan=hedef, neden="n", guven=0.9,
                             payload_ref="r"))
    assert [d.hedef_ajan for d in s.devirler()] == [
        "yorumlayici", "sentezleyici", "risk_analisti"]


def test_gozlem_roundtrips_nested_signals_with_int_keys():
    s = Store(":memory:")
    s.kaydet_gozlem(Gozlem(ts=2.0, sinyaller=Sinyaller(kisi_sayisi=3,
                                                       hizlar={7: 1.5})))
    assert s.gozlemler()[0].sinyaller.hizlar == {7: 1.5}


def test_aksiyon_durumu_updates_in_place_without_a_new_row():
    from gozcu.models import AksiyonKaydi
    s = Store(":memory:")
    aid = s.kaydet_aksiyon(AksiyonKaydi(ts=1.0, tool_adi="uretim_hatti_durdur",
                                        parametreler={}, sonuc={}, kim="ajan",
                                        onay_durumu="bekliyor"))
    s.aksiyon_durumu(aid, "onaylandi")
    assert len(s.aksiyonlar()) == 1
    assert s.aksiyonlar()[0].onay_durumu == "onaylandi"
```

Son iki test önemli. Dördüncüsü: JSON sözlük anahtarlarını string olarak geri
verir, `hizlar` ise `dict[int, float]` — Pydantic'in bunu geri çevirdiğini
kanıtlıyor. Beşincisi: onay akışı bu metoda dayanıyor, yeni satır eklemeyip
mevcut satırı güncellemesi şart (Görev 14).

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_store.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.store'`

### 3. `gozcu/store.py` yaz

```python
import json
import sqlite3
from pathlib import Path

from gozcu.models import (AksiyonKaydi, Devir, DiyalogSatiri, Duzeltme, Epizot,
                          Gozlem, RiskDegerlendirme, Yorum)

SEMA = """
CREATE TABLE IF NOT EXISTS gozlem (id INTEGER PRIMARY KEY, ts REAL, veri TEXT);
CREATE TABLE IF NOT EXISTS yorum (id INTEGER PRIMARY KEY, veri TEXT);
CREATE TABLE IF NOT EXISTS epizot (id INTEGER PRIMARY KEY, durum TEXT, veri TEXT);
CREATE TABLE IF NOT EXISTS epizot_embedding (epizot_id INTEGER PRIMARY KEY, vektor TEXT);
CREATE TABLE IF NOT EXISTS risk (id INTEGER PRIMARY KEY, veri TEXT);
CREATE TABLE IF NOT EXISTS devir (id INTEGER PRIMARY KEY, veri TEXT);
CREATE TABLE IF NOT EXISTS aksiyon (id INTEGER PRIMARY KEY, veri TEXT);
CREATE TABLE IF NOT EXISTS duzeltme (id INTEGER PRIMARY KEY, epizot_id INTEGER, veri TEXT);
CREATE TABLE IF NOT EXISTS diyalog (id INTEGER PRIMARY KEY, veri TEXT);
"""


class Store:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.executescript(SEMA)
        self.db.commit()

    def _ekle(self, tablo: str, model, **sutunlar) -> int:
        veri = model.model_dump_json(exclude={"id"})
        adlar = ", ".join(["veri", *sutunlar])
        yer = ", ".join("?" * (1 + len(sutunlar)))
        cur = self.db.execute(
            f"INSERT INTO {tablo} ({adlar}) VALUES ({yer})",
            (veri, *sutunlar.values()))
        self.db.commit()
        return cur.lastrowid

    def _oku(self, tablo: str, tip, kosul: str = "", *params) -> list:
        rows = self.db.execute(
            f"SELECT id, veri FROM {tablo} {kosul} ORDER BY id", params)
        return [tip(**{**json.loads(v), "id": i}) for i, v in rows]

    def kaydet_gozlem(self, g: Gozlem) -> int:
        return self._ekle("gozlem", g, ts=g.ts)

    def gozlemler(self) -> list[Gozlem]:
        return self._oku("gozlem", Gozlem)

    def kaydet_yorum(self, y: Yorum) -> int:
        return self._ekle("yorum", y)

    def yorumlar(self) -> list[Yorum]:
        return self._oku("yorum", Yorum)

    def epizot_ac(self, e: Epizot) -> int:
        return self._ekle("epizot", e, durum=e.durum)

    def epizot_guncelle(self, epizot_id: int, **alanlar) -> None:
        row = self.db.execute(
            "SELECT veri FROM epizot WHERE id = ?", (epizot_id,)).fetchone()
        e = Epizot(**{**json.loads(row[0]), **alanlar})
        self.db.execute("UPDATE epizot SET veri = ?, durum = ? WHERE id = ?",
                        (e.model_dump_json(exclude={"id"}), e.durum, epizot_id))
        self.db.commit()

    def acik_epizot(self) -> Epizot | None:
        acik = self._oku("epizot", Epizot, "WHERE durum = ?", "acik")
        return acik[-1] if acik else None

    def epizotlar(self) -> list[Epizot]:
        return self._oku("epizot", Epizot)

    def kaydet_risk(self, r: RiskDegerlendirme) -> int:
        return self._ekle("risk", r)

    def riskler(self) -> list[RiskDegerlendirme]:
        return self._oku("risk", RiskDegerlendirme)

    def kaydet_devir(self, d: Devir) -> int:
        return self._ekle("devir", d)

    def devirler(self) -> list[Devir]:
        return self._oku("devir", Devir)

    def kaydet_aksiyon(self, a: AksiyonKaydi) -> int:
        return self._ekle("aksiyon", a)

    def aksiyonlar(self) -> list[AksiyonKaydi]:
        return self._oku("aksiyon", AksiyonKaydi)

    def aksiyon_durumu(self, aksiyon_id: int, durum: str) -> None:
        row = self.db.execute(
            "SELECT veri FROM aksiyon WHERE id = ?", (aksiyon_id,)).fetchone()
        a = AksiyonKaydi(**{**json.loads(row[0]), "onay_durumu": durum})
        self.db.execute("UPDATE aksiyon SET veri = ? WHERE id = ?",
                        (a.model_dump_json(exclude={"id"}), aksiyon_id))
        self.db.commit()

    def kaydet_duzeltme(self, d: Duzeltme) -> int:
        return self._ekle("duzeltme", d, epizot_id=d.epizot_id)

    def duzeltmeler(self, epizot_id: int) -> list[Duzeltme]:
        return self._oku("duzeltme", Duzeltme, "WHERE epizot_id = ?", epizot_id)

    def kaydet_diyalog(self, s: DiyalogSatiri) -> int:
        return self._ekle("diyalog", s)

    def diyalog(self) -> list[DiyalogSatiri]:
        return self._oku("diyalog", DiyalogSatiri)

    def kaydet_embedding(self, epizot_id: int, vektor: list[float]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO epizot_embedding VALUES (?, ?)",
            (epizot_id, json.dumps(vektor)))
        self.db.commit()

    def embeddingler(self) -> list[tuple[int, list[float]]]:
        return [(i, json.loads(v)) for i, v in
                self.db.execute("SELECT epizot_id, vektor FROM epizot_embedding")]
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_store.py -v
```
Beklenen: 5 passed

### 5. Commit

```bash
git add gozcu/store.py tests/test_store.py
git commit -m "feat: SQLite event store for observations, episodes and ledgers"
```

## Doğrulama

```bash
uv run pytest tests/test_store.py -v
```
Beklenen: **5 passed**
