# Görev 02 — Olay deposu (`gozcu/store.py`)

> ## ✅ TAMAMLANDI — 23 Ağustos 2026, `6dc96bf`
>
> **Depo indi.** `gozcu/store.py` var, `tests/test_store.py` 6 test ile yeşil.
> Bu dosyayı yeniden uygulama — aşağısı ne yapıldığının kaydı.
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([kararlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> tablo adı `episode_embedding`; `open_episode()` **tek açık epizot garantisi
> vermiyor**, çağıran taraf koruyacak; `Store`'un `close()`'u ve kilidi yok.

**Bağımlılık:** [01](01-sozlesme.md)

## Bağlam

Sistemdeki bütün ajanlar birbirine bu depo üzerinden konuşuyor. Ajan sınırlarını
hiçbir şey serbest metin olarak geçmiyor — her devir buraya yazılan tipli bir
kayıt. Bunun üç getirisi var: şartnamenin istediği *bağlam yönetimi* ve *çok
adımlı karar zincirleri* için somut kanıt, her sınırda bir test noktası, ve
**açıklanabilirlik** — `handoff` tablosu arayüzde çizilince "sistem neden böyle
karar verdi" sorusunun cevabı ekranda görünür oluyor.

SQLite, tek dosya, kurulum yok. Testlerde `Store(":memory:")`.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/test_models.py -v     # Görev 01 yeşil olmalı
```

## Bağımlı olduğun imzalar

`gozcu/models.py` (Görev 01) içindeki bütün tipler. Bu görevde kullanacakların:
`Observation`, `Interpretation`, `Episode`, `RiskAssessment`, `Handoff`, `ActionRecord`,
`Correction`, `DialogueTurn`.

## Ne yapacaksın

`gozcu/store.py` — model başına bir tablo, iç içe yapılar JSON sütununda.

Üreteceğin arayüz:

```python
Store(db_path: str | Path = ":memory:")

save_observation(g) -> int          observations() -> list[Observation]
save_interpretation(y) -> int           interpretations() -> list[Interpretation]
create_episode(e) -> int              update_episode(episode_id, **fields) -> None
open_episode() -> Episode | None   episodes() -> list[Episode]
save_risk(r) -> int            risks() -> list[RiskAssessment]
save_handoff(d) -> int           handoffs() -> list[Handoff]
save_action(a) -> int         actions() -> list[ActionRecord]
set_action_approval(action_id, state) -> None
save_correction(d) -> int        corrections(episode_id) -> list[Correction]
save_dialogue(s) -> int         dialogue() -> list[DialogueTurn]
save_embedding(episode_id, vector) -> None
embeddings() -> list[tuple[int, list[float]]]
```

## Adımlar

### 1. Başarısız testi yaz — `tests/test_store.py`

```python
from gozcu.models import Handoff, Episode, Observation, Signals
from gozcu.store import Store


def test_open_episode_returns_only_the_open_one():
    s = Store(":memory:")
    closed_id = s.create_episode(Episode(start_ts=0.0, phase="outcome", summary_tr="a",
                                   preliminary_risk="Düşük", state="closed"))
    open_id = s.create_episode(Episode(start_ts=10.0, phase="onset", summary_tr="b",
                                 preliminary_risk="Kritik", state="open"))
    assert s.open_episode().id == open_id != closed_id


def test_update_episode_persists_and_roundtrips():
    s = Store(":memory:")
    eid = s.create_episode(Episode(start_ts=1.0, phase="onset", summary_tr="x",
                             preliminary_risk="Orta"))
    s.update_episode(eid, state="closed", end_ts=9.0, phase="outcome")
    e = s.episodes()[0]
    assert (e.state, e.end_ts, e.phase) == ("closed", 9.0, "outcome")


def test_handoff_ledger_preserves_insertion_order():
    s = Store(":memory:")
    for target in ("interpreter", "synthesizer", "risk_analyst"):
        s.save_handoff(Handoff(ts=1.0, source_agent="router",
                             target_agent=target, reason="n", confidence=0.9,
                             payload_ref="r"))
    assert [d.target_agent for d in s.handoffs()] == [
        "interpreter", "synthesizer", "risk_analyst"]


def test_observation_roundtrips_nested_signals_with_int_keys():
    s = Store(":memory:")
    s.save_observation(Observation(ts=2.0, signals=Signals(person_count=3,
                                                       velocities={7: 1.5})))
    assert s.observations()[0].signals.velocities == {7: 1.5}


def test_action_approval_updates_in_place_without_a_new_row():
    from gozcu.models import ActionRecord
    s = Store(":memory:")
    aid = s.save_action(ActionRecord(ts=1.0, tool_name="halt_production_line",
                                        params={}, result={}, actor="agent",
                                        approval="pending"))
    s.set_action_approval(aid, "approved")
    assert len(s.actions()) == 1
    assert s.actions()[0].approval == "approved"


def test_embedding_roundtrips_and_replaces_by_episode_id():
    s = Store(":memory:")
    eid = s.create_episode(Episode(start_ts=1.0, phase="onset", summary_tr="x",
                                   preliminary_risk="Orta"))
    s.save_embedding(eid, [0.1, 0.2, 0.3])
    assert s.embeddings() == [(eid, [0.1, 0.2, 0.3])]
    s.save_embedding(eid, [0.9, 0.8])
    assert s.embeddings() == [(eid, [0.9, 0.8])]
```

Son iki test önemli. Dördüncüsü: JSON sözlük anahtarlarını string olarak geri
verir, `velocities` ise `dict[int, float]` — Pydantic'in bunu geri çevirdiğini
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

from gozcu.models import (ActionRecord, Handoff, DialogueTurn, Correction, Episode,
                          Observation, RiskAssessment, Interpretation)

SCHEMA = """
CREATE TABLE IF NOT EXISTS observation (id INTEGER PRIMARY KEY, ts REAL, payload TEXT);
CREATE TABLE IF NOT EXISTS interpretation (id INTEGER PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS episode (id INTEGER PRIMARY KEY, state TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS episode_embedding (episode_id INTEGER PRIMARY KEY, vector TEXT);
CREATE TABLE IF NOT EXISTS risk (id INTEGER PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS handoff (id INTEGER PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS action (id INTEGER PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS correction (id INTEGER PRIMARY KEY, episode_id INTEGER, payload TEXT);
CREATE TABLE IF NOT EXISTS dialogue (id INTEGER PRIMARY KEY, payload TEXT);
"""


class Store:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.db.commit()

    def _insert(self, table: str, model, **columns) -> int:
        payload = model.model_dump_json(exclude={"id"})
        names = ", ".join(["payload", *columns])
        slots = ", ".join("?" * (1 + len(columns)))
        cur = self.db.execute(
            f"INSERT INTO {table} ({names}) VALUES ({slots})",
            (payload, *columns.values()))
        self.db.commit()
        return cur.lastrowid

    def _read(self, table: str, tip, where: str = "", *params) -> list:
        rows = self.db.execute(
            f"SELECT id, payload FROM {table} {where} ORDER BY id", params)
        return [tip(**{**json.loads(v), "id": i}) for i, v in rows]

    def save_observation(self, g: Observation) -> int:
        return self._insert("observation", g, ts=g.ts)

    def observations(self) -> list[Observation]:
        return self._read("observation", Observation)

    def save_interpretation(self, y: Interpretation) -> int:
        return self._insert("interpretation", y)

    def interpretations(self) -> list[Interpretation]:
        return self._read("interpretation", Interpretation)

    def create_episode(self, e: Episode) -> int:
        return self._insert("episode", e, state=e.state)

    def update_episode(self, episode_id: int, **fields) -> None:
        row = self.db.execute(
            "SELECT payload FROM episode WHERE id = ?", (episode_id,)).fetchone()
        e = Episode(**{**json.loads(row[0]), **fields})
        self.db.execute("UPDATE episode SET payload = ?, state = ? WHERE id = ?",
                        (e.model_dump_json(exclude={"id"}), e.state, episode_id))
        self.db.commit()

    def open_episode(self) -> Episode | None:
        open_rows = self._read("episode", Episode, "WHERE state = ?", "open")
        return open_rows[-1] if open_rows else None

    def episodes(self) -> list[Episode]:
        return self._read("episode", Episode)

    def save_risk(self, r: RiskAssessment) -> int:
        return self._insert("risk", r)

    def risks(self) -> list[RiskAssessment]:
        return self._read("risk", RiskAssessment)

    def save_handoff(self, d: Handoff) -> int:
        return self._insert("handoff", d)

    def handoffs(self) -> list[Handoff]:
        return self._read("handoff", Handoff)

    def save_action(self, a: ActionRecord) -> int:
        return self._insert("action", a)

    def actions(self) -> list[ActionRecord]:
        return self._read("action", ActionRecord)

    def set_action_approval(self, action_id: int, state: str) -> None:
        row = self.db.execute(
            "SELECT payload FROM action WHERE id = ?", (action_id,)).fetchone()
        a = ActionRecord(**{**json.loads(row[0]), "approval": state})
        self.db.execute("UPDATE action SET payload = ? WHERE id = ?",
                        (a.model_dump_json(exclude={"id"}), action_id))
        self.db.commit()

    def save_correction(self, d: Correction) -> int:
        return self._insert("correction", d, episode_id=d.episode_id)

    def corrections(self, episode_id: int) -> list[Correction]:
        return self._read("correction", Correction, "WHERE episode_id = ?", episode_id)

    def save_dialogue(self, s: DialogueTurn) -> int:
        return self._insert("dialogue", s)

    def dialogue(self) -> list[DialogueTurn]:
        return self._read("dialogue", DialogueTurn)

    def save_embedding(self, episode_id: int, vector: list[float]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO episode_embedding VALUES (?, ?)",
            (episode_id, json.dumps(vector)))
        self.db.commit()

    def embeddings(self) -> list[tuple[int, list[float]]]:
        return [(i, json.loads(v)) for i, v in
                self.db.execute("SELECT episode_id, vector FROM episode_embedding")]
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_store.py -v
```
Beklenen: 6 passed

### 5. Commit

```bash
git add gozcu/store.py tests/test_store.py
git commit -m "feat: SQLite event store for observations, episodes and ledgers"
```

## Doğrulama

```bash
uv run pytest tests/test_store.py -v
```
Beklenen: **6 passed**
\n
## Tamamlanma notları (gelecek görevleri bağlayan)

- **Tablo adı `episode_embedding`.** Bu dosya `embeddings()` içinde
  `FROM epizot_embedding` yazıyordu; şema ve `save_embedding` ise
  `episode_embedding` kuruyordu. İlk çağrıda `OperationalError` verecekti ve
  **hiçbir test bunu kapsamıyordu** — bu yüzden sessizce Görev 08/09'a
  taşınacaktı. Düzeltildi; artık altıncı test gömme yuvarlak yolunu ve
  `INSERT OR REPLACE` davranışını koruyor. Beklenen sayı **6 passed**.
- **`open_episode()` tek açık epizot garantisi vermiyor.** Açık satırların
  *sonuncusunu* döndürüyor; depo aynı anda birden çok açık epizota izin
  veriyor. **Bu değişmezi Görev 05'in karar döngüsü koruyacak** — depo
  korumuyor. Aynı şekilde Görev 14'ün beklediği "tam olarak bir bekleyen onay"
  koşulunu da hiçbir şey zorlamıyor.
- **`update_episode` ve `set_action_approval` bilinmeyen id'de `TypeError`
  atıyor** (`fetchone()` `None` dönüyor, `row[0]` patlıyor). Bilinçli olarak
  guard eklenmedi — minimum kod. Görev 05 ve 14 bayat bir id geçirirse okunmaz
  bir hata alır; oraya geldiğinde guard eklemek serbest.
- **`_read` `ORDER BY id`, yani ekleme sırası — `ts` sırası değil.** Gözlemler
  zaman damgası sırası dışında yazılırsa Görev 15/16'nın zaman çizelgesi
  kronolojik olmaz.
- **`Store`'un `close()`'u, WAL'ı ve kilidi yok**, ama `check_same_thread=False`
  ile açılıyor. Görev 05'in `DecisionLoop.run()` generator'ı Gradio'dan
  sürülürken Görev 16 konsolu aynı dosyayı okursa çekişme gerçek. Dosya
  tabanlı `Store` bekleyen Görev 15 bunu bilerek kullanmalı.
- **Filtreli sorgu yok:** `episodes(state=...)` ya da `risks(episode_id=...)`
  imzaları mevcut değil; sadece `corrections(episode_id)` var. Görev 08/09
  epizot başına riskleri Python tarafında süzecek.
