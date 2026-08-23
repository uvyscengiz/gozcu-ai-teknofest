# Agentic Gözcü Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing per-frame perception pipeline into an agentic video decision-support system that decides on the video's own clock, talks to a Turkish-speaking operator, calls mock field systems mid-run, and closes with a structured JSON report plus a root-cause report.

**Architecture:** A supervisor agent (Nöbetçi) with expert sub-agents, fed by a deterministic local perception pipeline. A cheap router decides what deserves attention; a VLM interprets only triggered windows; a synthesizer turns observations into episodes. Every cross-agent handoff is a typed record in a SQLite event store, which doubles as the explainability ledger and the episodic memory searched by embedding + reranker.

**Tech Stack:** Python 3.12, Pydantic v2, SQLite (stdlib `sqlite3`), `openai` client against the organizers' LiteLLM gateway, Ultralytics YOLOE + ByteTrack (local, existing), Gradio, pytest, numpy.

**Spec:** [docs/superpowers/specs/2026-08-22-agentic-gozcu-design.md](../specs/2026-08-22-agentic-gozcu-design.md)

## Global Constraints

- **Deadline 2026-08-26 23:59.** Code freeze **2026-08-26 12:00**. After freeze: bug fixes and packaging only.
- **Input is an uploaded video file.** No live camera, no RTSP. `FrameSource` exists but only a file source ships.
- **Decisions happen in flight.** Tool calls fire at the moment of the event inside the video's timeline, never after the closing report. See spec §3a.
- **All model calls go through the gateway** at `GOZCU_GATEWAY_BASE_URL`, OpenAI-compatible. Every model id lives in `gozcu/config.py` and nowhere else.
- **The perception layer is frozen.** `frames.py`, `detect.py`, `track.py`, `signals.py` get no new features. `interpret.py` is wrapped, not rewritten.
- **All operator-facing text is Turkish.** Short sentences, field terminology (`istif aracı`, `vardiya amiri`, `yerde hareketsiz kişi`), avoid passive constructions.
- **The four top-level JSON keys are `summary`, `events`, `risk`, `actions`** — verbatim from the şartname, produced even when extended layers fail.
- **Risk levels are exactly** `"Düşük" | "Orta" | "Yüksek" | "Kritik"`.
- **Timestamps in operator-facing output are `MM:SS`**; timestamps in storage are float seconds from video start.
- Open source only, no paid dependency, everything runs from `git clone` + `uv sync`.

---

## Schedule

Not four people for three days. **Two solo days, then two team days.**

| Day | Üveys (`uvyscengiz`) | `Xana-bit` | `beyzaalive` | `rumeysaoru` |
|---|---|---|---|---|
| **23 Aug** | Tasks 1, 2, 3, 4 | — | — | — |
| **24 Aug** | Tasks 5, 6 + wire `run.py` + UI refresh | — | — | — |
| **25 Aug** | Tasks 7, 10, 13 | Tasks 8, 9 | Tasks 11, 12 | Task 14 |
| **26 Aug am** | Task 16 | demo filming | Turkish style pass | Task 15 + benchmark run |
| **26 Aug pm** | **Packaging — everyone.** Code freeze 12:00 | | | |

### The 24 August exit criterion

By the end of the second solo day this must be true:

```bash
uv run python app.py     # upload one clip → four-key JSON appears in the UI
```

It does not need to be good. It needs to **run**. Three people arrive on the
25th either to a working system they extend, or to an empty scaffold they must
first understand — and there is no recovering from the second with one day left.
If the day is slipping, cut Task 6 before cutting integration.

### Why these tasks go to the people who arrive on the 25th

Tasks 8, 9, 11, 12 and 14 sit **entirely off the integration path**. The field
tools are plain Python functions that call no model. The fixtures are JSON. The
KPIs are pure functions over the store. The guard is fifteen lines. Each is
verified by one test command, none blocks anyone else, and none requires
understanding the decision loop. Tasks 13 and 16 stay with Üveys because they do.

Load is not equal — Üveys works four days, everyone else two. The **team days**
are balanced: roughly two person-days each across the 25th and 26th.

### File ownership

`gateway.py` (Tasks 3, 7), `config.py` (3), `run.py` and `app.py` (16) are all
Üveys. Everyone joining on the 25th writes **files that do not yet exist**.
Nothing needs coordinating beyond the interface reference below — work is fully
async.

## Interface reference

Everything the tasks depend on, with real paths and signatures. Task issues link
here instead of saying "see Task N".

```python
# gozcu/models.py  — Task 1. Pydantic v2, all extra="forbid".
RiskSeviyesi = Literal["Düşük", "Orta", "Yüksek", "Kritik"]
Tespit(sinif, guven, kutu, track_id)
Sinyaller(hizlar: dict[int, float], kaybolan_trackler, kisi_sayisi, toplanma)
Gozlem(id, ts, tespitler, sinyaller)
RouterKarari(karar, gerekce, guven)
Yorum(id, gozlem_ts, aciklama, notable_event, model, gecikme_ms, token)
Epizot(id, baslangic_ts, bitis_ts, faz, ozet_tr, katilimcilar, on_risk, durum)
AdayAksiyon(aciklama_tr, tool_adi, parametreler)
RiskDegerlendirme(id, epizot_id, seviye, gerekce_tr, onlenebilir, aday_aksiyonlar)
Devir(id, ts, kaynak_ajan, hedef_ajan, neden, guven, payload_ref)
AksiyonKaydi(id, ts, tool_adi, parametreler, sonuc, kim, onay_durumu)
Duzeltme(id, ts, epizot_id, alan, eski, yeni, gerekce)
DiyalogSatiri(id, ts, rol, metin)
OlayOzeti(time, event);  Ayrintili(...);  PipelineCiktisi(summary, events, risk, actions, ayrintili)

# gozcu/store.py  — Task 2. Store(":memory:") in tests.
kaydet_gozlem(g) -> int      gozlemler() -> list[Gozlem]
kaydet_yorum(y) -> int       yorumlar() -> list[Yorum]
epizot_ac(e) -> int          epizot_guncelle(epizot_id, **alanlar) -> None
acik_epizot() -> Epizot|None epizotlar() -> list[Epizot]
kaydet_risk(r) -> int        riskler() -> list[RiskDegerlendirme]
kaydet_devir(d) -> int       devirler() -> list[Devir]
kaydet_aksiyon(a) -> int     aksiyonlar() -> list[AksiyonKaydi]
kaydet_duzeltme(d) -> int    duzeltmeler(epizot_id) -> list[Duzeltme]
kaydet_diyalog(s) -> int     diyalog() -> list[DiyalogSatiri]
kaydet_embedding(epizot_id, vektor) -> None
embeddingler() -> list[tuple[int, list[float]]]

# gozcu/gateway.py  — Tasks 3, 7.
Gateway(store=None)
  .sor(kademe, mesajlar, sema=None, araclar=None) -> Yanit   # kademe positional
  .goem(metin) -> list[float]
  .yeniden_sirala(sorgu, adaylar) -> list[int]
  .hata_enjekte(kademeler: set[str]) -> None
  .bozulmus_mu() -> bool
Yanit(icerik, arac_cagrilari, model, gecikme_ms, token, bozulmus)
Kademeler: "router" | "hizli" | "ana" | "vlm" | "guard" | "embed" | "rerank"

# gozcu/memory.py  — Task 7.
epizodu_gom(gw, store, epizot) -> None
zaman_cizelgesi_ara(gw, store, sorgu, ust_k=5) -> list[Epizot]

# gozcu/tools/registry.py  — Task 8.
ARACLAR: dict[str, Callable];  ARAC_SEMALARI: list[dict]
ONAY_GEREKTIREN: set[str] = {"uretim_hatti_durdur"}
cagir(store, tool_adi, parametreler, kim="ajan") -> dict
```

## Issue template

Every GitHub issue opens with this block, filled in. Three people start cold on
the 25th; the task body alone is not enough for them.

```markdown
### Bu proje ne?
Gözcü, fabrika kamera kaydını izleyip olayları fark eden, riski değerlendiren
ve operatörle Türkçe konuşan bir karar destek sistemi. TEKNOFEST Yapay Zekâ
Dil Ajanları Yarışması, 3. senaryo. Teslim: 26 Ağustos 23:59.

### Kurulum
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest && uv sync
uv run pytest tests/ -v          # mevcut testlerin geçtiğini gör

### Bu görev neye dayanıyor
Planın "Interface reference" bölümü: docs/superpowers/plans/2026-08-23-agentic-gozcu.md
Bu görevin ihtiyaç duyduğu her imza orada, gerçek dosya yollarıyla.

### Bittiğini nasıl anlarsın
<tek doğrulama komutu>
Beklenen: <N> passed

### Takıldığında
Üveys'e yaz. Bekleme — bu sprintte bir saat, kapasitenin %4'ü.
```

Then the task section from the plan, verbatim.

## File structure

| File | Responsibility | Task |
|---|---|---|
| `gozcu/models.py` | Every Pydantic type crossing a boundary | 1 |
| `gozcu/store.py` | SQLite schema + repository functions | 2 |
| `gozcu/gateway.py` | Tiered model client, retry, degraded mode | 3 |
| `gozcu/config.py` | Model ids, tier names, gateway URL (modify) | 3 |
| `gozcu/loop.py` | The in-flight decision loop | 4 |
| `gozcu/agents/router.py` | Window → routing decision | 5 |
| `gozcu/agents/synthesizer.py` | Observations → `Epizot` | 6 |
| `gozcu/memory.py` | Embed, search, rerank over episodes | 7 |
| `gozcu/tools/saha.py` | Seven mock field-system tools | 8 |
| `gozcu/tools/registry.py` | Tool schemas + dispatch + action ledger | 8 |
| `gozcu/fixtures/*.json` | The seeded facility world | 9 |
| `gozcu/agents/risk.py` | Risk Analisti | 10 |
| `gozcu/agents/raportor.py` | Root-cause report | 11 |
| `gozcu/guard.py` | Operator-facing text check | 12 |
| `gozcu/agents/nobetci.py` | Supervisor, tool-call loop, proactive channel | 13 |
| `benchmark/run.py`, `benchmark/report.py` | KPI harness and report | 14 |
| `gozcu/ui/console.py` | Operator console (replaces `app.py`) | 15 |
| `gozcu/report.py` | The §4b output contract assembler | 16 |
| `tests/test_dialog_senaryo.py` | The eight-beat acceptance test | 15 |

---

## Task 1: Shared contract — `gozcu/models.py`

**Owner:** `uvyscengiz` · 23 Ağustos · **Blocks:** everything · **Do this first.**

**Files:**
- Create: `gozcu/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: every type below. No other task may invent a type that crosses a module boundary; if one is missing, add it here.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
import pytest
from pydantic import ValidationError
from gozcu.models import Epizot, PipelineCiktisi, RouterKarari, Sinyaller


def test_router_karari_rejects_unknown_decision():
    with pytest.raises(ValidationError):
        RouterKarari(karar="belki", gerekce="x", guven=0.5)


def test_epizot_requires_known_risk_level():
    with pytest.raises(ValidationError):
        Epizot(baslangic_ts=0.0, faz="baslangic", ozet_tr="x",
               on_risk="High", durum="acik")


def test_pipeline_ciktisi_has_the_four_sartname_keys():
    c = PipelineCiktisi(summary="özet", events=[], risk="Yüksek", actions=[])
    assert set(c.model_dump(exclude_none=True)) == {
        "summary", "events", "risk", "actions"}


def test_sinyaller_defaults_are_empty_not_none():
    s = Sinyaller()
    assert s.hizlar == {} and s.kaybolan_trackler == [] and s.kisi_sayisi == 0
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gozcu.models'`

- [ ] **Step 3: Write `gozcu/models.py`**

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RiskSeviyesi = Literal["Düşük", "Orta", "Yüksek", "Kritik"]
AjanAdi = Literal["algi", "yonlendirici", "yorumlayici", "sentezleyici",
                  "risk_analisti", "nobetci", "raportor"]


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Tespit(Base):
    sinif: str
    guven: float
    kutu: tuple[float, float, float, float]
    track_id: int | None = None


class Sinyaller(Base):
    hizlar: dict[int, float] = Field(default_factory=dict)
    kaybolan_trackler: list[int] = Field(default_factory=list)
    kisi_sayisi: int = 0
    toplanma: bool = False


class Gozlem(Base):
    id: int | None = None
    ts: float
    tespitler: list[Tespit] = Field(default_factory=list)
    sinyaller: Sinyaller = Field(default_factory=Sinyaller)


class RouterKarari(Base):
    karar: Literal["yoksay", "gorsel_incele", "epizot_ac",
                   "epizot_guncelle", "epizot_kapat", "acil_yukselt"]
    gerekce: str = Field(max_length=200)
    guven: float = Field(ge=0.0, le=1.0)


class Yorum(Base):
    id: int | None = None
    gozlem_ts: float
    aciklama: str = Field(max_length=300)
    notable_event: str | None = Field(default=None, max_length=200)
    model: str
    gecikme_ms: int = 0
    token: int = 0


class Epizot(Base):
    id: int | None = None
    baslangic_ts: float
    bitis_ts: float | None = None
    faz: Literal["baslangic", "gelisim", "sonuc"]
    ozet_tr: str = Field(max_length=600)
    katilimcilar: list[str] = Field(default_factory=list)
    on_risk: RiskSeviyesi
    durum: Literal["acik", "kapali"] = "acik"


class AdayAksiyon(Base):
    aciklama_tr: str = Field(max_length=200)
    tool_adi: str
    parametreler: dict = Field(default_factory=dict)


class RiskDegerlendirme(Base):
    id: int | None = None
    epizot_id: int
    seviye: RiskSeviyesi
    gerekce_tr: str = Field(max_length=800)
    onlenebilir: bool
    aday_aksiyonlar: list[AdayAksiyon] = Field(default_factory=list)


class Devir(Base):
    id: int | None = None
    ts: float
    kaynak_ajan: AjanAdi
    hedef_ajan: AjanAdi
    neden: str = Field(max_length=200)
    guven: float = Field(ge=0.0, le=1.0)
    payload_ref: str


class AksiyonKaydi(Base):
    id: int | None = None
    ts: float
    tool_adi: str
    parametreler: dict = Field(default_factory=dict)
    sonuc: dict = Field(default_factory=dict)
    kim: Literal["ajan", "operator"]
    onay_durumu: Literal["gerekmiyor", "bekliyor", "onaylandi", "reddedildi"]


class Duzeltme(Base):
    id: int | None = None
    ts: float
    epizot_id: int
    alan: str
    eski: str
    yeni: str
    gerekce: str = Field(max_length=300)


class DiyalogSatiri(Base):
    id: int | None = None
    ts: float
    rol: Literal["operator", "nobetci", "sistem"]
    metin: str


class OlayOzeti(Base):
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    event: str = Field(max_length=200)


class Ayrintili(Base):
    epizotlar: list[Epizot] = Field(default_factory=list)
    risk_degerlendirmeleri: list[RiskDegerlendirme] = Field(default_factory=list)
    devir_zinciri: list[Devir] = Field(default_factory=list)
    aksiyon_defteri: list[AksiyonKaydi] = Field(default_factory=list)
    kok_neden_raporu: dict | None = None


class PipelineCiktisi(Base):
    summary: str
    events: list[OlayOzeti] = Field(default_factory=list)
    risk: RiskSeviyesi
    actions: list[str] = Field(default_factory=list)
    ayrintili: Ayrintili | None = None
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add gozcu/models.py tests/test_models.py
git commit -m "feat: shared Pydantic contract for the agent layer"
```

---

## Task 2: Event store — `gozcu/store.py`

**Owner:** `uvyscengiz` · 23 Ağustos

**Files:**
- Create: `gozcu/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: every model from Task 1.
- Produces:
  - `Store(db_path: str | Path)` — pass `":memory:"` in tests.
  - `store.kaydet_gozlem(g: Gozlem) -> int`
  - `store.kaydet_yorum(y: Yorum) -> int`
  - `store.epizot_ac(e: Epizot) -> int`
  - `store.epizot_guncelle(epizot_id: int, **alanlar) -> None`
  - `store.acik_epizot() -> Epizot | None`
  - `store.epizotlar() -> list[Epizot]`
  - `store.kaydet_risk(r: RiskDegerlendirme) -> int`
  - `store.kaydet_devir(d: Devir) -> int`
  - `store.devirler() -> list[Devir]`
  - `store.kaydet_aksiyon(a: AksiyonKaydi) -> int`
  - `store.aksiyonlar() -> list[AksiyonKaydi]`
  - `store.kaydet_duzeltme(d: Duzeltme) -> int`
  - `store.duzeltmeler(epizot_id: int) -> list[Duzeltme]`
  - `store.kaydet_diyalog(s: DiyalogSatiri) -> int`
  - `store.diyalog() -> list[DiyalogSatiri]`
  - `store.kaydet_embedding(epizot_id: int, vektor: list[float]) -> None`
  - `store.embeddingler() -> list[tuple[int, list[float]]]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store.py
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


def test_gozlem_roundtrips_nested_signals():
    s = Store(":memory:")
    s.kaydet_gozlem(Gozlem(ts=2.0, sinyaller=Sinyaller(kisi_sayisi=3,
                                                       hizlar={7: 1.5})))
    assert s.gozlemler()[0].sinyaller.hizlar == {7: 1.5}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gozcu.store'`

- [ ] **Step 3: Implement `gozcu/store.py`**

Schema: one table per model, JSON columns for nested structures. `hizlar` keys come back from JSON as strings — convert to `int` on read, which is what the fourth test pins.

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

`Gozlem.sinyaller.hizlar` is typed `dict[int, float]`, and Pydantic coerces the string keys JSON gives back — the fourth test is what proves it.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/test_store.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add gozcu/store.py tests/test_store.py
git commit -m "feat: SQLite event store for observations, episodes and ledgers"
```

---

## Task 3: Tiered gateway client — `gozcu/gateway.py`

**Owner:** `uvyscengiz` · 23 Ağustos

Every model call in the system goes through here. Degraded mode is a designed feature, not an accident: demo beat 6 depends on it.

**Files:**
- Create: `gozcu/gateway.py`
- Modify: `gozcu/config.py`
- Test: `tests/test_gateway.py`

**Interfaces:**
- Consumes: `gozcu.config`.
- Produces:
  - `Kademe = Literal["router", "hizli", "ana", "vlm", "guard"]`
  - `Gateway(store: Store | None = None)`
  - `gw.sor(kademe, mesajlar, sema: type[BaseModel] | None = None, araclar: list[dict] | None = None) -> Yanit`
  - `Yanit(icerik: str, arac_cagrilari: list[dict], model: str, gecikme_ms: int, token: int, bozulmus: bool)`
  - `gw.bozulmus_mu() -> bool`
  - `gw.hata_enjekte(kademeler: set[str]) -> None` — demo beat 6 and tests

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gateway.py
import pytest
from pydantic import BaseModel

from gozcu.gateway import Gateway, GatewayHatasi


class Sema(BaseModel):
    a: int


def test_injected_failure_marks_degraded_not_crash():
    gw = Gateway()
    gw.hata_enjekte({"vlm"})
    yanit = gw.sor("vlm", [{"role": "user", "content": "x"}])
    assert yanit.bozulmus is True and yanit.icerik == ""
    assert gw.bozulmus_mu() is True


def test_injected_failure_is_scoped_to_named_tiers():
    gw = Gateway()
    gw.hata_enjekte({"vlm"})
    with pytest.raises(GatewayHatasi):
        gw.sor("ana", [{"role": "user", "content": "x"}], _deneme=1)


def test_recovery_clears_degraded_flag():
    gw = Gateway()
    gw.hata_enjekte({"vlm"})
    gw.sor("vlm", [{"role": "user", "content": "x"}])
    gw.hata_enjekte(set())
    assert gw.bozulmus_mu() is False
```

The second test asserts that failure injection targets only the tiers it names — a leak there would make beat 6 look like a total outage instead of a partial one. It reaches the real gateway and is expected to raise, so it passes `_deneme=1` to skip retry backoff.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_gateway.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gozcu.gateway'`

- [ ] **Step 3: Add tier config to `gozcu/config.py`**

Append; do not remove the existing YOLO/frame settings.

```python
GATEWAY_BASE_URL = os.environ.get(
    "GOZCU_GATEWAY_BASE_URL", "http://localhost:4000/v1")
GATEWAY_API_KEY = os.environ.get("GOZCU_GATEWAY_API_KEY", "not-needed")

MODELLER = {
    "router": os.environ.get("GOZCU_MODEL_ROUTER", "Qwen3-8B"),
    "hizli":  os.environ.get("GOZCU_MODEL_HIZLI",  "Qwen3.6-35B-A3B"),
    "ana":    os.environ.get("GOZCU_MODEL_ANA",    "Qwen3.5-122B-A10B"),
    "vlm":    os.environ.get("GOZCU_MODEL_VLM",    "Qwen3-VL-30B-A3B"),
    "guard":  os.environ.get("GOZCU_MODEL_GUARD",  "Qwen3Guard-Gen-4B"),
    "embed":  os.environ.get("GOZCU_MODEL_EMBED",  "Qwen3-Embedding-4B"),
    "rerank": os.environ.get("GOZCU_MODEL_RERANK", "Qwen3-Reranker-4B"),
}

GATEWAY_TIMEOUT_S = float(os.environ.get("GOZCU_GATEWAY_TIMEOUT", "60"))
GATEWAY_DENEME = int(os.environ.get("GOZCU_GATEWAY_DENEME", "3"))
```

If the organizers deploy different model names, this dict is the only edit.

- [ ] **Step 4: Implement `gozcu/gateway.py`**

```python
import time
from dataclasses import dataclass, field

from openai import OpenAI
from pydantic import BaseModel

from gozcu.config import (GATEWAY_API_KEY, GATEWAY_BASE_URL, GATEWAY_DENEME,
                          GATEWAY_TIMEOUT_S, MODELLER)

BOZULABILIR = {"vlm", "hizli"}  # tiers the system can lose and keep working


class GatewayHatasi(RuntimeError):
    """A tier failed after every retry and has no degraded fallback."""


@dataclass
class Yanit:
    icerik: str = ""
    arac_cagrilari: list[dict] = field(default_factory=list)
    model: str = ""
    gecikme_ms: int = 0
    token: int = 0
    bozulmus: bool = False


class Gateway:
    def __init__(self, store=None) -> None:
        self.store = store
        self._client = OpenAI(base_url=GATEWAY_BASE_URL,
                              api_key=GATEWAY_API_KEY,
                              timeout=GATEWAY_TIMEOUT_S)
        self._enjekte: set[str] = set()
        self._bozuk: set[str] = set()

    def hata_enjekte(self, kademeler: set[str]) -> None:
        self._enjekte = set(kademeler)
        if not kademeler:
            self._bozuk.clear()

    def bozulmus_mu(self) -> bool:
        return bool(self._bozuk)

    def sor(self, kademe: str, mesajlar: list[dict],
            sema: type[BaseModel] | None = None,
            araclar: list[dict] | None = None,
            _deneme: int | None = None) -> Yanit:
        model = MODELLER[kademe]
        denemeler = _deneme if _deneme is not None else GATEWAY_DENEME
        son_hata: Exception | None = None

        for i in range(denemeler):
            if kademe in self._enjekte:
                son_hata = GatewayHatasi(f"enjekte edilmiş hata: {kademe}")
                break
            t0 = time.monotonic()
            try:
                istek: dict = {"model": model, "messages": mesajlar}
                if sema is not None:
                    istek["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {"name": sema.__name__,
                                        "schema": sema.model_json_schema(),
                                        "strict": True}}
                if araclar:
                    istek["tools"] = araclar
                r = self._client.chat.completions.create(**istek)
                msg = r.choices[0].message
                self._bozuk.discard(kademe)
                return Yanit(
                    icerik=msg.content or "",
                    arac_cagrilari=[t.model_dump() for t in (msg.tool_calls or [])],
                    model=model,
                    gecikme_ms=int((time.monotonic() - t0) * 1000),
                    token=getattr(r.usage, "total_tokens", 0) or 0)
            except Exception as exc:  # noqa: BLE001 — any transport failure retries
                son_hata = exc
                if i < denemeler - 1:
                    time.sleep(0.5 * (2 ** i))

        if kademe in BOZULABILIR:
            self._bozuk.add(kademe)
            return Yanit(model=model, bozulmus=True)
        raise GatewayHatasi(f"{kademe} kademesi yanıt vermedi") from son_hata
```

Only `vlm` and `hizli` degrade. A `router` or `ana` failure raises, because there is no meaningful system without them — better a loud error than a silently lobotomised agent.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `uv run pytest tests/test_gateway.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add gozcu/gateway.py gozcu/config.py tests/test_gateway.py
git commit -m "feat: tiered gateway client with scoped degraded mode"
```

---

## Task 4: The in-flight decision loop — `gozcu/loop.py`

**Owner:** `uvyscengiz` · 23 Ağustos · **This task is the spec's §3a made real.**

The loop walks the video's timeline. When the router escalates, it stops and hands off — before the video is finished. Everything downstream is a callback so this module stays testable without any agent.

**Files:**
- Create: `gozcu/loop.py`
- Test: `tests/test_loop.py`

**Interfaces:**
- Consumes: `Store` (Task 2), `Gozlem`/`RouterKarari`/`Devir` (Task 1).
- Produces:
  - `PENCERE_S = 10.0`
  - `pencereler(gozlemler: list[Gozlem], pencere_s: float = PENCERE_S) -> Iterator[list[Gozlem]]`
  - `taban_gecti(pencere: list[Gozlem]) -> bool`
  - `KararDongusu(store, yonlendir, yorumla, sentezle, yukselt)` where every callback is injected
  - `dongu.calistir(gozlemler: list[Gozlem]) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_loop.py
from gozcu.loop import KararDongusu, pencereler, taban_gecti
from gozcu.models import Gozlem, RouterKarari, Sinyaller, Tespit
from gozcu.store import Store


def _gozlem(ts, kisi=0, hiz=None):
    return Gozlem(ts=ts, tespitler=[Tespit(sinif="person", guven=0.9,
                                           kutu=(0, 0, 1, 1), track_id=1)] * kisi,
                  sinyaller=Sinyaller(kisi_sayisi=kisi, hizlar=hiz or {}))


def test_pencereler_groups_by_ten_seconds():
    g = [_gozlem(float(t)) for t in range(25)]
    assert [len(p) for p in pencereler(g)] == [10, 10, 5]


def test_taban_blocks_a_completely_still_window():
    assert taban_gecti([_gozlem(float(t)) for t in range(10)]) is False
    assert taban_gecti([_gozlem(float(t), kisi=2) for t in range(10)]) is True


def test_router_is_not_called_for_windows_below_the_floor():
    cagrilar = []
    d = KararDongusu(Store(":memory:"),
                     yonlendir=lambda p: cagrilar.append(p) or RouterKarari(
                         karar="yoksay", gerekce="x", guven=0.5),
                     yorumla=lambda p: None, sentezle=lambda p, y: None,
                     yukselt=lambda e: None)
    d.calistir([_gozlem(float(t)) for t in range(20)])
    assert cagrilar == []


def test_escalation_fires_before_the_video_ends():
    store, ne_zaman = Store(":memory:"), []
    gozlemler = [_gozlem(float(t), kisi=2) for t in range(30)]

    def yonlendir(p):
        karar = "acil_yukselt" if p[0].ts < 10 else "yoksay"
        return RouterKarari(karar=karar, gerekce="x", guven=0.9)

    d = KararDongusu(store, yonlendir=yonlendir, yorumla=lambda p: None,
                     sentezle=lambda p, y: None,
                     yukselt=lambda e: ne_zaman.append(e))
    d.calistir(gozlemler)
    assert ne_zaman and ne_zaman[0] < gozlemler[-1].ts


def test_every_routing_decision_is_written_to_the_handoff_ledger():
    store = Store(":memory:")
    d = KararDongusu(store,
                     yonlendir=lambda p: RouterKarari(karar="yoksay",
                                                      gerekce="sakin",
                                                      guven=0.8),
                     yorumla=lambda p: None, sentezle=lambda p, y: None,
                     yukselt=lambda e: None)
    d.calistir([_gozlem(float(t), kisi=1) for t in range(20)])
    assert len(store.devirler()) == 2
    assert store.devirler()[0].kaynak_ajan == "yonlendirici"
```

`test_escalation_fires_before_the_video_ends` is the one that pins §3a. If someone later refactors the loop into collect-then-decide, this test goes red.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_loop.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gozcu.loop'`

- [ ] **Step 3: Implement `gozcu/loop.py`**

```python
from collections.abc import Callable, Iterator

from gozcu.models import Devir, Gozlem, RouterKarari
from gozcu.store import Store

PENCERE_S = 10.0
TABAN_HIZ = 1.0


def pencereler(gozlemler: list[Gozlem],
               pencere_s: float = PENCERE_S) -> Iterator[list[Gozlem]]:
    if not gozlemler:
        return
    basla, kova = gozlemler[0].ts, []
    for g in gozlemler:
        if g.ts - basla >= pencere_s:
            yield kova
            basla, kova = g.ts, []
        kova.append(g)
    if kova:
        yield kova


def taban_gecti(pencere: list[Gozlem]) -> bool:
    """Cheap local floor: decides *when to ask*, never *what matters*."""
    for g in pencere:
        s = g.sinyaller
        if s.kisi_sayisi > 0 or s.kaybolan_trackler or s.toplanma:
            return True
        if any(h >= TABAN_HIZ for h in s.hizlar.values()):
            return True
    return False


class KararDongusu:
    def __init__(self, store: Store,
                 yonlendir: Callable[[list[Gozlem]], RouterKarari],
                 yorumla: Callable[[list[Gozlem]], object],
                 sentezle: Callable[[list[Gozlem], object], int | None],
                 yukselt: Callable[[float], None]) -> None:
        self.store = store
        self.yonlendir = yonlendir
        self.yorumla = yorumla
        self.sentezle = sentezle
        self.yukselt = yukselt

    def _devir(self, hedef: str, ts: float, neden: str, guven: float) -> None:
        self.store.kaydet_devir(Devir(ts=ts, kaynak_ajan="yonlendirici",
                                      hedef_ajan=hedef, neden=neden,
                                      guven=guven, payload_ref=f"pencere@{ts}"))

    def calistir(self, gozlemler: list[Gozlem]) -> None:
        for pencere in pencereler(gozlemler):
            ts = pencere[0].ts
            if not taban_gecti(pencere):
                continue

            karar = self.yonlendir(pencere)
            hedef = {"gorsel_incele": "yorumlayici",
                     "epizot_ac": "sentezleyici",
                     "epizot_guncelle": "sentezleyici",
                     "epizot_kapat": "sentezleyici",
                     "acil_yukselt": "nobetci"}.get(karar.karar, "algi")
            self._devir(hedef, ts, karar.gerekce, karar.guven)

            if karar.karar == "yoksay":
                continue

            yorum = self.yorumla(pencere) if karar.karar in (
                "gorsel_incele", "epizot_ac", "epizot_guncelle") else None

            if karar.karar in ("epizot_ac", "epizot_guncelle", "epizot_kapat"):
                self.sentezle(pencere, yorum)

            if karar.karar == "acil_yukselt":
                # Fires here, mid-video. This is the whole point of §3a.
                self.yukselt(ts)
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/test_loop.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add gozcu/loop.py tests/test_loop.py
git commit -m "feat: in-flight decision loop with windowed routing and local floor"
```

---

## Task 5: Router agent — `gozcu/agents/router.py`

**Owner:** `uvyscengiz` · 24 Ağustos

**Files:**
- Create: `gozcu/agents/__init__.py` (empty), `gozcu/agents/router.py`
- Test: `tests/test_router.py`

**Interfaces:**
- Consumes: `Gateway.sor` (Task 3), `Gozlem`/`RouterKarari` (Task 1).
- Produces:
  - `pencere_ozeti(pencere: list[Gozlem]) -> str` — the digest the router sees
  - `yonlendir(gw: Gateway, pencere: list[Gozlem], acik_epizot_var: bool) -> RouterKarari`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_router.py
from unittest.mock import Mock

from gozcu.agents.router import pencere_ozeti, yonlendir
from gozcu.gateway import Yanit
from gozcu.models import Gozlem, Sinyaller


def _g(ts, **kw):
    return Gozlem(ts=ts, sinyaller=Sinyaller(**kw))


def test_digest_is_text_and_carries_no_image():
    ozet = pencere_ozeti([_g(0.0, kisi_sayisi=2, hizlar={1: 3.4}),
                          _g(1.0, kaybolan_trackler=[1])])
    assert "00:00" in ozet and "2" in ozet and "3.4" in ozet
    assert "base64" not in ozet and "image" not in ozet


def test_yonlendir_parses_the_model_decision():
    gw = Mock()
    gw.sor.return_value = Yanit(
        icerik='{"karar":"acil_yukselt","gerekce":"araç devrildi","guven":0.91}')
    k = yonlendir(gw, [_g(0.0, kisi_sayisi=1)], acik_epizot_var=False)
    assert k.karar == "acil_yukselt" and k.guven == 0.91
    assert gw.sor.call_args.args[0] == "router"


def test_unparseable_response_degrades_to_yoksay_not_a_crash():
    gw = Mock()
    gw.sor.return_value = Yanit(icerik="model bugün konuşmuyor")
    assert yonlendir(gw, [_g(0.0)], acik_epizot_var=False).karar == "yoksay"
```

The third test matters more than it looks: a router that raises on bad JSON takes the whole run down on one malformed response.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gozcu.agents'`

- [ ] **Step 3: Implement `gozcu/agents/router.py`**

```python
import json

from gozcu.models import Gozlem, RouterKarari

SISTEM = """Sen bir fabrika güvenlik kontrol odasının yönlendiricisisin.
Sana 10 saniyelik bir pencerenin sinyal özeti verilir. Görüntü görmezsin.
Görevin: bu pencere dikkat gerektiriyor mu, gerekiyorsa kime gitmeli.

Kararlar:
- yoksay: olağan hareket, ilgilenmeye değmez
- gorsel_incele: bir şey var ama ne olduğu sinyalden anlaşılmıyor
- epizot_ac: yeni bir olay başlıyor
- epizot_guncelle: açık olay devam ediyor
- epizot_kapat: açık olay sonuçlandı
- acil_yukselt: can güvenliği riski, operatör derhal haberdar edilmeli

Sadece JSON döndür."""


def _mmss(ts: float) -> str:
    return f"{int(ts) // 60:02d}:{int(ts) % 60:02d}"


def pencere_ozeti(pencere: list[Gozlem]) -> str:
    satirlar = []
    for g in pencere:
        s = g.sinyaller
        parcalar = [f"kişi={s.kisi_sayisi}"]
        if s.hizlar:
            parcalar.append("hızlar=" + ",".join(
                f"{tid}:{h:.1f}" for tid, h in s.hizlar.items()))
        if s.kaybolan_trackler:
            parcalar.append(f"kaybolan={s.kaybolan_trackler}")
        if s.toplanma:
            parcalar.append("toplanma")
        satirlar.append(f"{_mmss(g.ts)} " + " ".join(parcalar))
    return "\n".join(satirlar)


def yonlendir(gw, pencere: list[Gozlem],
              acik_epizot_var: bool) -> RouterKarari:
    durum = "Açık bir olay var." if acik_epizot_var else "Açık olay yok."
    yanit = gw.sor("router", [
        {"role": "system", "content": SISTEM},
        {"role": "user", "content": f"{durum}\n\n{pencere_ozeti(pencere)}"},
    ], sema=RouterKarari)

    try:
        return RouterKarari(**json.loads(yanit.icerik))
    except Exception:  # noqa: BLE001 — a bad decision must never stop the run
        return RouterKarari(karar="yoksay",
                            gerekce="yönlendirici yanıtı okunamadı",
                            guven=0.0)
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/test_router.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add gozcu/agents/__init__.py gozcu/agents/router.py tests/test_router.py
git commit -m "feat: router agent over windowed signal digests"
```

---

## Task 6: Synthesizer — `gozcu/agents/synthesizer.py`

**Owner:** `uvyscengiz` · 24 Ağustos · Breaks frame independence. Spec §3 ④.

**Files:**
- Create: `gozcu/agents/synthesizer.py`
- Test: `tests/test_synthesizer.py`

**Interfaces:**
- Consumes: `Gateway.sor`, `Store`, `Gozlem`, `Yorum`, `Epizot`.
- Produces: `sentezle(gw, store, pencere: list[Gozlem], yorumlar: list[Yorum]) -> Epizot`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_synthesizer.py
from unittest.mock import Mock

from gozcu.agents.synthesizer import sentezle
from gozcu.gateway import Yanit
from gozcu.models import Gozlem, Sinyaller, Yorum
from gozcu.store import Store

YANIT = ('{"faz":"gelisim","ozet_tr":"İstif aracı devrildi, yerde hareketsiz '
         'kişi var.","katilimcilar":["istif aracı","personel"],'
         '"on_risk":"Kritik"}')


def test_sentezle_merges_a_window_into_one_episode():
    gw = Mock(); gw.sor.return_value = Yanit(icerik=YANIT)
    store = Store(":memory:")
    pencere = [Gozlem(ts=float(t), sinyaller=Sinyaller(kisi_sayisi=1))
               for t in range(10)]
    yorumlar = [Yorum(gozlem_ts=3.0, aciklama="araç yan yattı", model="m")]

    e = sentezle(gw, store, pencere, yorumlar)

    assert e.baslangic_ts == 0.0 and e.bitis_ts == 9.0
    assert e.on_risk == "Kritik" and e.faz == "gelisim"
    assert len(store.epizotlar()) == 1


def test_sentezle_uses_the_fast_tier_not_the_large_one():
    gw = Mock(); gw.sor.return_value = Yanit(icerik=YANIT)
    sentezle(gw, Store(":memory:"),
             [Gozlem(ts=0.0)], [])
    assert gw.sor.call_args.args[0] == "hizli"


def test_sentezle_records_a_handoff_from_the_synthesizer():
    gw = Mock(); gw.sor.return_value = Yanit(icerik=YANIT)
    store = Store(":memory:")
    sentezle(gw, store, [Gozlem(ts=0.0)], [])
    assert store.devirler()[-1].kaynak_ajan == "sentezleyici"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_synthesizer.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `gozcu/agents/synthesizer.py`**

```python
import json

from pydantic import BaseModel, Field

from gozcu.agents.router import _mmss
from gozcu.models import Devir, Epizot, Gozlem, RiskSeviyesi, Yorum

SISTEM = """Sen bir fabrika kontrol odasının kâtibisin. Sana bir zaman
aralığındaki gözlemler ve görsel yorumlar verilir. Bunları TEK BİR OLAY
halinde birleştir.

Kurallar:
- Olayın hangi fazda olduğunu belirt: baslangic, gelisim, sonuc
- Özet Türkçe, kısa cümlelerle, saha terminolojisiyle yazılır
- Görmediğin bir şeyi yazma. Emin değilsen "olası" de.
- Ön riski şu dördünden biri olarak ver: Düşük, Orta, Yüksek, Kritik

Sadece JSON döndür."""


class _Sentez(BaseModel):
    faz: str
    ozet_tr: str = Field(max_length=600)
    katilimcilar: list[str] = Field(default_factory=list)
    on_risk: RiskSeviyesi


def sentezle(gw, store, pencere: list[Gozlem],
             yorumlar: list[Yorum]) -> Epizot:
    satirlar = [f"{_mmss(g.ts)} kişi={g.sinyaller.kisi_sayisi} "
                f"hızlar={g.sinyaller.hizlar or '-'}" for g in pencere]
    satirlar += [f"{_mmss(y.gozlem_ts)} GÖRSEL: {y.aciklama}" for y in yorumlar]

    yanit = gw.sor("hizli", [
        {"role": "system", "content": SISTEM},
        {"role": "user", "content": "\n".join(satirlar)},
    ], sema=_Sentez)

    try:
        s = _Sentez(**json.loads(yanit.icerik))
    except Exception:  # noqa: BLE001
        s = _Sentez(faz="gelisim",
                    ozet_tr="Sentez üretilemedi; ham gözlemler kayıtlı.",
                    on_risk="Orta")

    epizot = Epizot(baslangic_ts=pencere[0].ts,
                    bitis_ts=pencere[-1].ts,
                    faz=s.faz if s.faz in ("baslangic", "gelisim", "sonuc")
                    else "gelisim",
                    ozet_tr=s.ozet_tr,
                    katilimcilar=s.katilimcilar,
                    on_risk=s.on_risk)
    epizot.id = store.epizot_ac(epizot)

    store.kaydet_devir(Devir(ts=epizot.baslangic_ts,
                             kaynak_ajan="sentezleyici",
                             hedef_ajan="risk_analisti",
                             neden=f"epizot {epizot.id} oluşturuldu",
                             guven=0.8,
                             payload_ref=f"epizot:{epizot.id}"))
    return epizot
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/test_synthesizer.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add gozcu/agents/synthesizer.py tests/test_synthesizer.py
git commit -m "feat: synthesizer turning observation windows into episodes"
```

---

## Task 7: Episodic memory — `gozcu/memory.py`

**Owner:** `uvyscengiz` · 25 Ağustos

Brute-force cosine over a few hundred vectors. No vector database.

**Files:**
- Create: `gozcu/memory.py`
- Test: `tests/test_memory.py`

**Interfaces:**
- Consumes: `Store`, `Gateway`, `Epizot`.
- Produces:
  - `epizodu_gom(gw, store, epizot: Epizot) -> None`
  - `zaman_cizelgesi_ara(gw, store, sorgu: str, ust_k: int = 5) -> list[Epizot]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory.py
from unittest.mock import Mock

from gozcu.memory import epizodu_gom, zaman_cizelgesi_ara
from gozcu.models import Epizot
from gozcu.store import Store


def _epizot(ozet, risk="Orta"):
    return Epizot(baslangic_ts=0.0, faz="sonuc", ozet_tr=ozet, on_risk=risk)


def _gw(vektorler, sira=None):
    gw = Mock()
    gw.goem.side_effect = vektorler
    gw.yeniden_sirala.return_value = sira if sira is not None else []
    return gw


def test_search_ranks_the_semantically_closest_episode_first():
    store = Store(":memory:")
    gw = _gw(vektorler=[[1.0, 0.0], [0.0, 1.0], [0.99, 0.14]])
    for ozet in ("istif aracı devrildi", "personel mola verdi"):
        e = _epizot(ozet); e.id = store.epizot_ac(e); epizodu_gom(gw, store, e)

    gw.yeniden_sirala.side_effect = lambda s, adaylar: adaylar
    sonuc = zaman_cizelgesi_ara(gw, store, "araç devrilmesi")
    assert sonuc[0].ozet_tr == "istif aracı devrildi"


def test_search_returns_empty_when_nothing_is_stored():
    gw = Mock()
    assert zaman_cizelgesi_ara(gw, Store(":memory:"), "herhangi bir şey") == []
    gw.goem.assert_not_called()
```

The second test guards the demo: an empty archive must return nothing, not raise inside beat 5.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_memory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gozcu.memory'`

- [ ] **Step 3: Add embedding and rerank helpers to `gozcu/gateway.py`**

```python
    def goem(self, metin: str) -> list[float]:
        r = self._client.embeddings.create(model=MODELLER["embed"], input=metin)
        return list(r.data[0].embedding)

    def yeniden_sirala(self, sorgu: str, adaylar: list[str]) -> list[int]:
        """Return candidate indices, best first."""
        istek = "\n".join(f"[{i}] {m}" for i, m in enumerate(adaylar))
        yanit = self.sor("rerank", [
            {"role": "user",
             "content": f"Sorgu: {sorgu}\n\nAdaylar:\n{istek}\n\n"
                        "En alakalıdan en alakasıza indeksleri virgülle sırala."},
        ])
        try:
            return [int(p) for p in yanit.icerik.replace(" ", "").split(",")
                    if p.isdigit() and int(p) < len(adaylar)]
        except Exception:  # noqa: BLE001
            return list(range(len(adaylar)))
```

Add `"rerank"` to `MODELLER` usage — it is already in the dict from Task 3.

- [ ] **Step 4: Implement `gozcu/memory.py`**

```python
import numpy as np

from gozcu.models import Epizot

ADAY_K = 20


def epizodu_gom(gw, store, epizot: Epizot) -> None:
    if epizot.id is None:
        raise ValueError("epizot önce kaydedilmeli")
    metin = f"{epizot.ozet_tr} | katılımcılar: {', '.join(epizot.katilimcilar)}"
    store.kaydet_embedding(epizot.id, gw.goem(metin))


def zaman_cizelgesi_ara(gw, store, sorgu: str, ust_k: int = 5) -> list[Epizot]:
    kayitli = store.embeddingler()
    if not kayitli:
        return []

    q = np.asarray(gw.goem(sorgu), dtype=float)
    ids = [i for i, _ in kayitli]
    M = np.asarray([v for _, v in kayitli], dtype=float)

    normlar = np.linalg.norm(M, axis=1) * np.linalg.norm(q)
    normlar[normlar == 0] = 1e-9
    skorlar = (M @ q) / normlar

    aday_ids = [ids[i] for i in np.argsort(-skorlar)[:ADAY_K]]
    hepsi = {e.id: e for e in store.epizotlar()}
    adaylar = [hepsi[i] for i in aday_ids if i in hepsi]
    if not adaylar:
        return []

    sira = gw.yeniden_sirala(sorgu, [e.ozet_tr for e in adaylar])
    sirali = [adaylar[i] for i in sira if i < len(adaylar)] or adaylar
    return sirali[:ust_k]
```

- [ ] **Step 5: Run the tests and watch them pass**

Run: `uv run pytest tests/test_memory.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add gozcu/memory.py gozcu/gateway.py tests/test_memory.py
git commit -m "feat: episodic memory search via embedding and rerank"
```

---

## Task 8: Mock field systems — `gozcu/tools/`

**Owner:** `Xana-bit` · 25 Ağustos · Scored twice: Functionality and Architecture.

**Files:**
- Create: `gozcu/tools/__init__.py`, `gozcu/tools/saha.py`, `gozcu/tools/registry.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Consumes: `Store`, `AksiyonKaydi`, fixtures from Task 9.
- Produces:
  - Seven callables in `saha.py` with the exact names below
  - `ARAC_SEMALARI: list[dict]` — OpenAI tool-schema list for `Gateway.sor(araclar=...)`
  - `cagir(store, tool_adi: str, parametreler: dict, kim="ajan") -> dict`
  - `ONAY_GEREKTIREN: set[str] = {"uretim_hatti_durdur"}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools.py
import pytest

from gozcu.store import Store
from gozcu.tools.registry import ARAC_SEMALARI, ONAY_GEREKTIREN, cagir


def test_every_call_lands_in_the_action_ledger():
    store = Store(":memory:")
    cagir(store, "saha_telsiz_cagrisi",
          {"birim": "vardiya amiri", "mesaj": "B-Hattı'na gel"})
    kayit = store.aksiyonlar()[0]
    assert kayit.tool_adi == "saha_telsiz_cagrisi" and kayit.kim == "ajan"
    assert kayit.onay_durumu == "gerekmiyor"


def test_line_stop_waits_for_operator_approval():
    store = Store(":memory:")
    sonuc = cagir(store, "uretim_hatti_durdur",
                  {"hat_id": "B", "gerekce": "devrilme"})
    assert sonuc["onay_bekliyor"] is True
    assert store.aksiyonlar()[0].onay_durumu == "bekliyor"
    assert "uretim_hatti_durdur" in ONAY_GEREKTIREN


def test_shift_query_returns_certifications_so_the_agent_can_reason():
    kisiler = cagir(Store(":memory:"), "vardiya_personel_sorgula",
                    {"bolge": "B-Hattı", "zaman": "03:12"})["personel"]
    assert kisiler and all("yetkiler" in k for k in kisiler)


def test_equipment_history_exposes_overdue_maintenance():
    gecmis = cagir(Store(":memory:"), "ekipman_gecmisi_sorgula",
                   {"ekipman_id": "IST-04"})
    assert gecmis["geciken_bakim_ay"] >= 4


def test_unknown_tool_raises_rather_than_silently_succeeding():
    with pytest.raises(KeyError):
        cagir(Store(":memory:"), "nukleer_firlat", {})


def test_schemas_cover_every_registered_tool():
    from gozcu.tools.registry import ARACLAR
    assert {s["function"]["name"] for s in ARAC_SEMALARI} == set(ARACLAR)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gozcu.tools'`

- [ ] **Step 3: Implement `gozcu/tools/saha.py`**

Fixtures come from Task 9; this module reads them.

```python
import json
from pathlib import Path

FIXTURE = Path(__file__).parent.parent / "fixtures"
_sayac = {"cagri": 1000, "talep": 2000, "alarm": 3000, "kayit": 4000}


def _no(tur: str) -> str:
    _sayac[tur] += 1
    return f"2026-{_sayac[tur]}"


def _yukle(ad: str) -> dict:
    return json.loads((FIXTURE / f"{ad}.json").read_text(encoding="utf-8"))


def saha_telsiz_cagrisi(birim: str, mesaj: str) -> dict:
    return {"cagri_id": _no("cagri"), "birim": birim, "durum": "iletildi",
            "yanit_bekleniyor": True}


def saglik_ekibi_cagir(konum: str, aciliyet: str, aciklama: str = "") -> dict:
    return {"talep_id": _no("talep"), "konum": konum,
            "ekip": "Revir-2", "tahmini_varis_dk": 2 if aciliyet == "kritik" else 8}


def saha_alarmi(bolge: str, seviye: str) -> dict:
    return {"alarm_id": _no("alarm"), "etkilenen_bolge": bolge,
            "siren_durumu": "aktif", "seviye": seviye}


def isg_olay_kaydi_ac(epizot_id: int, siniflandirma: str,
                      aciklama: str = "") -> dict:
    return {"kayit_no": _no("kayit"), "siniflandirma": siniflandirma,
            "durum": "acik", "epizot_id": epizot_id}


def uretim_hatti_durdur(hat_id: str, gerekce: str) -> dict:
    return {"hat_id": hat_id, "gerekce": gerekce, "onay_bekliyor": True}


def vardiya_personel_sorgula(bolge: str, zaman: str) -> dict:
    veri = _yukle("personel")
    return {"bolge": bolge, "zaman": zaman,
            "personel": [k for k in veri["personel"] if k["bolge"] == bolge]}


def ekipman_gecmisi_sorgula(ekipman_id: str) -> dict:
    veri = _yukle("ekipman")
    kayit = veri["ekipman"].get(ekipman_id)
    if kayit is None:
        return {"ekipman_id": ekipman_id, "bulunamadi": True}
    return {"ekipman_id": ekipman_id, **kayit}
```

- [ ] **Step 4: Implement `gozcu/tools/registry.py`**

```python
import time

from gozcu.models import AksiyonKaydi
from gozcu.tools import saha

ARACLAR = {
    "saha_telsiz_cagrisi": saha.saha_telsiz_cagrisi,
    "saglik_ekibi_cagir": saha.saglik_ekibi_cagir,
    "saha_alarmi": saha.saha_alarmi,
    "isg_olay_kaydi_ac": saha.isg_olay_kaydi_ac,
    "uretim_hatti_durdur": saha.uretim_hatti_durdur,
    "vardiya_personel_sorgula": saha.vardiya_personel_sorgula,
    "ekipman_gecmisi_sorgula": saha.ekipman_gecmisi_sorgula,
}

ONAY_GEREKTIREN = {"uretim_hatti_durdur"}

_ACIKLAMA = {
    "saha_telsiz_cagrisi": ("Bir saha birimini telsizle arar.",
                            {"birim": "str", "mesaj": "str"}),
    "saglik_ekibi_cagir": ("Revir sağlık ekibini olay yerine çağırır.",
                           {"konum": "str", "aciliyet": "str",
                            "aciklama": "str"}),
    "saha_alarmi": ("Bölgesel sesli alarmı çalıştırır.",
                    {"bolge": "str", "seviye": "str"}),
    "isg_olay_kaydi_ac": ("İş güvenliği olay kaydı açar.",
                          {"epizot_id": "integer", "siniflandirma": "str",
                           "aciklama": "str"}),
    "uretim_hatti_durdur": ("Üretim hattını durdurur. Operatör onayı gerekir.",
                            {"hat_id": "str", "gerekce": "str"}),
    "vardiya_personel_sorgula": ("Bir bölgede vardiyadaki personeli ve yetki "
                                 "belgelerini getirir.",
                                 {"bolge": "str", "zaman": "str"}),
    "ekipman_gecmisi_sorgula": ("Bir ekipmanın bakım ve arıza geçmişini getirir.",
                                {"ekipman_id": "str"}),
}

ARAC_SEMALARI = [{
    "type": "function",
    "function": {
        "name": ad,
        "description": _ACIKLAMA[ad][0],
        "parameters": {
            "type": "object",
            "properties": {p: {"type": "integer" if t == "integer" else "string"}
                           for p, t in _ACIKLAMA[ad][1].items()},
            "required": [p for p in _ACIKLAMA[ad][1]],
        },
    },
} for ad in ARACLAR]


def cagir(store, tool_adi: str, parametreler: dict, kim: str = "ajan") -> dict:
    fn = ARACLAR[tool_adi]  # KeyError on unknown tool, deliberately
    sonuc = fn(**parametreler)
    store.kaydet_aksiyon(AksiyonKaydi(
        ts=time.monotonic(), tool_adi=tool_adi, parametreler=parametreler,
        sonuc=sonuc, kim=kim,
        onay_durumu="bekliyor" if tool_adi in ONAY_GEREKTIREN else "gerekmiyor"))
    return sonuc
```

- [ ] **Step 5: Run the tests and watch them pass**

Run: `uv run pytest tests/test_tools.py -v`
Expected: 6 passed. Tests 3 and 4 need Task 9's fixtures — if Task 9 is not merged yet, write the two fixture files first from the content in Task 9 Step 3.

- [ ] **Step 6: Commit**

```bash
git add gozcu/tools tests/test_tools.py
git commit -m "feat: seven mock field-system tools with an action ledger"
```

---

## Task 9: The seeded facility world — `gozcu/fixtures/`

**Owner:** `Xana-bit` · 25 Ağustos · **Demo beats 4, 5 and 7 fail without this.**

Not decoration. Beat 5 has nothing to retrieve without prior incidents; beat 7's
root cause comes back empty without overdue maintenance. This also ships as part
of the published open dataset.

**Files:**
- Create: `gozcu/fixtures/personel.json`, `gozcu/fixtures/ekipman.json`, `gozcu/fixtures/gecmis_olaylar.json`, `gozcu/fixtures/README.md`
- Create: `gozcu/fixtures/loader.py`
- Test: `tests/test_fixtures.py`

**Interfaces:**
- Consumes: `Store`, `Epizot`, `epizodu_gom` (Task 7).
- Produces: `gecmisi_yukle(gw, store) -> int` — seeds prior incidents into the archive and embeds them; returns how many were loaded.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fixtures.py
from unittest.mock import Mock

from gozcu.fixtures.loader import gecmisi_yukle
from gozcu.store import Store
from gozcu.tools.registry import cagir


def test_the_incident_vehicle_has_overdue_brake_maintenance():
    g = cagir(Store(":memory:"), "ekipman_gecmisi_sorgula",
              {"ekipman_id": "IST-04"})
    assert g["geciken_bakim_ay"] >= 4
    assert any("fren" in b["islem"].lower() for b in g["bakim_gecmisi"])


def test_the_shift_has_a_person_without_forklift_certification():
    p = cagir(Store(":memory:"), "vardiya_personel_sorgula",
              {"bolge": "B-Hattı", "zaman": "03:12"})["personel"]
    assert any("istif_araci" not in k["yetkiler"] for k in p)


def test_prior_incidents_are_loaded_and_embedded():
    store, gw = Store(":memory:"), Mock()
    gw.goem.return_value = [0.1, 0.2, 0.3]
    n = gecmisi_yukle(gw, store)
    assert n >= 2
    assert len(store.embeddingler()) == n
    assert all(e.durum == "kapali" for e in store.epizotlar())


def test_a_prior_incident_involves_the_same_vehicle_as_the_demo():
    store, gw = Store(":memory:"), Mock()
    gw.goem.return_value = [0.1]
    gecmisi_yukle(gw, store)
    assert any("IST-04" in e.ozet_tr or "IST-04" in e.katilimcilar
               for e in store.epizotlar())
```

The fourth test is the one beat 5 depends on: the operator asks whether this
vehicle has been involved before, and the archive must have an answer.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_fixtures.py -v`
Expected: FAIL — fixtures missing.

- [ ] **Step 3: Write the fixture files**

`gozcu/fixtures/personel.json`:

```json
{
  "personel": [
    {"ad": "M.K.", "bolge": "B-Hattı", "gorev": "istif aracı operatörü",
     "yetkiler": ["istif_araci", "yuksekte_calisma"], "vardiya": "gece"},
    {"ad": "S.A.", "bolge": "B-Hattı", "gorev": "sevkiyat personeli",
     "yetkiler": [], "vardiya": "gece"},
    {"ad": "H.Y.", "bolge": "B-Hattı", "gorev": "vardiya amiri",
     "yetkiler": ["isg_sorumlusu", "istif_araci"], "vardiya": "gece"},
    {"ad": "E.D.", "bolge": "C-Hattı", "gorev": "bakım teknisyeni",
     "yetkiler": ["elektrik", "mekanik"], "vardiya": "gece"}
  ]
}
```

`gozcu/fixtures/ekipman.json`:

```json
{
  "ekipman": {
    "IST-04": {
      "tur": "istif aracı", "model": "2019 dizel forklift",
      "bolge": "B-Hattı", "durum": "serviste",
      "geciken_bakim_ay": 4,
      "bakim_gecmisi": [
        {"tarih": "2026-04-11", "islem": "Fren balata kontrolü", "sonuc": "uyarı verildi"},
        {"tarih": "2026-01-08", "islem": "Periyodik bakım", "sonuc": "tamam"}
      ],
      "ariza_kayitlari": [
        {"tarih": "2026-06-02", "aciklama": "Fren mesafesi uzun, operatör bildirimi"}
      ]
    },
    "IST-07": {
      "tur": "istif aracı", "model": "2022 elektrikli forklift",
      "bolge": "C-Hattı", "durum": "serviste", "geciken_bakim_ay": 0,
      "bakim_gecmisi": [{"tarih": "2026-08-01", "islem": "Periyodik bakım", "sonuc": "tamam"}],
      "ariza_kayitlari": []
    }
  }
}
```

`gozcu/fixtures/gecmis_olaylar.json`:

```json
{
  "olaylar": [
    {"baslangic_ts": 0.0, "bitis_ts": 42.0, "faz": "sonuc", "on_risk": "Orta",
     "katilimcilar": ["IST-04", "personel"],
     "ozet_tr": "12 Ağustos gecesi B-Hattı'nda IST-04 istif aracının fren mesafesi uzadı, operatör raf hizasında zor durdu. Yaralanma olmadı, olay kaydı açıldı."},
    {"baslangic_ts": 0.0, "bitis_ts": 25.0, "faz": "sonuc", "on_risk": "Düşük",
     "katilimcilar": ["IST-07"],
     "ozet_tr": "3 Ağustos'ta C-Hattı'nda IST-07 istif aracı yükü hatalı istifledi, yük kaymadı, uyarı yapıldı."},
    {"baslangic_ts": 0.0, "bitis_ts": 60.0, "faz": "sonuc", "on_risk": "Yüksek",
     "katilimcilar": ["personel"],
     "ozet_tr": "28 Temmuz'da B-Hattı sevkiyat alanında kask takmayan personel tespit edildi, vardiya amiri uyardı."}
  ]
}
```

`gozcu/fixtures/README.md` documents that this is synthetic data invented for
the competition demo, describing a fictional facility — no real person,
equipment or incident is represented. State this plainly; it goes in the public
dataset.

- [ ] **Step 4: Implement `gozcu/fixtures/loader.py`**

```python
import json
from pathlib import Path

from gozcu.memory import epizodu_gom
from gozcu.models import Epizot

FIXTURE = Path(__file__).parent


def gecmisi_yukle(gw, store) -> int:
    veri = json.loads((FIXTURE / "gecmis_olaylar.json").read_text(encoding="utf-8"))
    n = 0
    for kayit in veri["olaylar"]:
        e = Epizot(**kayit, durum="kapali")
        e.id = store.epizot_ac(e)
        epizodu_gom(gw, store, e)
        n += 1
    return n
```

- [ ] **Step 5: Run the tests and watch them pass**

Run: `uv run pytest tests/test_fixtures.py tests/test_tools.py -v`
Expected: 4 + 6 passed.

- [ ] **Step 6: Commit**

```bash
git add gozcu/fixtures tests/test_fixtures.py
git commit -m "feat: seeded facility world — personnel, equipment, prior incidents"
```

---

## Task 10: Risk Analisti — `gozcu/agents/risk.py`

**Owner:** `uvyscengiz` · 25 Ağustos

Every candidate action must name a real tool. A recommendation the system cannot
execute is a sentence, and sentences are what §5 of the spec exists to avoid.

**Files:**
- Create: `gozcu/agents/risk.py`
- Test: `tests/test_risk.py`

**Interfaces:**
- Consumes: `Gateway`, `Store`, `Epizot`, `zaman_cizelgesi_ara` (Task 7), `ARACLAR` (Task 8).
- Produces: `risk_analiz_et(gw, store, epizot: Epizot) -> RiskDegerlendirme`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_risk.py
from unittest.mock import Mock, patch

from gozcu.agents.risk import risk_analiz_et
from gozcu.gateway import Yanit
from gozcu.models import Epizot
from gozcu.store import Store

YANIT = ('{"seviye":"Kritik","gerekce_tr":"Yerde hareketsiz kişi var ve '
         'aracın fren bakımı gecikmiş.","onlenebilir":true,'
         '"aday_aksiyonlar":[{"aciklama_tr":"Sağlık ekibini çağır",'
         '"tool_adi":"saglik_ekibi_cagir",'
         '"parametreler":{"konum":"B-Hattı","aciliyet":"kritik"}}]}')


def _epizot(store):
    e = Epizot(baslangic_ts=0.0, faz="gelisim", ozet_tr="araç devrildi",
               on_risk="Yüksek")
    e.id = store.epizot_ac(e)
    return e


def test_candidate_actions_map_to_real_registered_tools():
    from gozcu.tools.registry import ARACLAR
    gw = Mock(); gw.sor.return_value = Yanit(icerik=YANIT)
    store = Store(":memory:")
    with patch("gozcu.agents.risk.zaman_cizelgesi_ara", return_value=[]):
        r = risk_analiz_et(gw, store, _epizot(store))
    assert r.aday_aksiyonlar
    assert all(a.tool_adi in ARACLAR for a in r.aday_aksiyonlar)


def test_invented_tool_names_are_dropped_not_passed_through():
    kotu = YANIT.replace("saglik_ekibi_cagir", "helikopter_gonder")
    gw = Mock(); gw.sor.return_value = Yanit(icerik=kotu)
    store = Store(":memory:")
    with patch("gozcu.agents.risk.zaman_cizelgesi_ara", return_value=[]):
        r = risk_analiz_et(gw, store, _epizot(store))
    assert r.aday_aksiyonlar == []


def test_analysis_consults_the_archive_before_deciding():
    gw = Mock(); gw.sor.return_value = Yanit(icerik=YANIT)
    store = Store(":memory:")
    with patch("gozcu.agents.risk.zaman_cizelgesi_ara",
               return_value=[]) as ara:
        risk_analiz_et(gw, store, _epizot(store))
    ara.assert_called_once()


def test_assessment_is_persisted_with_a_handoff():
    gw = Mock(); gw.sor.return_value = Yanit(icerik=YANIT)
    store = Store(":memory:")
    with patch("gozcu.agents.risk.zaman_cizelgesi_ara", return_value=[]):
        risk_analiz_et(gw, store, _epizot(store))
    assert len(store.riskler()) == 1
    assert store.devirler()[-1].hedef_ajan == "nobetci"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_risk.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `gozcu/agents/risk.py`**

```python
import json

from gozcu.memory import zaman_cizelgesi_ara
from gozcu.models import AdayAksiyon, Devir, Epizot, RiskDegerlendirme
from gozcu.tools.registry import ARACLAR

SISTEM = """Sen bir savunma sanayi üretim tesisinin iş güvenliği uzmanısın.
Sana bir olay ve arşivden gelen benzer geçmiş olaylar verilir.

Görevin:
- Risk seviyesini belirle: Düşük, Orta, Yüksek, Kritik
- Gerekçeni Türkçe, kısa cümlelerle yaz. Kamera verisine dayan.
- Kesin hüküm verme; "olası", "muhtemelen" gibi ifadeler kullan
- Önlenebilir olup olmadığını söyle
- Her aksiyon önerisini SADECE şu araçlardan birine bağla:
{araclar}

Var olmayan bir araç adı uydurma. Sadece JSON döndür."""


def risk_analiz_et(gw, store, epizot: Epizot) -> RiskDegerlendirme:
    gecmis = zaman_cizelgesi_ara(
        gw, store, f"{epizot.ozet_tr} {' '.join(epizot.katilimcilar)}")
    gecmis_metin = "\n".join(f"- {e.ozet_tr}" for e in gecmis) or "- (kayıt yok)"
    duzeltmeler = store.duzeltmeler(epizot.id) if epizot.id else []
    duzeltme_metin = "\n".join(
        f"- OPERATÖR DÜZELTMESİ: {d.alan}: {d.eski} → {d.yeni}"
        for d in duzeltmeler)

    yanit = gw.sor("ana", [
        {"role": "system",
         "content": SISTEM.format(araclar="\n".join(f"- {a}" for a in ARACLAR))},
        {"role": "user",
         "content": f"OLAY: {epizot.ozet_tr}\nÖN RİSK: {epizot.on_risk}\n"
                    f"{duzeltme_metin}\n\nARŞİV:\n{gecmis_metin}"},
    ], sema=RiskDegerlendirme)

    try:
        ham = json.loads(yanit.icerik)
        aksiyonlar = [AdayAksiyon(**a) for a in ham.get("aday_aksiyonlar", [])]
        seviye, gerekce = ham["seviye"], ham["gerekce_tr"]
        onlenebilir = bool(ham.get("onlenebilir", False))
    except Exception:  # noqa: BLE001
        seviye, gerekce, onlenebilir, aksiyonlar = (
            epizot.on_risk, "Risk analizi üretilemedi; ön risk korundu.",
            False, [])

    # Hallucinated tool names are dropped, never forwarded to the supervisor.
    aksiyonlar = [a for a in aksiyonlar if a.tool_adi in ARACLAR]

    degerlendirme = RiskDegerlendirme(
        epizot_id=epizot.id, seviye=seviye, gerekce_tr=gerekce,
        onlenebilir=onlenebilir, aday_aksiyonlar=aksiyonlar)
    degerlendirme.id = store.kaydet_risk(degerlendirme)

    store.kaydet_devir(Devir(ts=epizot.baslangic_ts,
                             kaynak_ajan="risk_analisti", hedef_ajan="nobetci",
                             neden=f"risk: {seviye}", guven=0.85,
                             payload_ref=f"risk:{degerlendirme.id}"))
    return degerlendirme
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/test_risk.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add gozcu/agents/risk.py tests/test_risk.py
git commit -m "feat: risk analyst grounding every recommendation in a real tool"
```

---

## Task 11: Raportör — `gozcu/agents/raportor.py`

**Owner:** `beyzaalive` · 25 Ağustos · Demo beat 7.

**Files:**
- Create: `gozcu/agents/raportor.py`
- Test: `tests/test_raportor.py`

**Interfaces:**
- Consumes: `Gateway`, `Store`.
- Produces: `KokNedenRaporu` (Pydantic) and `kok_neden_raporu_uret(gw, store) -> KokNedenRaporu`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_raportor.py
from unittest.mock import Mock

from gozcu.agents.raportor import kok_neden_raporu_uret
from gozcu.gateway import Yanit
from gozcu.models import AksiyonKaydi, Duzeltme, Epizot
from gozcu.store import Store

YANIT = ('{"ne_oldu":"B-Hattı sevkiyat alanında yük düştü.",'
         '"muhtemel_kok_neden":"Fren bakımının 4 ay gecikmiş olması.",'
         '"alinan_aksiyonlar":["İSG kaydı açıldı"],'
         '"onleme_onerileri":["Bakım periyodu denetlensin"],'
         '"guven_sinirlari":"Kamera görüntüsü fren durumunu doğrudan gösteremez."}')


def _hazir_store():
    store = Store(":memory:")
    e = Epizot(baslangic_ts=12.0, faz="sonuc", ozet_tr="yük düştü",
               on_risk="Yüksek", durum="kapali")
    e.id = store.epizot_ac(e)
    store.kaydet_aksiyon(AksiyonKaydi(ts=1.0, tool_adi="isg_olay_kaydi_ac",
                                      parametreler={}, sonuc={"kayit_no": "x"},
                                      kim="ajan", onay_durumu="gerekmiyor"))
    return store, e


def test_report_always_states_its_confidence_limits():
    gw = Mock(); gw.sor.return_value = Yanit(icerik=YANIT)
    store, _ = _hazir_store()
    r = kok_neden_raporu_uret(gw, store)
    assert r.guven_sinirlari.strip()


def test_report_prompt_includes_the_action_ledger():
    gw = Mock(); gw.sor.return_value = Yanit(icerik=YANIT)
    store, _ = _hazir_store()
    kok_neden_raporu_uret(gw, store)
    istem = gw.sor.call_args.args[1][-1]["content"]
    assert "isg_olay_kaydi_ac" in istem


def test_operator_corrections_reach_the_report_prompt():
    gw = Mock(); gw.sor.return_value = Yanit(icerik=YANIT)
    store, e = _hazir_store()
    store.kaydet_duzeltme(Duzeltme(ts=1.0, epizot_id=e.id, alan="olay_turu",
                                   eski="araç devrildi", yeni="yük düştü",
                                   gerekce="operatör gözlemi"))
    kok_neden_raporu_uret(gw, store)
    istem = gw.sor.call_args.args[1][-1]["content"]
    assert "yük düştü" in istem and "araç devrildi" in istem
```

The third test is beat 3's guarantee: a correction that does not reach the final
report is a correction that silently did nothing.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_raportor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `gozcu/agents/raportor.py`**

```python
import json

from pydantic import BaseModel, ConfigDict, Field

SISTEM = """Sen bir savunma sanayi üretim tesisinin olay inceleme raportörüsün.
Sana olay zinciri, risk değerlendirmeleri, operatör düzeltmeleri ve alınan
aksiyonlar verilir. Bir kök neden raporu yaz.

Kurallar:
- Türkçe, kısa cümleler, saha terminolojisi
- Kesin hüküm verme. Kamera verisine dayanan kalibre edilmiş tahmin ver.
- Operatör düzeltmesi varsa DÜZELTİLMİŞ hâli esas al
- guven_sinirlari alanında neyi bilemeyeceğini açıkça yaz

Sadece JSON döndür."""


class KokNedenRaporu(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ne_oldu: str = Field(max_length=800)
    muhtemel_kok_neden: str = Field(max_length=600)
    alinan_aksiyonlar: list[str] = Field(default_factory=list)
    onleme_onerileri: list[str] = Field(default_factory=list)
    guven_sinirlari: str = Field(max_length=400)


def kok_neden_raporu_uret(gw, store) -> KokNedenRaporu:
    bolumler = ["OLAY ZİNCİRİ:"]
    bolumler += [f"- {e.baslangic_ts:.0f}s [{e.faz}] {e.ozet_tr}"
                 for e in store.epizotlar()]

    bolumler.append("\nRİSK DEĞERLENDİRMELERİ:")
    bolumler += [f"- {r.seviye}: {r.gerekce_tr}" for r in store.riskler()]

    bolumler.append("\nOPERATÖR DÜZELTMELERİ:")
    duzeltmeler = [d for e in store.epizotlar() if e.id
                   for d in store.duzeltmeler(e.id)]
    bolumler += [f"- {d.alan}: '{d.eski}' → '{d.yeni}' ({d.gerekce})"
                 for d in duzeltmeler] or ["- (yok)"]

    bolumler.append("\nAKSİYON DEFTERİ:")
    bolumler += [f"- {a.tool_adi}({a.parametreler}) → {a.sonuc} "
                 f"[{a.onay_durumu}]" for a in store.aksiyonlar()] or ["- (yok)"]

    bolumler.append("\nDİYALOG:")
    bolumler += [f"- {s.rol}: {s.metin}" for s in store.diyalog()] or ["- (yok)"]

    yanit = gw.sor("ana", [
        {"role": "system", "content": SISTEM},
        {"role": "user", "content": "\n".join(bolumler)},
    ], sema=KokNedenRaporu)

    try:
        return KokNedenRaporu(**json.loads(yanit.icerik))
    except Exception:  # noqa: BLE001
        return KokNedenRaporu(
            ne_oldu="Rapor üretilemedi; ham olay zinciri kayıtlıdır.",
            muhtemel_kok_neden="Belirlenemedi.",
            guven_sinirlari="Rapor modeli yanıt vermedi.")
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/test_raportor.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add gozcu/agents/raportor.py tests/test_raportor.py
git commit -m "feat: root-cause reporter honouring corrections and stating limits"
```

---

## Task 12: Guard wrapper — `gozcu/guard.py`

**Owner:** `beyzaalive` · 25 Ağustos

Answers the şartname's ethics clause: output must be fair, inclusive and free of
bias. Must never block a critical safety alert — a guard that swallows "call the
medics" is worse than no guard.

**Files:**
- Create: `gozcu/guard.py`
- Test: `tests/test_guard.py`

**Interfaces:**
- Consumes: `Gateway`.
- Produces: `denetle(gw, metin: str, kritik: bool = False) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_guard.py
from unittest.mock import Mock

from gozcu.gateway import Yanit
from gozcu.guard import denetle


def test_clean_text_passes_through_unchanged():
    gw = Mock(); gw.sor.return_value = Yanit(icerik="uygun")
    metin = "Sağlık ekibi 2 dakikaya varıyor."
    assert denetle(gw, metin) == metin


def test_flagged_text_is_replaced_with_a_neutral_notice():
    gw = Mock(); gw.sor.return_value = Yanit(icerik="uygunsuz")
    assert denetle(gw, "uygunsuz bir ifade") != "uygunsuz bir ifade"


def test_critical_alerts_are_never_blocked():
    gw = Mock(); gw.sor.return_value = Yanit(icerik="uygunsuz")
    metin = "KRİTİK: yerde hareketsiz kişi var."
    assert denetle(gw, metin, kritik=True) == metin
    gw.sor.assert_not_called()


def test_guard_failure_lets_text_through_rather_than_silencing_the_system():
    gw = Mock(); gw.sor.side_effect = RuntimeError("guard down")
    metin = "Vardiya amirine bildirildi."
    assert denetle(gw, metin) == metin
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_guard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gozcu.guard'`

- [ ] **Step 3: Implement `gozcu/guard.py`**

```python
SISTEM = """Aşağıdaki metin bir fabrika kontrol odasında operatöre gösterilecek.
Metin ayrımcı, aşağılayıcı, kişiyi hedef alan veya yanlı bir ifade içeriyor mu?
Sadece "uygun" veya "uygunsuz" yaz."""

NOTR = "[Bu ifade uygunsuz bulundu ve gösterilmedi. Olay kaydı korunmuştur.]"


def denetle(gw, metin: str, kritik: bool = False) -> str:
    # A safety alert is never withheld. Missing an injury beats a tone violation.
    if kritik:
        return metin
    try:
        yanit = gw.sor("guard", [{"role": "system", "content": SISTEM},
                                 {"role": "user", "content": metin}])
    except Exception:  # noqa: BLE001 — fail open, never silence the system
        return metin
    return NOTR if "uygunsuz" in yanit.icerik.strip().lower() else metin
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/test_guard.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add gozcu/guard.py tests/test_guard.py
git commit -m "feat: guard pass that fails open and never blocks critical alerts"
```

---

## Task 13: Nöbetçi supervisor — `gozcu/agents/nobetci.py`

**Owner:** `uvyscengiz` · 25 Ağustos · **20% of the grade lives here.**

**Files:**
- Create: `gozcu/agents/nobetci.py`
- Test: `tests/test_nobetci.py`

**Interfaces:**
- Consumes: `Gateway`, `Store`, `ARAC_SEMALARI`/`cagir`/`ONAY_GEREKTIREN` (Task 8), `zaman_cizelgesi_ara` (Task 7), `risk_analiz_et` (Task 10), `kok_neden_raporu_uret` (Task 11), `denetle` (Task 12).
- Produces:
  - `Nobetci(gw, store)`
  - `n.yukselt(epizot: Epizot) -> str` — proactive opening, beat 1
  - `n.konus(operator_metni: str) -> str` — one dialogue turn
  - `n.bekleyen_onay() -> AksiyonKaydi | None`
  - `n.onayla(aksiyon_id: int, onay: bool) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nobetci.py
from unittest.mock import Mock, patch

from gozcu.agents.nobetci import Nobetci
from gozcu.gateway import Yanit
from gozcu.models import Epizot, RiskDegerlendirme
from gozcu.store import Store


def _kurulum(yanitlar):
    gw = Mock(); gw.sor.side_effect = yanitlar
    store = Store(":memory:")
    e = Epizot(baslangic_ts=192.0, faz="gelisim",
               ozet_tr="istif aracı devrildi, yerde hareketsiz kişi",
               on_risk="Kritik")
    e.id = store.epizot_ac(e)
    return gw, store, e


def _arac_yaniti(ad, params):
    return Yanit(arac_cagrilari=[{"id": "c1", "type": "function",
                                  "function": {"name": ad,
                                               "arguments": str(params).replace("'", '"')}}])


def test_escalation_queries_the_shift_before_speaking():
    gw, store, e = _kurulum([
        _arac_yaniti("vardiya_personel_sorgula",
                     {"bolge": "B-Hattı", "zaman": "03:12"}),
        Yanit(icerik="03:12 — B-Hattı'nda istif aracı devrildi. Risk: Kritik."),
        Yanit(icerik="uygun"),
    ])
    with patch("gozcu.agents.nobetci.risk_analiz_et",
               return_value=RiskDegerlendirme(epizot_id=e.id, seviye="Kritik",
                                              gerekce_tr="g", onlenebilir=True)):
        mesaj = Nobetci(gw, store).yukselt(e)
    cagrilanlar = [a.tool_adi for a in store.aksiyonlar()]
    assert "vardiya_personel_sorgula" in cagrilanlar
    assert "03:12" in mesaj


def test_line_stop_is_held_for_approval_and_not_executed():
    gw, store, _ = _kurulum([
        _arac_yaniti("uretim_hatti_durdur",
                     {"hat_id": "B", "gerekce": "devrilme"}),
        Yanit(icerik="B-Hattı'nı durdurmamı ister misiniz?"),
        Yanit(icerik="uygun"),
    ])
    n = Nobetci(gw, store)
    n.konus("durumu özetle")
    bekleyen = n.bekleyen_onay()
    assert bekleyen is not None and bekleyen.tool_adi == "uretim_hatti_durdur"


def test_correction_is_written_to_the_correction_table():
    gw, store, e = _kurulum([
        _arac_yaniti("gozlem_duzelt",
                     {"epizot_id": e.id if False else 1, "alan": "olay_turu",
                      "eski": "araç devrildi", "yeni": "yük düştü",
                      "gerekce": "operatör gözlemi"}),
        Yanit(icerik="Anlaşıldı, kaydı güncelledim."),
        Yanit(icerik="uygun"),
    ])
    Nobetci(gw, store).konus("araç devrilmedi, yük düştü")
    assert store.duzeltmeler(1)[0].yeni == "yük düştü"


def test_open_incident_survives_a_context_switch():
    gw, store, e = _kurulum([
        _arac_yaniti("zaman_cizelgesi_ara", {"sorgu": "IST-04 geçmiş olay"}),
        Yanit(icerik="Daha önce bir fren uyarısı var. "
                     "Bu arada B-Hattı olayı hâlâ açık."),
        Yanit(icerik="uygun"),
    ])
    with patch("gozcu.agents.nobetci.zaman_cizelgesi_ara", return_value=[]):
        cevap = Nobetci(gw, store).konus("dur, bu araçla daha önce olay olmuş muydu?")
    assert "hâlâ açık" in cevap
    assert store.acik_epizot() is not None


def test_dialogue_turns_are_recorded_both_sides():
    gw, store, _ = _kurulum([Yanit(icerik="Anlaşıldı."), Yanit(icerik="uygun")])
    Nobetci(gw, store).konus("durum nedir?")
    roller = [s.rol for s in store.diyalog()]
    assert roller == ["operator", "nobetci"]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_nobetci.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `gozcu/agents/nobetci.py`**

The supervisor's own tools (`zaman_cizelgesi_ara`, `gozlem_duzelt`,
`risk_analizi_iste`, `kok_neden_raporu_uret`) are appended to the seven field
tools, so tool selection across both kinds is one decision for the model.

```python
import json
import time

from gozcu.agents.raportor import kok_neden_raporu_uret
from gozcu.agents.risk import risk_analiz_et
from gozcu.guard import denetle
from gozcu.memory import zaman_cizelgesi_ara
from gozcu.models import DiyalogSatiri, Duzeltme, Epizot
from gozcu.tools.registry import ARAC_SEMALARI, ONAY_GEREKTIREN, cagir

MAKS_TUR = 4

SISTEM = """Sen bir savunma sanayi üretim tesisinin kontrol odasında görevli
vardiya amirisin. Operatörle Türkçe konuşuyorsun.

Nasıl davranırsın:
- Kritik bir olay gördüğünde SORULMADAN önce sen haber verirsin
- Konuşmadan önce gerekli sorguları yaparsın (vardiya, ekipman geçmişi)
- Kameradan göremediğin bir şeyi UYDURMAZSIN, operatöre sorarsın
- Operatör seni düzeltirse gozlem_duzelt aracını çağırırsın
- Operatör konuyu değiştirirse cevaplarsın ama AÇIK OLAYI HATIRLATIRSIN
- Üretim hattını durdurmak gibi geri dönüşü zor aksiyonlarda İZİN İSTERSİN
- Kısa cümleler kurarsın. Saha terminolojisi kullanırsın.

Zaman damgalarını MM:SS biçiminde yazarsın."""

EK_ARACLAR = [
    {"type": "function", "function": {
        "name": "zaman_cizelgesi_ara",
        "description": "Geçmiş olay arşivinde anlamsal arama yapar.",
        "parameters": {"type": "object",
                       "properties": {"sorgu": {"type": "string"}},
                       "required": ["sorgu"]}}},
    {"type": "function", "function": {
        "name": "gozlem_duzelt",
        "description": "Operatörün düzeltmesini kalıcı olarak kaydeder.",
        "parameters": {"type": "object", "properties": {
            "epizot_id": {"type": "integer"}, "alan": {"type": "string"},
            "eski": {"type": "string"}, "yeni": {"type": "string"},
            "gerekce": {"type": "string"}},
            "required": ["epizot_id", "alan", "eski", "yeni", "gerekce"]}}},
    {"type": "function", "function": {
        "name": "risk_analizi_iste",
        "description": "Bir olay için iş güvenliği risk analizi ister.",
        "parameters": {"type": "object",
                       "properties": {"epizot_id": {"type": "integer"}},
                       "required": ["epizot_id"]}}},
    {"type": "function", "function": {
        "name": "kok_neden_raporu_uret",
        "description": "Kapanan olay için kök neden raporu üretir.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]


class Nobetci:
    def __init__(self, gw, store) -> None:
        self.gw, self.store = gw, store
        self.gecmis: list[dict] = [{"role": "system", "content": SISTEM}]

    # -- internal tools -----------------------------------------------------

    def _ic_arac(self, ad: str, p: dict):
        if ad == "zaman_cizelgesi_ara":
            return [e.model_dump() for e in
                    zaman_cizelgesi_ara(self.gw, self.store, p["sorgu"])]
        if ad == "gozlem_duzelt":
            self.store.kaydet_duzeltme(Duzeltme(ts=time.monotonic(), **p))
            return {"durum": "kaydedildi"}
        if ad == "risk_analizi_iste":
            epizot = next((e for e in self.store.epizotlar()
                           if e.id == p["epizot_id"]), None)
            if epizot is None:
                return {"hata": "epizot bulunamadı"}
            return risk_analiz_et(self.gw, self.store, epizot).model_dump()
        if ad == "kok_neden_raporu_uret":
            return kok_neden_raporu_uret(self.gw, self.store).model_dump()
        return None

    def _arac_calistir(self, cagri: dict) -> dict:
        ad = cagri["function"]["name"]
        try:
            p = json.loads(cagri["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            return {"hata": "parametreler okunamadı"}

        ic = self._ic_arac(ad, p)
        if ic is not None:
            return ic if isinstance(ic, dict) else {"sonuc": ic}
        return cagir(self.store, ad, p, kim="ajan")

    # -- dialogue -----------------------------------------------------------

    def _dongu(self, kritik: bool) -> str:
        araclar = ARAC_SEMALARI + EK_ARACLAR
        for _ in range(MAKS_TUR):
            yanit = self.gw.sor("ana", self.gecmis, araclar=araclar)
            if not yanit.arac_cagrilari:
                metin = denetle(self.gw, yanit.icerik, kritik=kritik)
                self.gecmis.append({"role": "assistant", "content": metin})
                self.store.kaydet_diyalog(DiyalogSatiri(
                    ts=time.monotonic(), rol="nobetci", metin=metin))
                return metin

            self.gecmis.append({"role": "assistant",
                                "tool_calls": yanit.arac_cagrilari})
            for cagri in yanit.arac_cagrilari:
                sonuc = self._arac_calistir(cagri)
                self.gecmis.append({
                    "role": "tool", "tool_call_id": cagri.get("id", "c"),
                    "content": json.dumps(sonuc, ensure_ascii=False,
                                          default=str)})
        return "Yanıt üretilemedi; olay kaydı korunuyor."

    def yukselt(self, epizot: Epizot) -> str:
        risk = risk_analiz_et(self.gw, self.store, epizot)
        dk, sn = divmod(int(epizot.baslangic_ts), 60)
        self.gecmis.append({
            "role": "user",
            "content": f"[SİSTEM] {dk:02d}:{sn:02d} — kritik olay: "
                       f"{epizot.ozet_tr}. Risk: {risk.seviye}. "
                       f"Operatöre kendin haber ver."})
        return self._dongu(kritik=risk.seviye in ("Yüksek", "Kritik"))

    def konus(self, operator_metni: str) -> str:
        self.store.kaydet_diyalog(DiyalogSatiri(
            ts=time.monotonic(), rol="operator", metin=operator_metni))
        acik = self.store.acik_epizot()
        ek = f"\n[SİSTEM] Açık olay: epizot {acik.id} — {acik.ozet_tr}" if acik else ""
        self.gecmis.append({"role": "user", "content": operator_metni + ek})
        return self._dongu(kritik=False)

    # -- approvals ----------------------------------------------------------

    def bekleyen_onay(self):
        bekleyen = [a for a in self.store.aksiyonlar()
                    if a.onay_durumu == "bekliyor"]
        return bekleyen[-1] if bekleyen else None

    def onayla(self, aksiyon_id: int, onay: bool) -> dict:
        kayit = next(a for a in self.store.aksiyonlar() if a.id == aksiyon_id)
        if not onay:
            self.store.db.execute(
                "UPDATE aksiyon SET veri = json_set(veri, '$.onay_durumu', "
                "'reddedildi') WHERE id = ?", (aksiyon_id,))
            self.store.db.commit()
            return {"durum": "reddedildi"}
        sonuc = cagir(self.store, kayit.tool_adi, kayit.parametreler,
                      kim="operator")
        self.store.db.execute(
            "UPDATE aksiyon SET veri = json_set(veri, '$.onay_durumu', "
            "'onaylandi') WHERE id = ?", (aksiyon_id,))
        self.store.db.commit()
        return {"durum": "onaylandi", **sonuc}
```

`ONAY_GEREKTIREN` is imported for the approval-state constant that `cagir`
already applies; the supervisor never bypasses it.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/test_nobetci.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add gozcu/agents/nobetci.py tests/test_nobetci.py
git commit -m "feat: Nöbetçi supervisor with tool loop, corrections and approvals"
```

---

## Task 14: Benchmark and KPIs — `benchmark/`

**Owner:** `rumeysaoru` · 25 Ağustos

Three families from spec §6. Family C costs nothing — the ledgers already record
tokens and latency.

**Files:**
- Create: `benchmark/__init__.py`, `benchmark/kpi.py`, `benchmark/run.py`, `benchmark/report.py`, `benchmark/ground_truth.csv`
- Test: `tests/test_kpi.py`

**Interfaces:**
- Consumes: `Store`.
- Produces:
  - `karar_dagilimi(store) -> dict[str, float]`
  - `vlm_tetikleme_orani(store) -> float`
  - `olay_basina_token(store) -> dict[str, float]`
  - `duzeltme_yayilimi(store) -> float`
  - `zaman_damgasi_sapmasi(store, gercek: list[tuple[float, float]]) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_kpi.py
from benchmark.kpi import karar_dagilimi, olay_basina_token, vlm_tetikleme_orani
from gozcu.models import Devir, Gozlem, Yorum
from gozcu.store import Store


def _store_with(devirler, gozlem_sayisi=0, yorum_sayisi=0):
    s = Store(":memory:")
    for hedef in devirler:
        s.kaydet_devir(Devir(ts=0.0, kaynak_ajan="yonlendirici",
                             hedef_ajan=hedef, neden="n", guven=0.5,
                             payload_ref="r"))
    for i in range(gozlem_sayisi):
        s.kaydet_gozlem(Gozlem(ts=float(i)))
    for i in range(yorum_sayisi):
        s.kaydet_yorum(Yorum(gozlem_ts=float(i), aciklama="x", model="vlm",
                             token=100, gecikme_ms=500))
    return s


def test_decision_distribution_sums_to_one():
    s = _store_with(["algi", "algi", "yorumlayici", "nobetci"])
    d = karar_dagilimi(s)
    assert abs(sum(d.values()) - 1.0) < 1e-9
    assert d["yonlendiricide_kapandi"] == 0.5


def test_vlm_trigger_rate_is_interpretations_over_observations():
    assert vlm_tetikleme_orani(_store_with([], 100, 3)) == 0.03


def test_trigger_rate_is_zero_not_a_crash_on_an_empty_run():
    assert vlm_tetikleme_orani(_store_with([])) == 0.0


def test_token_totals_are_grouped_by_model():
    assert olay_basina_token(_store_with([], 10, 2))["vlm"] == 200.0
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_kpi.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'benchmark'`

- [ ] **Step 3: Implement `benchmark/kpi.py`**

```python
from collections import defaultdict


def karar_dagilimi(store) -> dict[str, float]:
    devirler = store.devirler()
    if not devirler:
        return {"yonlendiricide_kapandi": 0.0, "yorumlamaya_gitti": 0.0,
                "sentezlemeye_gitti": 0.0, "nobetciye_yukseldi": 0.0}
    n = len(devirler)
    sayac = defaultdict(int)
    for d in devirler:
        sayac[d.hedef_ajan] += 1
    return {
        "yonlendiricide_kapandi": sayac["algi"] / n,
        "yorumlamaya_gitti": sayac["yorumlayici"] / n,
        "sentezlemeye_gitti": sayac["sentezleyici"] / n,
        "nobetciye_yukseldi": sayac["nobetci"] / n,
    }


def vlm_tetikleme_orani(store) -> float:
    gozlem = len(store.gozlemler())
    return 0.0 if gozlem == 0 else len(store.yorumlar()) / gozlem


def olay_basina_token(store) -> dict[str, float]:
    toplam: dict[str, float] = defaultdict(float)
    for y in store.yorumlar():
        toplam[y.model] += y.token
    return dict(toplam)


def duzeltme_yayilimi(store) -> float:
    """Share of corrections whose new value appears in a later episode summary."""
    duzeltmeler = [d for e in store.epizotlar() if e.id
                   for d in store.duzeltmeler(e.id)]
    if not duzeltmeler:
        return 1.0
    yansiyan = sum(
        1 for d in duzeltmeler
        if any(d.yeni in e.ozet_tr for e in store.epizotlar() if e.id == d.epizot_id))
    return yansiyan / len(duzeltmeler)


def zaman_damgasi_sapmasi(store, gercek: list[tuple[float, float]]) -> float:
    """Median |detected episode start - annotated start| in seconds."""
    epizotlar = store.epizotlar()
    if not epizotlar or not gercek:
        return float("nan")
    sapmalar = []
    for baslangic, _bitis in gercek:
        en_yakin = min(epizotlar, key=lambda e: abs(e.baslangic_ts - baslangic))
        sapmalar.append(abs(en_yakin.baslangic_ts - baslangic))
    sapmalar.sort()
    orta = len(sapmalar) // 2
    return (sapmalar[orta] if len(sapmalar) % 2
            else (sapmalar[orta - 1] + sapmalar[orta]) / 2)
```

- [ ] **Step 4: Write `benchmark/ground_truth.csv` and the runner**

Label ~15 clips from `data/` by hand. Header:

```csv
video,olay_var,baslangic_s,bitis_s,tur
forklift-accident--qOPnf-YRuk8.mp4,1,12.5,19.0,arac_devrilmesi
```

`benchmark/run.py` walks every labelled clip, runs the pipeline into a
per-clip SQLite file under `runs/`, and writes `runs/kpi.json`.
`benchmark/report.py` reads that and emits `runs/kpi.md` plus a bar chart of
`karar_dagilimi` — the one chart that goes on a slide.

- [ ] **Step 5: Run the tests and watch them pass**

Run: `uv run pytest tests/test_kpi.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add benchmark tests/test_kpi.py
git commit -m "feat: KPI harness for decision distribution, trigger rate and drift"
```

---

## Task 15: Operator console and the eight-beat acceptance test

**Owner:** `rumeysaoru` · 26 Ağustos

**Files:**
- Create: `gozcu/ui/__init__.py`, `gozcu/ui/console.py`
- Modify: `app.py` (thin entry point calling `gozcu.ui.console.baslat()`)
- Test: `tests/test_dialog_senaryo.py`

**Interfaces:**
- Consumes: everything.
- Produces: `baslat()` launching Gradio; `senaryo_calistir(gw, store) -> dict` — the scripted eight-beat run the test drives.

- [ ] **Step 1: Write the failing acceptance test**

```python
# tests/test_dialog_senaryo.py
from unittest.mock import Mock

import pytest

from gozcu.agents.nobetci import Nobetci
from gozcu.fixtures.loader import gecmisi_yukle
from gozcu.models import Epizot
from gozcu.store import Store


@pytest.fixture
def kurulum():
    store, gw = Store(":memory:"), Mock()
    gw.goem.return_value = [0.1, 0.2, 0.3]
    gw.yeniden_sirala.side_effect = lambda s, a: list(range(len(a)))
    gecmisi_yukle(gw, store)
    e = Epizot(baslangic_ts=192.0, faz="gelisim",
               ozet_tr="istif aracı devrildi, yerde hareketsiz kişi",
               on_risk="Kritik")
    e.id = store.epizot_ac(e)
    return gw, store, e


def test_beat_3_correction_reaches_the_final_report(kurulum):
    """The operator's correction must survive all the way to the report."""
    from gozcu.agents.raportor import kok_neden_raporu_uret
    from gozcu.models import Duzeltme
    gw, store, e = kurulum
    store.kaydet_duzeltme(Duzeltme(ts=1.0, epizot_id=e.id, alan="olay_turu",
                                   eski="araç devrildi", yeni="yük düştü",
                                   gerekce="operatör gözlemi"))
    gw.sor.return_value = type("Y", (), {"icerik": "{}", "arac_cagrilari": []})()
    kok_neden_raporu_uret(gw, store)
    istem = gw.sor.call_args.args[1][-1]["content"]
    assert "yük düştü" in istem


def test_beat_5_archive_answers_a_question_about_this_vehicle(kurulum):
    from gozcu.memory import zaman_cizelgesi_ara
    gw, store, _ = kurulum
    assert zaman_cizelgesi_ara(gw, store, "IST-04 fren") != []


def test_beat_5_open_incident_is_still_open_after_the_switch(kurulum):
    _gw, store, _ = kurulum
    assert store.acik_epizot() is not None


def test_beat_6_degraded_mode_keeps_the_run_alive():
    from gozcu.gateway import Gateway
    gw = Gateway()
    gw.hata_enjekte({"vlm"})
    assert gw.sor("vlm", [{"role": "user", "content": "x"}]).bozulmus is True


def test_beat_4_line_stop_is_never_executed_without_approval(kurulum):
    from gozcu.tools.registry import cagir
    _gw, store, _ = kurulum
    cagir(store, "uretim_hatti_durdur", {"hat_id": "B", "gerekce": "x"})
    assert store.aksiyonlar()[-1].onay_durumu == "bekliyor"


def test_beat_7_output_carries_the_four_sartname_keys():
    from gozcu.models import PipelineCiktisi
    c = PipelineCiktisi(summary="ö", events=[], risk="Kritik", actions=["a"])
    assert set(c.model_dump(exclude_none=True)) >= {
        "summary", "events", "risk", "actions"}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_dialog_senaryo.py -v`
Expected: FAIL until Tasks 7–12 are merged.

- [ ] **Step 3: Build `gozcu/ui/console.py`**

Four panes in a Gradio `Blocks`, left to right, top to bottom:

1. **Video + timeline** — the uploaded clip with episode markers, coloured by risk level.
2. **Chat panel** — the operator's conversation with Nöbetçi. `n.konus()` per turn.
3. **Approval bar** — appears only when `n.bekleyen_onay()` is not `None`; two buttons wired to `n.onayla(id, True/False)`.
4. **Handoff ledger** — `store.devirler()` as a live table: source → target, reason, confidence. This is the explainability artifact.

Two buttons above: **Analizi başlat** (runs `KararDongusu` over the uploaded
video) and **Bağlantıyı kes** (calls `gw.hata_enjekte({"vlm"})` for beat 6).

Keep `app.py` as a three-line entry point so `uv run python app.py` still works.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `uv run pytest tests/ -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add gozcu/ui app.py tests/test_dialog_senaryo.py
git commit -m "feat: operator console with approval bar and handoff ledger"
```

---

## Task 16: Output contract and integration — `gozcu/report.py`

**Owner:** `uvyscengiz` · 26 Ağustos · **Highest-scoring single deliverable (Functionality 35%).**

The four şartname keys are produced even when every extended layer failed.

**Files:**
- Create: `gozcu/report.py`
- Modify: `gozcu/run.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `Store`, `PipelineCiktisi`, `KokNedenRaporu`.
- Produces: `ciktiyi_derle(store, ozet: str, kok_neden=None) -> PipelineCiktisi`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report.py
from gozcu.models import AdayAksiyon, AksiyonKaydi, Epizot, RiskDegerlendirme
from gozcu.report import ciktiyi_derle
from gozcu.store import Store


def test_four_keys_exist_even_with_a_completely_empty_run():
    c = ciktiyi_derle(Store(":memory:"), ozet="Kayda değer olay yok.")
    d = c.model_dump(exclude_none=True)
    assert {"summary", "events", "risk", "actions"} <= set(d)
    assert d["risk"] == "Düşük"


def test_events_use_mmss_and_come_from_episodes():
    store = Store(":memory:")
    store.epizot_ac(Epizot(baslangic_ts=15.0, faz="baslangic",
                           ozet_tr="İstif aracı devrildi", on_risk="Yüksek"))
    c = ciktiyi_derle(store, ozet="ö")
    assert c.events[0].time == "00:15"
    assert c.events[0].event == "İstif aracı devrildi"


def test_overall_risk_is_the_highest_assessed_level():
    store = Store(":memory:")
    for seviye in ("Düşük", "Kritik", "Orta"):
        store.kaydet_risk(RiskDegerlendirme(epizot_id=1, seviye=seviye,
                                            gerekce_tr="g", onlenebilir=True))
    assert ciktiyi_derle(store, ozet="ö").risk == "Kritik"


def test_actions_are_rendered_from_tool_backed_candidates_only():
    store = Store(":memory:")
    store.kaydet_risk(RiskDegerlendirme(
        epizot_id=1, seviye="Kritik", gerekce_tr="g", onlenebilir=True,
        aday_aksiyonlar=[AdayAksiyon(aciklama_tr="Sağlık ekibini çağır",
                                     tool_adi="saglik_ekibi_cagir")]))
    assert ciktiyi_derle(store, ozet="ö").actions == ["Sağlık ekibini çağır"]


def test_detail_block_is_attached_but_never_replaces_the_four_keys():
    store = Store(":memory:")
    store.kaydet_aksiyon(AksiyonKaydi(ts=1.0, tool_adi="saha_alarmi",
                                      parametreler={}, sonuc={}, kim="ajan",
                                      onay_durumu="gerekmiyor"))
    c = ciktiyi_derle(store, ozet="ö")
    assert c.ayrintili is not None and len(c.ayrintili.aksiyon_defteri) == 1
    assert c.summary == "ö"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gozcu.report'`

- [ ] **Step 3: Implement `gozcu/report.py`**

```python
from gozcu.models import (Ayrintili, OlayOzeti, PipelineCiktisi, RiskSeviyesi)

SIRA: list[RiskSeviyesi] = ["Düşük", "Orta", "Yüksek", "Kritik"]


def _mmss(ts: float) -> str:
    return f"{int(ts) // 60:02d}:{int(ts) % 60:02d}"


def ciktiyi_derle(store, ozet: str, kok_neden=None) -> PipelineCiktisi:
    epizotlar = store.epizotlar()
    riskler = store.riskler()

    events = [OlayOzeti(time=_mmss(e.baslangic_ts), event=e.ozet_tr[:200])
              for e in epizotlar]

    seviyeler = [r.seviye for r in riskler] or [e.on_risk for e in epizotlar]
    risk = max(seviyeler, key=SIRA.index) if seviyeler else "Düşük"

    # Rendered from tool-backed candidates only, so the human list and the
    # machine ledger cannot drift apart.
    actions = [a.aciklama_tr for r in riskler for a in r.aday_aksiyonlar]

    return PipelineCiktisi(
        summary=ozet, events=events, risk=risk, actions=actions,
        ayrintili=Ayrintili(
            epizotlar=epizotlar,
            risk_degerlendirmeleri=riskler,
            devir_zinciri=store.devirler(),
            aksiyon_defteri=store.aksiyonlar(),
            kok_neden_raporu=kok_neden.model_dump() if kok_neden else None))
```

- [ ] **Step 4: Rewrite `gozcu/run.py` to drive the loop**

`run_pipeline(video_path)` now: extract frames → build `Gozlem` records from
`detect_objects` + `compute_signals` → construct `KararDongusu` with the real
router, interpreter, synthesizer and `Nobetci.yukselt` callbacks → run it →
return `ciktiyi_derle(store, ozet)`.

Wrap the whole extended path in a `try`; on failure still return a valid
`PipelineCiktisi` with the four keys and `ayrintili=None`. A degraded run must
still be gradeable.

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest tests/ -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add gozcu/report.py gozcu/run.py tests/test_report.py
git commit -m "feat: şartname output contract with detail block and safe fallback"
```

---

## Self-review notes

**Spec coverage.** §3 components → Tasks 4–6, 10–13. §3a decision timing →
Task 4, pinned by `test_escalation_fires_before_the_video_ends`. §4 data model
→ Tasks 1–2. §4b output contract → Task 16. §5 seven tools → Task 8. §6 eight
beats → Task 15; KPIs → Task 14. §7 frozen perception layer → no task touches
`frames.py`/`detect.py`/`track.py`/`signals.py`. §8 work split → track table.

**Two spec items have no code task and are tracked as checklist work on the
26th, not as issues:** the Turkish style pass (a human read of ~20 outputs) and
the packaging deliverables (demo video, docs, slides, repo made public).

**Known deliberate gaps.** `benchmark/run.py` and `gozcu/ui/console.py` are
described structurally rather than line-by-line — both are glue over interfaces
fully specified elsewhere, and both are owned by whoever has the running system
in front of them. `ground_truth.csv` needs human labelling; no code can
substitute.

**Type consistency.** `store.epizot_ac` returns `int` and is assigned to
`e.id` at every call site. `gw.sor(kademe, mesajlar, ...)` is positional in
tier and messages everywhere, which the `call_args.args[0]` assertions depend
on. `zaman_cizelgesi_ara(gw, store, sorgu)` keeps that argument order in
Tasks 7, 10 and 13.

---

## GitHub issues

One task, one issue. Each body = the issue template above (filled in) + that
task's section from this file, verbatim.

| # | Title | Assignee | Day | Labels |
|---|---|---|---|---|
| 1 | Shared Pydantic contract (`gozcu/models.py`) | uvyscengiz | 23 | `çekirdek`, `blocker` |
| 2 | SQLite event store | uvyscengiz | 23 | `çekirdek` |
| 3 | Tiered gateway client with degraded mode | uvyscengiz | 23 | `çekirdek` |
| 4 | In-flight decision loop | uvyscengiz | 23 | `çekirdek` |
| 5 | Router agent over windowed digests | uvyscengiz | 24 | `ajan` |
| 6 | Synthesizer: observations to episodes | uvyscengiz | 24 | `ajan` |
| — | **24 Ağu çıkış kriteri: uçtan uca ince dilim çalışıyor** | uvyscengiz | 24 | `kilometre-taşı` |
| 7 | Episodic memory search | uvyscengiz | 25 | `hafıza` |
| 8 | Seven mock field-system tools | Xana-bit | 25 | `araçlar`, `cold-start` |
| 9 | Seeded facility world (fixtures) | Xana-bit | 25 | `araçlar`, `veri`, `cold-start` |
| 10 | Risk Analisti | uvyscengiz | 25 | `ajan` |
| 11 | Raportör and root-cause report | beyzaalive | 25 | `ajan`, `cold-start` |
| 12 | Guard wrapper | beyzaalive | 25 | `ajan`, `cold-start` |
| 13 | Nöbetçi supervisor | uvyscengiz | 25 | `ajan`, `puan-20` |
| 14 | KPI harness and benchmark report | rumeysaoru | 25 | `ölçüm`, `cold-start` |
| 15 | Operator console and acceptance test | rumeysaoru | 26 | `arayüz` |
| 16 | Output contract and integration | uvyscengiz | 26 | `çekirdek`, `puan-35` |
| 17 | Turkish style pass | beyzaalive | 26 | `teslim` |
| 18 | Packaging: demo video, docs, slides, public repo | hepsi | 26 | `teslim` |

Issues 8, 9, 11, 12 and 14 carry the `cold-start` label: their owner has never
seen this codebase and joins one day before the deadline. Each must be
self-contained, off the integration path, and verifiable with one command. If a
`cold-start` issue turns out to need a conversation to understand, it was
mis-scoped — rewrite it rather than expecting the owner to ask.

**Blocked until the repo invitations are accepted.** `Xana-bit`, `beyzaalive`
and `rumeysaoru` were invited 2026-08-13 and none has accepted, so GitHub will
reject them as assignees. Create the issues unassigned and assign on acceptance.
