# Canlı akış konsolu — implementasyon planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Konsolu beş sekmeden ikiye indirmek — **CANLI** (oluş sırasında,
ajan atıflı tek kolon besleme) ve **RAPOR** (teslim yükü, kök neden, KPI,
denetim tabloları).

**Architecture:** `Store`'a append-only bir `journal` tablosu ekleniyor;
`AUTOINCREMENT` küresel yazma sırasını veriyor ve besleme o sırada
çiziliyor. Algının pencere özeti (bugün yalnız stderr'e giden) `WindowRecord`
olarak tipleniyor. Saf besleme katmanı `gozcu/ui/feed.py`'de, Gradio
bilmiyor. `console.py` yalnız bağlantı yapıyor.

**Tech Stack:** Python 3.12 · pydantic v2 · sqlite3 · Gradio 6 · pytest

**Spec:** [docs/superpowers/specs/2026-08-26-canli-akis-konsolu-design.md](../specs/2026-08-26-canli-akis-konsolu-design.md)

## Global Constraints

- **Kod İngilizce, insana görünen metin Türkçe.** Sınıf/fonksiyon/alan/JSON
  anahtarı/tablo adı İngilizce; ekran metni, docstring ve yorum Türkçe.
- **Risk seviyeleri tam olarak** `"Düşük" | "Orta" | "Yüksek" | "Kritik"`.
- **Model kimlikleri sadece `gozcu/config.py`'da.**
- **Çıktı sözleşmesi değişmez:** `summary` · `events` · `risk` · `actions`.
- **TDD.** Önce test, kırmızı olduğunu gör, sonra minimum kod.
- Doğrulama: `.venv/bin/pytest tests/ -q` ve
  `uv run python scripts/check-tasks.py`.
- Depo kökü: `/Users/uveyscengiz/Developer/teknofest/gözcü-ai-teknofest`,
  dal `gorev-19-canli-akis`. **Worktree kullanma** — `.venv` ana ağaçta.

## Zaman baskısı altında kesme sırası

Kod dondurma **26 Ağustos 12:00**. Plan 02:05'te yazıldı, yani ~10 saat var
ve tamamı hedefleniyor. Sıkışırsa kesme sırası — bu sırayla, başka türlü
değil:

1. **Task 3 (`WindowRecord`)** ilk düşer. `loop.py`'ye dokunan tek parça ve
   zorunlu örneklemeli pencereler zaten `perception` kaynaklı bir devir
   yazıyor (`loop.py:380`), yani besleme o pencereler için bedavaya bir algı
   satırı alıyor. Kaybedilen: `skipped` ve sessiz `routed` pencereler.
2. **Beslemenin içindeki yükseltme kartı** ikinci düşer — kartlar
   beslemenin ALTINA eklenir (bugünkü `intervention_html`, olduğu gibi).
3. **Defterin kendisi (Task 1–2) kesilmez.** Küçük, eklemeli ve beslemenin
   dayandığı tek şey.

Hiçbiri yetmezse dürüst karşılık: **indirme.** Bugünkü beş sekmeli konsol
çalışıyor.

## Dosya haritası

| Dosya | Sorumluluk |
|---|---|
| `gozcu/models.py` | `JournalEntry`, `WindowRecord` tipleri |
| `gozcu/store.py` | kilit, `journal` + `window_record` tabloları, okumalar |
| `gozcu/loop.py` | pencere özetini tipleyip depoya yazmak |
| `gozcu/ui/feed.py` | **yeni** — saf besleme: `build_feed`, `feed_html` |
| `gozcu/ui/console.py` | iki sekme, yuvalar, bağlantı |

---

### Task 1: Depo kilidi

Defterden ÖNCE gelmeli: kilitsiz `seq` çift numara veriyor (spec §2.1b,
ölçüldü). Kendi başına da değerli — bugünkü gizli bir arızayı kapatıyor.

**Files:**
- Modify: `gozcu/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: —
- Produces: `Store` bütün genel metotlarında iş parçacığı güvenli.
  `Store._lock` bir `threading.RLock`.

- [ ] **Step 1: Write the failing test**

`tests/test_store.py` sonuna:

```python
import threading


def test_concurrent_writers_never_lose_or_duplicate_a_row():
    """İki iş parçacığı aynı bağlantıya yazıyor — konsolda GERÇEKTEN böyle.

    Boru hattı iş parçacığı `run_pipeline`'da yazarken Gradio olay iş
    parçacığı `nobetci.talk()` ve `set_action_approval` ile aynı depoya
    yazıyor (`console.py:953`, `973`, `988`). Kilitsiz hâlde sqlite3 hem
    `InterfaceError` atıyor hem aynı satır kimliğini iki kez veriyor.
    """
    s = Store(":memory:")
    errors, ids = [], []

    def write(agent):
        try:
            for _ in range(200):
                ids.append(s.save_handoff(Handoff(
                    ts=1.0, source_agent="router", target_agent=agent,
                    reason="n", confidence=0.9, payload_ref="r")))
        except Exception as error:      # noqa: BLE001 — teste taşınacak
            errors.append(repr(error))

    threads = [threading.Thread(target=write, args=(a,))
               for a in ("interpreter", "synthesizer")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(ids) == 400
    assert len(set(ids)) == 400, "aynı satır kimliği iki kez dağıtıldı"
    assert len(s.handoffs()) == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_store.py::test_concurrent_writers_never_lose_or_duplicate_a_row -q`

Expected: FAIL — ya `errors != []` (`InterfaceError: bad parameter or other
API misuse`) ya da `len(set(ids)) < 400`.

> Bu test doğası gereği yarış koşuluna dayanıyor; kırmızıyı görmek için
> gerekirse birkaç kez koştur. Yeşile döndükten sonra deterministik.

- [ ] **Step 3: Write minimal implementation**

`gozcu/store.py` başına `import threading`. `Store.__init__` içine, ilk satır
olarak:

```python
        #: Konsolda iki iş parçacığı aynı bağlantıya yazıyor: boru hattı
        #: (`run_pipeline`) ve Gradio olay iş parçacığı (`talk`, onay,
        #: `catch_up`). Kilitsiz hâlde sqlite3 çift `lastrowid` veriyor ve
        #: `journal`'ın sırası sessizce karışıyor — beslemenin dayandığı tek
        #: şey o sıra. RLock: `create_episode` gibi genel metotlar `_insert`i,
        #: `open_episode` `_read`i çağırıyor; düz kilit kendini kilitlerdi.
        self._lock = threading.RLock()
```

Sonra `_insert`, `_read`, `update_episode`, `set_action_approval`,
`save_embedding`, `embeddings` gövdelerini `with self._lock:` altına al.
`open_episode` `_read` çağırdığı için ayrıca sarmaya gerek yok ama zararsız.

Örnek:

```python
    def _insert(self, table: str, model, **columns) -> int:
        payload = model.model_dump_json(exclude={"id"})
        names = ", ".join(["payload", *columns])
        slots = ", ".join(["?"] * (1 + len(columns)))
        with self._lock:
            cur = self.db.execute(
                f"INSERT INTO {table} ({names}) VALUES ({slots})",
                (payload, *columns.values()))
            self.db.commit()
            return cur.lastrowid
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_store.py -q` — hepsi yeşil.

- [ ] **Step 5: Commit**

```bash
git add gozcu/store.py tests/test_store.py
git commit -m "fix(store): iki yazar iş parçacığı çift satır kimliği veriyordu — kilit"
```

---

### Task 2: Sıra defteri (`journal`)

**Files:**
- Modify: `gozcu/models.py`, `gozcu/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: Task 1'in `Store._lock`'u.
- Produces:
  - `models.JournalEntry(seq:int, source:str, row_id:int, kind:str, snapshot:dict|None)`
  - `Store.journal() -> list[JournalEntry]` — `seq` artan.
  - `Store._insert(table, model, *, journal=True, snapshot=None, **columns)`
  - `save_observation` defterlemez.

- [ ] **Step 1: Write the failing test**

`tests/test_store.py` sonuna:

```python
def test_the_journal_orders_writes_across_tables():
    """Defterin bütün işi bu: farklı tablolara yazılmış satırları GERÇEK
    yazılma sırasında dizmek. Aynı `ts`, ayrı tablo, ayrı kimlik uzayı."""
    s = Store(":memory:")
    s.save_handoff(Handoff(ts=5.0, source_agent="router",
                           target_agent="interpreter", reason="n",
                           confidence=0.9, payload_ref="r"))
    eid = s.create_episode(Episode(start_ts=5.0, phase="onset", summary_tr="a",
                                   preliminary_risk="Orta"))
    s.save_action(ActionRecord(ts=5.0, tool_name="notify_supervisor",
                               actor="agent", approval="not_required"))
    assert [(e.source, e.kind) for e in s.journal()] == [
        ("handoff", "create"), ("episode", "create"), ("action", "create")]
    assert [e.seq for e in s.journal()] == sorted(e.seq for e in s.journal())
    assert s.journal()[1].row_id == eid


def test_observations_are_not_journalled():
    """3 fps'te on saniyelik bir pencere ~30 gözlem. Defterlenirlerse besleme
    ayrıntılı kayda döner — ve gözlem bir ajan sınırını geçmiyor."""
    s = Store(":memory:")
    s.save_observation(Observation(ts=1.0))
    s.save_observation(Observation(ts=2.0))
    assert s.observations() != []
    assert s.journal() == []


def test_a_mutated_episode_keeps_the_summary_it_had_at_the_time():
    """Anlık görüntünün bütün sebebi: sentezleyici epizoda kaynaşıyor ve
    `summary_tr` değişiyor. Defter satırını canlı satıra çözmek, koşunun
    başındaki girdiye epizodun SONUNDAKİ özetini bastırırdı — ekran o an
    söylenmemiş bir şeyi söylemiş gibi görünürdü."""
    s = Store(":memory:")
    eid = s.create_episode(Episode(start_ts=1.0, phase="onset",
                                   summary_tr="ilk hâli",
                                   preliminary_risk="Düşük"))
    s.update_episode(eid, summary_tr="sonraki hâli", preliminary_risk="Kritik")

    created, updated = s.journal()
    assert created.snapshot["summary_tr"] == "ilk hâli"
    assert created.snapshot["preliminary_risk"] == "Düşük"
    assert updated.kind == "update"
    assert updated.snapshot["summary_tr"] == "sonraki hâli"
    assert updated.snapshot["preliminary_risk"] == "Kritik"


def test_a_gated_call_does_not_print_the_same_tool_three_times():
    """Onaylı bir araç ÜÇ defter satırı doğuruyor: ajanın `pending` çağrısı,
    operatörün ikinci `call_tool` çağrısı (`supervisor.py:466`) ve onay
    güncellemesi (`supervisor.py:471`). Üçünü de basmak, bir kez çağrılan
    aracı üç kez çağrılmış gibi gösterir.

    Kural: aynı `tool_name` + aynı `ts` için operatörün ikinci `create`i
    atlanıyor; çağrı ajanda, karar onay satırında kalıyor.
    """
    s = Store(":memory:")
    aid = s.save_action(ActionRecord(ts=3.0, tool_name="halt_production_line",
                                     actor="agent", approval="pending"))
    s.save_action(ActionRecord(ts=3.0, tool_name="halt_production_line",
                               actor="operator", approval="approved"))
    s.set_action_approval(aid, "approved")
    from gozcu.ui.feed import build_feed
    assert [(e.kind, e.agent) for e in build_feed(s)] == [
        ("action", "supervisor"), ("approval", "operator")]


def test_an_approval_decision_is_its_own_journal_row():
    """Onay kararı AYRI bir girdi. Çağrının kendi satırını güncellemek onu
    beslemede yerinden oynatırdı; çağrı çağrıldığı anda kalmalı, karar
    verildiği anda görünmeli."""
    s = Store(":memory:")
    aid = s.save_action(ActionRecord(ts=3.0, tool_name="halt_production_line",
                                     actor="agent", approval="pending"))
    s.set_action_approval(aid, "approved")
    rows = s.journal()
    assert [r.kind for r in rows] == ["create", "approval"]
    assert rows[1].row_id == aid
    assert rows[1].snapshot == {"approval": "approved"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_store.py -q -k "journal or journalled or mutated or approval_decision"`
Expected: FAIL — `AttributeError: 'Store' object has no attribute 'journal'`

- [ ] **Step 3: Write minimal implementation**

`gozcu/models.py`, `Correction`'ın yanına:

```python
class JournalEntry(Base):
    """Bir yazmanın küresel sıradaki yeri.

    Tipli tablolar tek gerçek kaynak olarak KALIYOR; defter yalnız "hangi
    satır ne zaman yazıldı"yı söylüyor. `seq` süreç boyunca artan tek sayaç
    — aynı `ts`'e düşen yazmaları ayıran tek şey o.

    `snapshot` yalnız DEĞİŞEN kayıtlarda dolu (epizot, onay): defter satırı
    canlı satıra çözülürse o an geçerli olmayan bir metin basılır.
    """

    seq: int
    source: str
    row_id: int
    kind: Literal["create", "update", "approval"]
    snapshot: dict | None = None
```

`gozcu/store.py` — `SCHEMA` sonuna:

```sql
CREATE TABLE IF NOT EXISTS journal (seq INTEGER PRIMARY KEY AUTOINCREMENT,
                                    source TEXT, row_id INTEGER, kind TEXT,
                                    snapshot TEXT);
```

`JournalEntry`'yi import et. Sonra:

```python
    def _journal(self, source: str, row_id: int, kind: str,
                 snapshot: dict | None = None) -> None:
        """Deftere tek satır. `_insert`'ün içinden ve mutasyonlardan çağrılır."""
        self.db.execute(
            "INSERT INTO journal (source, row_id, kind, snapshot) "
            "VALUES (?, ?, ?, ?)",
            (source, row_id, kind,
             json.dumps(snapshot, ensure_ascii=False) if snapshot else None))

    def journal(self) -> list[JournalEntry]:
        with self._lock:
            rows = self.db.execute(
                "SELECT seq, source, row_id, kind, snapshot FROM journal "
                "ORDER BY seq").fetchall()
        return [JournalEntry(seq=seq, source=source, row_id=row_id, kind=kind,
                             snapshot=json.loads(snap) if snap else None)
                for seq, source, row_id, kind, snap in rows]
```

`_insert` defterliyor:

```python
    def _insert(self, table: str, model, *, journal: bool = True,
                snapshot: dict | None = None, **columns) -> int:
        """`journal=False` yalnız gözlem için: 3 fps'te defteri boğar ve
        gözlem bir ajan sınırını geçmiyor (bkz. `save_observation`)."""
        payload = model.model_dump_json(exclude={"id"})
        names = ", ".join(["payload", *columns])
        slots = ", ".join(["?"] * (1 + len(columns)))
        with self._lock:
            cur = self.db.execute(
                f"INSERT INTO {table} ({names}) VALUES ({slots})",
                (payload, *columns.values()))
            row_id = cur.lastrowid
            if journal:
                self._journal(table, row_id, "create", snapshot)
            self.db.commit()
            return row_id
```

`save_action` anlık görüntü taşıyor — `set_action_approval` bu satırı
YERİNDE yeniden yazıyor, yani çağrı satırı durumu canlı okursa çağrıldığı
anda `pending` olan bir araç geriye dönük `onaylandı` görünür:

```python
    def save_action(self, action: ActionRecord) -> int:
        return self._insert("action", action,
                            snapshot={"approval": action.approval})
```

`save_observation` defterlemiyor:

```python
    def save_observation(self, observation: Observation) -> int:
        return self._insert("observation", observation, ts=observation.ts,
                            journal=False)
```

`create_episode` anlık görüntü yazıyor (epizot sonradan değişiyor):

```python
    def create_episode(self, episode: Episode) -> int:
        return self._insert("episode", episode, state=episode.state,
                            snapshot=_episode_snapshot(episode, "synthesizer"))
```

Modül düzeyinde:

```python
def _episode_snapshot(episode: Episode, origin: str) -> dict:
    """Beslemenin epizottan bastığı alanlar — hepsi bu, fazlası defteri şişirir.

    `end_ts` DAHİL: epizodun bitişi sonraki her kaynaşmada ileri kayıyor ve
    damga canlı satırdan okunursa erken bir girdi olayın SONUNDAKİ bitişini
    gösterir — anlık görüntünün önlemek için var olduğu kayma.

    `origin` `update_episode`'un iki çağıranını ayırıyor: sentezleyici
    kaynaştırıyor (`synthesizer.py:267`), süpervizör özeti DÜZELTİYOR
    (`supervisor.py:249`). Tek satıra düşerlerse operatörün düzelttiği bir
    özet model çıktısı gibi görünür.
    """
    return {"summary_tr": episode.summary_tr,
            "preliminary_risk": episode.preliminary_risk,
            "phase": episode.phase, "state": episode.state,
            "start_ts": episode.start_ts, "end_ts": episode.end_ts,
            "origin": origin}
```

`update_episode` ve `set_action_approval` defterliyor:

```python
    def update_episode(self, episode_id: int, *,
                       origin: str = "synthesizer", **fields) -> None:
        """`origin` çağıranın sorumluluğu. Süpervizör düzeltirken
        `origin="supervisor"` geçiyor (`supervisor.py:249`); sentezleyici
        varsayılanı kullanıyor."""
        with self._lock:
            row = self.db.execute(
                "SELECT payload FROM episode WHERE id = ?",
                (episode_id,)).fetchone()
            episode = Episode(**{**json.loads(row[0]), **fields})
            self.db.execute(
                "UPDATE episode SET payload = ?, state = ? WHERE id = ?",
                (episode.model_dump_json(exclude={"id"}), episode.state,
                 episode_id))
            self._journal("episode", episode_id, "update",
                          _episode_snapshot(episode, origin))
            self.db.commit()

    def set_action_approval(self, action_id: int, state: str) -> None:
        """Onay akışı buna dayanır: yeni satır açmaz, mevcut satırı günceller.

        Deftere ise AYRI bir girdi yazar — çağrının kendi satırını oynatmak
        onu beslemede çağrıldığı andan koparırdı.
        """
        with self._lock:
            row = self.db.execute(
                "SELECT payload FROM action WHERE id = ?",
                (action_id,)).fetchone()
            action = ActionRecord(**{**json.loads(row[0]), "approval": state})
            self.db.execute("UPDATE action SET payload = ? WHERE id = ?",
                            (action.model_dump_json(exclude={"id"}), action_id))
            self._journal("action", action_id, "approval", {"approval": state})
            self.db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_store.py tests/test_models.py -q`

- [ ] **Step 5: Commit**

```bash
git add gozcu/models.py gozcu/store.py tests/test_store.py
git commit -m "feat(store): append-only sıra defteri — tablolar arası gerçek yazma sırası"
```

---

### Task 3: Pencere kaydı (`WindowRecord`)

Algının pencere özeti bugün `loop.py:518-527`'de hesaplanıp **yalnız
stderr'e** gidiyor. Tipleniyor ve depoya yazılıyor.

**Files:**
- Modify: `gozcu/models.py`, `gozcu/store.py`, `gozcu/loop.py`
- Test: `tests/test_loop.py`

**Interfaces:**
- Consumes: Task 2'nin `_insert`/`journal`'ı.
- Produces:
  - `models.WindowRecord`
  - `Store.save_window(record) -> int`, `Store.window_records() -> list[WindowRecord]`
  - `loop.window_record(window, index, total, floor_passed, vision_budgeted, outcome) -> WindowRecord`

- [ ] **Step 1: Write the failing test**

`tests/test_loop.py` sonuna:

```python
from gozcu.models import WindowRecord


def _obs(ts, people=0, labels=()):
    from gozcu.models import Detection, Observation, Signals
    return Observation(
        ts=ts, signals=Signals(person_count=people),
        detections=[Detection(label=l, confidence=0.9, box=(0, 0, 1, 1))
                    for l in labels])


def test_a_window_record_is_written_for_every_window():
    """Besleme "sistem bu on saniyede ne gördü"yü buradan okuyor — 30 ham
    gözlemden değil."""
    store = Store(":memory:")
    loop = DecisionLoop(store, route=lambda w: RouterDecision(
        decision="ignore", rationale="sakin", confidence=0.9),
        interpret=lambda w: None, synthesize=lambda w, i, d: None)
    observations = [_obs(t, people=2, labels=("person", "forklift"))
                    for t in (0.0, 3.0, 6.0, 11.0, 14.0)]

    list(loop.run(observations))

    records = store.window_records()
    assert [r.index for r in records] == [1, 2]
    assert [r.total for r in records] == [2, 2]
    assert records[0].frames == 3
    assert records[0].person_peak == 2
    assert records[0].detections == 6
    assert records[0].labels == ["forklift", "person"]
    assert records[0].floor_passed is True


def test_the_three_window_outcomes_stay_distinct():
    """`skipped` ile `routed` aynı satıra düşemez: "bakılmadı" ile
    "bakıldı, bir şey yoktu" farklı şeyler."""
    store = Store(":memory:")
    loop = DecisionLoop(store, route=lambda w: RouterDecision(
        decision="ignore", rationale="sakin", confidence=0.9),
        interpret=lambda w: None, synthesize=lambda w, i, d: None)
    # ilk pencere tabandan geçiyor (insan var), ikincisi geçemiyor ve
    # bütçeye de seçilmiyor
    observations = [_obs(0.0, people=1), _obs(11.0, people=0)]

    list(loop.run(observations))

    outcomes = [r.outcome for r in store.window_records()]
    assert outcomes[0] == "routed"
    assert outcomes[1] == "skipped"


def test_the_window_record_matches_what_the_trace_line_says():
    """İki gösterim tek yardımcıdan doğuyor. Ayrışırlarsa ekran ile kayıt
    farklı şeyler söyler."""
    from gozcu.loop import window_record
    window = [_obs(0.0, people=1, labels=("person",)),
              _obs(2.0, people=3, labels=("forklift",))]
    record = window_record(window, index=1, total=4, floor_passed=True,
                           vision_budgeted=False, outcome="routed")
    assert isinstance(record, WindowRecord)
    assert (record.ts, record.end_ts) == (0.0, 2.0)
    assert record.person_peak == 3
    assert record.detections == 2
    assert record.labels == ["forklift", "person"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_loop.py -q -k "window_record or window_outcomes or every_window"`
Expected: FAIL — `ImportError: cannot import name 'WindowRecord'`

- [ ] **Step 3: Write minimal implementation**

`gozcu/models.py`:

```python
class WindowRecord(Base):
    """Bir pencerenin algı + triyaj özeti.

    Aynı sayılar bugün `loop.run()` içinde hesaplanıp yalnız `trace`e
    gidiyor. Besleme "sistem bu on saniyede ne gördü" sorusunu buradan
    cevaplıyor; ham gözlem 3 fps ile akıyor ve ekrana basılamaz.

    `outcome` üç dalı ayırıyor: `routed` tabandan geçti, `forced` geçemedi
    ama görü bütçesine seçildi, `skipped` hiçbir katman bakmadı. "Bakılmadı"
    ile "bakıldı, bir şey yoktu" aynı kelimeye düşemez.
    """

    id: int | None = None
    ts: float
    end_ts: float
    index: int
    total: int
    frames: int
    person_peak: int = 0
    detections: int = 0
    labels: list[str] = Field(default_factory=list)
    floor_passed: bool
    vision_budgeted: bool = False
    outcome: Literal["routed", "forced", "skipped"]
```

`gozcu/store.py` — `SCHEMA`'ya (**tablo adı `window_record`**; `window`
SQLite 3.25+'ta anahtar kelime):

```sql
CREATE TABLE IF NOT EXISTS window_record (id INTEGER PRIMARY KEY, ts REAL, payload TEXT);
```

```python
    def save_window(self, record: WindowRecord) -> int:
        return self._insert("window_record", record, ts=record.ts)

    def window_records(self) -> list[WindowRecord]:
        return self._read("window_record", WindowRecord)
```

**`gozcu/agents/supervisor.py:249`** — düzeltme kendini bildiriyor:

```python
        self.store.update_episode(episode.id, summary_tr=new_summary[:600],
                                  origin="supervisor")
```

Bu tek kelime, operatörün düzelttiği bir özetin beslemede model çıktısı gibi
görünmesini engelliyor.

`gozcu/loop.py` — modül düzeyinde, `windows()`'un yanına:

```python
def window_record(window: list[Observation], index: int, total: int,
                  floor_passed: bool, vision_budgeted: bool,
                  outcome: str) -> WindowRecord:
    """Pencerenin algı özeti — iz satırı da bu kayıttan yazılıyor.

    Toplama TEK yerde: `trace` satırı ile depo kaydı ayrışırsa ekran ile
    kayıt farklı şeyler söyler ve hangisinin doğru olduğu anlaşılamaz.
    """
    return WindowRecord(
        ts=window[0].ts, end_ts=window[-1].ts, index=index, total=total,
        frames=len(window),
        person_peak=max((o.signals.person_count for o in window), default=0),
        detections=sum(len(o.detections) for o in window),
        labels=sorted({d.label for o in window for d in o.detections}),
        floor_passed=floor_passed, vision_budgeted=vision_budgeted,
        outcome=outcome)


def window_span(record: WindowRecord) -> str:
    """İz satırının metni — `window_record`'dan türetiliyor, elle değil."""
    return (f"{record.ts:.0f}–{record.end_ts:.0f}s kişi≤{record.person_peak} "
            f"kutu={record.detections} "
            f"[{','.join(record.labels) or 'tespit yok'}]")
```

`run()` içinde, mevcut `span`/`peak`/`boxes`/`labels` hesabını **sil** ve
yerine kaydı kur. Her dal kendi `outcome`'unu veriyor:

```python
        for index, window in enumerate(plan):
            if not window:
                continue
            passed = not failing[index]
            budgeted = index in forced
            outcome = ("routed" if passed
                       else "forced" if budgeted else "skipped")
            record = window_record(window, index + 1, len(plan), passed,
                                   budgeted, outcome)
            self.store.save_window(record)
            span = window_span(record)

            if failing[index]:
                if budgeted:
                    with trace.step(f"pencere[{index + 1}/{len(plan)}]",
                                    f"{span} taban=HAYIR görü=zorunlu"):
                        self._forced_sample(window)
                else:
                    trace.event(f"pencere[{index + 1}/{len(plan)}]",
                                f"{span} taban=HAYIR atlandı")
                continue
            started = time.monotonic()
            trace.event(f"pencere[{index + 1}/{len(plan)}]",
                        f"{span} taban=EVET "
                        f"görü={'bütçede' if budgeted else 'gerekirse'}")
            yield from self._routed(window, vision_budgeted=budgeted)
            trace.event(f"pencere[{index + 1}/{len(plan)}]",
                        f"bitti, {(time.monotonic() - started) * 1000:.0f} ms")
```

`WindowRecord`'u `gozcu/loop.py` importlarına ekle.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_loop.py tests/test_store.py -q`

- [ ] **Step 5: Commit**

```bash
git add gozcu/models.py gozcu/store.py gozcu/loop.py tests/test_loop.py
git commit -m "feat(loop): pencere özeti tiplendi ve depoya yazılıyor — stderr'de kalmıyor"
```

---

### Task 4: Besleme katmanı (`gozcu/ui/feed.py`)

Saf. Gradio bilmiyor. `console.py` zaten 1140 satır; besleme oraya girmiyor.

**Files:**
- Create: `gozcu/ui/feed.py`
- Test: `tests/test_feed.py` (yeni)

**Interfaces:**
- Consumes: `Store.journal()`, `Store.window_records()` ve mevcut okumalar.
- **`visible_dialogue` `console.py`'dan buraya TAŞINIYOR** (dairesel import:
  `console` başında `feed`i, `feed` de yarı kurulmuş `console`u çağırırdı ve
  konsol her açılışta `ImportError` ile ölürdü).
- Produces:
  - `feed.FeedEntry`
  - `feed.build_feed(store, escalated_ids=None, archived=None) -> list[FeedEntry]`
  - `feed.feed_html(entries) -> str`
  - `feed.FEED_EMPTY`

- [ ] **Step 1: Write the failing test**

`tests/test_feed.py`:

```python
"""Besleme katmanı — oluş sırası ve ajan atfı."""

from gozcu.models import (ActionRecord, DialogueTurn, Episode, Handoff,
                          Interpretation, RiskAssessment, WindowRecord)
from gozcu.store import Store
from gozcu.ui.feed import FEED_EMPTY, build_feed, feed_html


def _store():
    return Store(":memory:")


def test_an_empty_store_says_so_instead_of_drawing_a_box():
    assert build_feed(_store()) == []
    assert FEED_EMPTY in feed_html([])


def test_the_feed_follows_write_order_not_timestamp():
    """Telafi (`catch_up`) sonradan yazılan bir kaydı ÖNCEKİ bir video
    saniyesine koyabiliyor. Besleme yaşanan sırayı göstermek zorunda; damga
    zaten hangi saniyeye ait olduğunu söylüyor."""
    s = _store()
    s.save_dialogue(DialogueTurn(ts=90.0, role="supervisor", text="sonra"))
    s.save_dialogue(DialogueTurn(ts=10.0, role="system", text="telafi"))
    assert [e.title for e in build_feed(s)] == ["sonra", "telafi"]
    assert [e.ts for e in build_feed(s)] == [90.0, 10.0]


def test_every_entry_names_the_agent_that_produced_it():
    """%20'lik otonomi kriteri tam olarak "bunu ajan mı yaptı, insan mı"
    diye soruyor."""
    s = _store()
    s.save_window(WindowRecord(ts=0.0, end_ts=9.0, index=1, total=2, frames=3,
                               floor_passed=True, outcome="routed"))
    s.save_handoff(Handoff(ts=0.0, source_agent="router",
                           target_agent="interpreter", reason="bak",
                           confidence=0.8, payload_ref="w"))
    s.save_interpretation(Interpretation(observation_ts=0.0,
                                         description="forklift devrildi",
                                         model="m"))
    eid = s.create_episode(Episode(start_ts=0.0, phase="onset",
                                   summary_tr="devrilme",
                                   preliminary_risk="Yüksek"))
    s.save_risk(RiskAssessment(episode_id=eid, level="Kritik",
                               rationale_tr="yaralı olabilir",
                               preventable=True))
    s.save_dialogue(DialogueTurn(ts=0.0, role="supervisor", text="dikkat"))
    s.save_action(ActionRecord(ts=0.0, tool_name="notify_supervisor",
                               actor="agent", approval="not_required"))

    assert [e.agent for e in build_feed(s)] == [
        "perception", "router", "interpreter", "synthesizer", "risk_analyst",
        "supervisor", "supervisor"]


def test_a_handoff_carries_both_ends_so_the_arrow_can_be_drawn():
    s = _store()
    s.save_handoff(Handoff(ts=1.0, source_agent="risk_analyst",
                           target_agent="supervisor", reason="yükselt",
                           confidence=0.91, payload_ref="e1"))
    entry, = build_feed(s)
    assert (entry.agent, entry.target) == ("risk_analyst", "supervisor")
    assert entry.confidence == 0.91
    assert "yükselt" in entry.detail
    assert "→" in feed_html([entry])


def test_an_operator_action_is_not_credited_to_an_agent():
    s = _store()
    s.save_action(ActionRecord(ts=1.0, tool_name="notify_supervisor",
                               actor="operator", approval="not_required"))
    assert build_feed(s)[0].agent == "operator"


def test_the_approval_decision_appears_where_it_was_decided():
    """Çağrı çağrıldığı anda kalıyor, karar verildiği anda görünüyor."""
    s = _store()
    aid = s.save_action(ActionRecord(ts=3.0, tool_name="halt_production_line",
                                     actor="agent", approval="pending"))
    s.save_dialogue(DialogueTurn(ts=3.0, role="operator", text="onayla"))
    s.set_action_approval(aid, "approved")
    kinds = [(e.kind, e.agent) for e in build_feed(s)]
    assert kinds == [("action", "supervisor"), ("dialogue", "operator"),
                     ("approval", "operator")]


def test_an_updated_episode_shows_the_summary_it_had_at_the_time():
    s = _store()
    eid = s.create_episode(Episode(start_ts=1.0, phase="onset",
                                   summary_tr="ilk hâli",
                                   preliminary_risk="Düşük"))
    s.update_episode(eid, summary_tr="sonraki hâli", preliminary_risk="Kritik")
    first, second = build_feed(s)
    assert first.title == "ilk hâli" and first.risk == "Düşük"
    assert second.title == "sonraki hâli" and second.risk == "Kritik"


def test_audit_rows_stay_out_of_the_feed():
    """`visible_dialogue`'un kuralı aynen taşınıyor: denetim hükmü operatöre
    söylenmiş bir söz değil. Diğer `system` satırları GÖRÜNÜYOR — bozulmuş
    mod cevapları ve `LATE_NOTICE` demo beat 6'nın kendisi."""
    from gozcu.agents.supervisor import AUDIT_PREFIX
    s = _store()
    s.save_dialogue(DialogueTurn(ts=1.0, role="system",
                                 text=f"{AUDIT_PREFIX} engellendi"))
    s.save_dialogue(DialogueTurn(ts=2.0, role="system", text="bağlantı kesildi"))
    assert [e.title for e in build_feed(s)] == ["bağlantı kesildi"]


def test_archived_episodes_never_enter_the_feed():
    """`load_history` arşiv fikstürlerini epizot olarak yazıyor. Beslemede
    "sentezleyici olay açtı" diye görünürlerse bu videoda olmamış bir şey
    iddia edilir."""
    s = _store()
    old = s.create_episode(Episode(start_ts=0.0, phase="outcome",
                                   summary_tr="geçen ayki kaza",
                                   preliminary_risk="Yüksek", state="closed"))
    s.create_episode(Episode(start_ts=5.0, phase="onset", summary_tr="bugünkü",
                             preliminary_risk="Orta"))
    assert [e.title for e in build_feed(s, archived={old})] == ["bugünkü"]


def test_a_journal_row_pointing_at_a_missing_record_is_skipped_not_raised():
    """Bir tanı yüzeyi ölçtüğü koşuyu öldürmemeli — `trace.py` ile aynı
    sözleşme."""
    s = _store()
    s.save_dialogue(DialogueTurn(ts=1.0, role="supervisor", text="var"))
    s.db.execute("INSERT INTO journal (source, row_id, kind) "
                 "VALUES ('dialogue', 999, 'create')")
    s.db.execute("INSERT INTO journal (source, row_id, kind) "
                 "VALUES ('kimsenin_bilmediği_tablo', 1, 'create')")
    s.db.commit()
    assert [e.title for e in build_feed(s)] == ["var"]


def test_the_html_puts_the_newest_entry_last_in_the_dom():
    """`column-reverse` görsel sırayı ters çeviriyor: DOM'da EN YENİ ÖNCE
    yazılıyor ki ekranda eskiden yeniye okunsun ve kaydırma en yeniye
    sabitlensin (tarayıcıda ölçüldü, spec §2.4)."""
    s = _store()
    s.save_dialogue(DialogueTurn(ts=1.0, role="supervisor", text="birinci"))
    s.save_dialogue(DialogueTurn(ts=2.0, role="supervisor", text="ikinci"))
    html = feed_html(build_feed(s))
    assert "column-reverse" in html
    assert html.index("ikinci") < html.index("birinci")


def test_model_text_is_escaped_so_it_cannot_break_the_page():
    s = _store()
    s.save_dialogue(DialogueTurn(ts=1.0, role="supervisor",
                                 text="<script>alert(1)</script>"))
    html = feed_html(build_feed(s))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_feed.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'gozcu.ui.feed'`

- [ ] **Step 3: Write minimal implementation**

`gozcu/ui/feed.py`. Tam dosya:

```python
"""Canlı besleme — oluş sırasında, ajan atıflı tek akış.

Beş sekmelik konsol sistemin yaptığı işi KAYNAĞINA göre bölüyordu: devirler
bir sekmede, araç çağrıları başkasında, süpervizörün konuşması üçüncüde.
Hepsi aynı on saniyede olmuş şeylerdi ve hiçbir ekran onları birlikte
göstermiyordu — jüri, ajanların birbirine ne devrettiğini görmek için sekme
değiştirmek zorundaydı. Şartname §7 "çok adımlı karar zincirleri"ni doğrudan
puanlıyor ve o zincir tam olarak burada görünüyor.

Bu modül SAF: Gradio bilmiyor, depoyu yalnız okuyor, `tests/test_feed.py`
bütünüyle sınıyor.

## Sıra `seq`, `ts` değil

Besleme `Store.journal()`'ın küresel yazma sırasında çiziliyor. Telafi
(`catch_up`) sonradan yazılan bir kaydı ÖNCEKİ bir video saniyesine
koyabiliyor; `ts`'e göre dizmek onu yaşanmadığı bir geçmişe taşırdı. Damga
ekranda duruyor ve hangi saniyeye ait olduğunu zaten söylüyor.
"""

import html

from gozcu.agents.router import mmss
from gozcu.agents.supervisor import AUDIT_PREFIX
from gozcu.models import JournalEntry

__all__ = ["FEED_EMPTY", "FeedEntry", "build_feed", "feed_html",
           "visible_dialogue"]


def visible_dialogue(turns: list) -> list:
    """Ekranda gösterilecek diyalog satırları. **`console.py`'dan taşındı.**

    Yalnız `[denetim]` ile BAŞLAYAN `role="system"` satırları süzülüyor —
    onlar denetim hükmünün kaydı, operatöre söylenmiş bir söz değil.

    Düz bir `role != "system"` süzgeci bozulmuş modu ekrandan siler:
    `Supervisor._fault`'un cevapları, `run.py`'nin `LATE_NOTICE` damgası ve
    bekleyen onay bildirimi hep `system` satırı — ve demo beat 6'da jürinin
    görmesi gereken şey tam olarak bunlar.

    Ev değişti çünkü `feed` onu `console`dan alsaydı import dairesi kapanırdı;
    kural yine tek yerde duruyor.
    """
    return [turn for turn in turns
            if not (turn.role == "system"
                    and turn.text.startswith(AUDIT_PREFIX))]

FEED_EMPTY = "Henüz kayda değer olay yok."

GREEN = "#2e7d32"
YELLOW = "#f9a825"
ORANGE = "#ef6c00"
RED = "#c62828"
UNKNOWN_COLOR = "#546e7a"
NEUTRAL = "#78909c"

RISK_COLORS = {"Düşük": GREEN, "Orta": YELLOW, "Yüksek": ORANGE,
               "Kritik": RED}

#: Ajanların ekran rozeti. Adlar İngilizce KALIYOR — sistem kimlikleri ve
#: devir defteri de aynı adları basıyor; iki ekran birbirini tutmak zorunda.
AGENT_MARKS = {"perception": "👁", "router": "🧭", "interpreter": "🔎",
               "synthesizer": "🧩", "risk_analyst": "⚖️",
               "supervisor": "🎙", "reporter": "📄",
               "operator": "👤", "system": "⚙️"}

WINDOW_FLOOR = {True: "taban=EVET", False: "taban=HAYIR"}
OUTCOME_LABELS = {"routed": "yönlendiriciye gitti",
                  "forced": "görü bütçesinden bakıldı",
                  "skipped": "hiçbir katman bakmadı"}

PROACTIVE_MARK = "🔔 [KENDİLİĞİNDEN]"
APPROVAL_LABELS = {"not_required": "otomatik", "pending": "⏸ onay bekliyor",
                   "approved": "✓ onaylandı", "rejected": "✗ reddedildi"}
ACTOR_AGENT = "supervisor"


def risk_color(level) -> str:
    """Tanınmayan seviye gerçek bir rengi ÖDÜNÇ ALMIYOR, kendi rengine düşer."""
    if level is None:
        return NEUTRAL
    return RISK_COLORS.get(level, UNKNOWN_COLOR)


class FeedEntry:
    """Beslemedeki tek girdi. Saf veri; çizim `feed_html`'in işi."""

    __slots__ = ("seq", "ts", "agent", "target", "kind", "title", "detail",
                 "risk", "confidence")

    def __init__(self, seq, ts, agent, kind, title, detail="", target=None,
                 risk=None, confidence=None):
        self.seq, self.ts, self.agent = seq, ts, agent
        self.kind, self.title, self.detail = kind, title, detail
        self.target, self.risk, self.confidence = target, risk, confidence

    def __repr__(self) -> str:                     # test okunabilirliği
        return f"FeedEntry({self.seq}, {self.agent}, {self.title!r})"


def _pairs(mapping: dict, limit: int = 3) -> str:
    """Boş bırakmak yerine tire: boş hücre "parametresiz çağrıldı" ile
    "gösterilmedi"yi aynı şeye çevirir."""
    if not mapping:
        return "—"
    items = list(mapping.items())[:limit]
    text = ", ".join(f"{key}={value}" for key, value in items)
    return text + (" …" if len(mapping) > limit else "")


def _window_entry(entry: JournalEntry, record) -> FeedEntry:
    detail = (f"{record.frames} kare · kişi≤{record.person_peak} · "
              f"kutu={record.detections} · "
              f"{', '.join(record.labels) or 'tespit yok'}")
    return FeedEntry(
        entry.seq, record.ts, "perception", "window",
        f"Pencere {record.index}/{record.total} "
        f"({mmss(record.ts)}–{mmss(record.end_ts)}) — "
        f"{WINDOW_FLOOR[record.floor_passed]}",
        f"{detail} · {OUTCOME_LABELS.get(record.outcome, record.outcome)}")


def _dialogue_entry(entry: JournalEntry, turn, previous_role) -> FeedEntry:
    if turn.role == "operator":
        return FeedEntry(entry.seq, turn.ts, "operator", "dialogue", turn.text)
    if turn.role == "system":
        return FeedEntry(entry.seq, turn.ts, "system", "dialogue", turn.text)
    # Kendinden önce operatör satırı olmayan bir süpervizör satırı kimse
    # sormadan söylenmiştir — ayrım TÜRETİLİYOR, saklanan bir bayrağa
    # dayanmıyor (`talk()` önce operatör satırını yazıyor, `escalate()`
    # hiçbir şey sormadan konuşuyor).
    mark = "" if previous_role == "operator" else f"{PROACTIVE_MARK} "
    return FeedEntry(entry.seq, turn.ts, "supervisor", "dialogue",
                     f"{mark}{turn.text}")


def build_feed(store, escalated_ids=None, archived=None) -> list:
    """Defteri `seq` sırasında gezip besleme girdilerine çevirir.

    `archived` — koşudan ÖNCE depoda duran epizot kimlikleri. `load_history`
    arşiv fikstürlerini epizot olarak yazıyor ve onlar bu videonun olayı
    değil; beslemede "sentezleyici olay açtı" diye görünürlerse ekran
    olmamış bir şey iddia eder (`run.py:246` aynı korumayı risk biçmesi için
    yapıyor).

    `escalated_ids` yükseltilen epizotları işaretliyor — kart o girdinin
    üstünde basılıyor. `None` geçilirse hiçbir şey işaretlenmiyor:
    "bilmiyorum"un güvenli yorumu abartmak değil susmaktır.
    """
    skip = set(archived or ())
    escalated = set(escalated_ids or ())

    windows = {r.id: r for r in store.window_records()}
    handoffs = {h.id: h for h in store.handoffs()}
    interpretations = {i.id: i for i in store.interpretations()}
    episodes = {e.id: e for e in store.episodes()}
    risks = {r.id: r for r in store.risks()}
    actions = {a.id: a for a in store.actions()}
    visible = {t.id: t for t in visible_dialogue(store.dialogue())}

    entries, previous_role = [], None
    for entry in store.journal():
        made = None
        if entry.source == "window_record":
            record = windows.get(entry.row_id)
            made = _window_entry(entry, record) if record else None
        elif entry.source == "handoff":
            handoff = handoffs.get(entry.row_id)
            if handoff:
                made = FeedEntry(
                    entry.seq, handoff.ts, handoff.source_agent, "handoff",
                    f"{handoff.source_agent} → {handoff.target_agent}",
                    handoff.reason, target=handoff.target_agent,
                    confidence=handoff.confidence)
        elif entry.source == "interpretation":
            reading = interpretations.get(entry.row_id)
            if reading:
                beats = " · ".join(b.text for b in reading.beats)
                made = FeedEntry(entry.seq, reading.observation_ts,
                                 "interpreter", "interpretation",
                                 reading.description, beats)
        elif entry.source == "episode":
            episode = episodes.get(entry.row_id)
            snapshot = entry.snapshot or {}
            if episode and entry.row_id not in skip:
                # `update_episode`'un iki çağıranı var ve ikisi AYRI şeyler
                # yapıyor: sentezleyici kaynaştırıyor, süpervizör operatörün
                # sözüyle özeti DÜZELTİYOR. Tek satıra düşerlerse insan
                # müdahalesi model çıktısı gibi görünür.
                origin = snapshot.get("origin", "synthesizer")
                if entry.kind == "create":
                    kind, note = "episode", "Olay açıldı"
                elif origin == "supervisor":
                    kind, note = "episode_update", "Özet düzeltildi"
                else:
                    kind, note = "episode_update", "Olaya eklendi"
                made = FeedEntry(
                    entry.seq, snapshot.get("start_ts", episode.start_ts),
                    origin, kind,
                    snapshot.get("summary_tr", episode.summary_tr), note,
                    risk=snapshot.get("preliminary_risk",
                                      episode.preliminary_risk))
                # Yükseltme çapası `create` ile SINIRLI DEĞİL: açık bir
                # epizotta `escalate` `_resolve` ile kaynaşmaya iniyor
                # (`loop.py:288`) ve o an bir `update` satırı doğuruyor.
                # Kart, epizodun beslemedeki SON satırına iliştiriliyor.
                if entry.row_id in escalated:
                    made.kind = "escalation"
        elif entry.source == "risk":
            risk = risks.get(entry.row_id)
            episode = episodes.get(risk.episode_id) if risk else None
            if risk:
                proposed = " · ".join(a.tool_name
                                      for a in risk.proposed_actions)
                made = FeedEntry(
                    entry.seq, episode.start_ts if episode else 0.0,
                    "risk_analyst", "risk", risk.rationale_tr,
                    f"önerilen: {proposed}" if proposed else "",
                    risk=risk.level)
        elif entry.source == "dialogue":
            turn = visible.get(entry.row_id)
            if turn:
                made = _dialogue_entry(entry, turn, previous_role)
            # Rol izleme GÖRÜNMEYEN satırları da sayıyor: denetim satırı
            # araya girse bile "kendinden önce operatör var mıydı" sorusunun
            # cevabı değişmemeli.
            all_turn = next((t for t in store.dialogue()
                             if t.id == entry.row_id), None)
            previous_role = all_turn.role if all_turn else previous_role
        elif entry.source == "action":
            action = actions.get(entry.row_id)
            if action and entry.kind == "create":
                # Onaylı bir araç ÜÇ satır doğuruyor: ajanın `pending`
                # çağrısı, operatörün ikinci `call_tool`u (`supervisor.py:466`)
                # ve onay güncellemesi. Üçünü de basmak bir kez çağrılan
                # aracı üç kez çağrılmış gibi gösterir — ikinci `create`
                # atlanıyor, karar onay satırında zaten görünüyor.
                twin = any(
                    other.tool_name == action.tool_name
                    and other.ts == action.ts
                    and other.actor == "agent"
                    and (other.id or 0) < (action.id or 0)
                    for other in actions.values())
                if action.actor == "operator" and twin:
                    made = None
                else:
                    state = (entry.snapshot or {}).get("approval",
                                                       action.approval)
                    made = FeedEntry(
                        entry.seq, action.ts,
                        ACTOR_AGENT if action.actor == "agent" else "operator",
                        "action", action.tool_name,
                        f"parametre: {_pairs(action.params)} · "
                        f"sonuç: {_pairs(action.result)} · "
                        f"{APPROVAL_LABELS.get(state, state)}")
            elif action:
                state = (entry.snapshot or {}).get("approval", action.approval)
                made = FeedEntry(
                    entry.seq, action.ts, "operator", "approval",
                    f"{action.tool_name} — "
                    f"{APPROVAL_LABELS.get(state, state)}")
        elif entry.source == "correction":
            made = None                  # düzeltmeler epizot güncellemesinde
        # Tanınmayan `source` SUSARAK atlanıyor: yeni bir tablo eklenip
        # eşleme unutulursa besleme uydurmak yerine susar.
        if made is not None:
            entries.append(made)
    return entries


def _entry_html(entry) -> str:
    color = risk_color(entry.risk)
    mark = AGENT_MARKS.get(entry.agent, "•")
    who = html.escape(entry.agent)
    if entry.target:
        who = f"{who} <b>→</b> {html.escape(entry.target)}"
    meta = [f"{mark} {who}"]
    if entry.confidence is not None:
        meta.append(f"güven {entry.confidence:.2f}")
    if entry.risk:
        meta.append(f"<span style='color:{color};font-weight:600'>"
                    f"{html.escape(entry.risk)}</span>")
    detail = (f"<div style='opacity:.75;margin-top:.15rem'>"
              f"{html.escape(entry.detail)}</div>" if entry.detail else "")
    # `gr.Chatbot` baloncukları kalktı ve şartname §7 "metin tabanlı
    # etkileşim NET görünmeli" diyor: operatör ile süpervizör beslemede
    # birbirinden bakışta ayrılmak zorunda, yoksa puanlanan bir kalem
    # zayıflar. Operatör satırı girintili ve kendi zeminiyle duruyor.
    highlight = ("background:rgba(198,40,40,.08);"
                 if entry.kind == "escalation"
                 else "background:rgba(120,144,156,.10);margin-left:2rem;"
                 if entry.agent == "operator" else "")
    return (
        f"<div style='border-left:6px solid {color};{highlight}"
        f"padding:.35rem .6rem;margin:.25rem 0'>"
        f"<div style='display:flex;gap:.6rem;align-items:baseline;"
        f"font-size:.82em;opacity:.8'>"
        f"<b>{html.escape(mmss(entry.ts))}</b>"
        f"<span>{' &nbsp;·&nbsp; '.join(meta)}</span></div>"
        f"<div style='margin-top:.1rem'>{html.escape(entry.title)}</div>"
        f"{detail}</div>")


def feed_html(entries: list) -> str:
    """Beslemenin HTML'i.

    Kap `column-reverse` ve girdiler DOM'a **yeniden eskiye** yazılıyor.
    Ekran kalp atışında bütünüyle yeniden çiziliyor; düz bir kaydırma kutusu
    her çizimde tepeye zıplar ve okunamaz. `column-reverse`'te tarayıcı
    kaydırmayı flex başlangıcına — görsel olarak alta — sabitliyor ve
    yeniden çizimde orada kalıyor. Tarayıcıda ölçüldü: üç ardışık tam
    `innerHTML` değişiminde `scrollTop` 0 kaldı ve alt kenardaki girdi her
    seferinde en yeni olan oldu.
    """
    if not entries:
        return f"<p style='opacity:.7'>{FEED_EMPTY}</p>"
    items = "".join(_entry_html(entry) for entry in reversed(entries))
    return (f"<div style='display:flex;flex-direction:column-reverse;"
            f"max-height:52vh;overflow-y:auto;padding:.2rem'>{items}</div>")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_feed.py -q`

- [ ] **Step 5: Commit**

```bash
git add gozcu/ui/feed.py tests/test_feed.py
git commit -m "feat(ui): besleme katmanı — oluş sırasında, ajan atıflı tek akış"
```

---

### Task 5: Konsol — iki sekme

**Files:**
- Modify: `gozcu/ui/console.py`
- Test: `tests/test_console.py`

**Interfaces:**
- Consumes: `feed.build_feed`, `feed.feed_html`, `feed.FEED_EMPTY`
- Produces: `SCREEN_SLOTS = 13`, yeni `SLOT` haritası, `build()` iki sekme.

- [ ] **Step 1: Write the failing test**

`tests/test_console.py`'de `SCREEN_SLOTS`/`SLOT` bekleyen mevcut testleri
güncelle ve şunları ekle:

```python
def test_the_console_has_exactly_two_tabs():
    """Beş sekme sistemin işini KAYNAĞINA göre bölüyordu; ikisi zamana göre
    bölüyor: olan biten (CANLI) ve teslim edilen (RAPOR)."""
    import gradio as gr
    from gozcu.ui.console import build

    demo = build()
    tabs = [block.label for block in demo.blocks.values()
            if isinstance(block, gr.Tab)]
    assert tabs == ["CANLI", "RAPOR"]


def test_every_slot_has_a_name_and_the_count_matches():
    from gozcu.ui.console import SCREEN_SLOTS, SLOT

    assert len(SLOT) == SCREEN_SLOTS == 13
    assert sorted(SLOT.values()) == list(range(SCREEN_SLOTS))
    assert "feed" in SLOT
    assert "timeline" not in SLOT and "chat" not in SLOT


def test_the_blank_screen_fills_every_slot():
    """Eksik bir çıktı Gradio'da hata vermiyor — o bileşen sessizce
    tazelenmiyor."""
    from gozcu.ui.console import SCREEN_SLOTS, _blank

    assert len(_blank("hazır")) == SCREEN_SLOTS


def test_the_refresh_fills_every_slot_and_puts_the_feed_where_slot_says():
    from gozcu.ui.console import SCREEN_SLOTS, SLOT, Session, _refresh

    session = Session()
    session.store.save_dialogue(DialogueTurn(ts=1.0, role="supervisor",
                                             text="dikkat"))
    drawn = _refresh(session, "koşuyor")
    assert len(drawn) == SCREEN_SLOTS
    assert "dikkat" in drawn[SLOT["feed"]]


def test_the_feed_skips_episodes_that_were_in_the_store_before_the_run():
    """`Session` arşiv kimliklerini kuruluşta alıyor."""
    from gozcu.ui.console import Session, _refresh, SLOT

    session = Session()
    session.store.create_episode(Episode(start_ts=0.0, phase="outcome",
                                         summary_tr="geçen ayki kaza",
                                         preliminary_risk="Yüksek",
                                         state="closed"))
    session.archived = {e.id for e in session.store.episodes()}
    assert "geçen ayki kaza" not in _refresh(session, "koşuyor")[SLOT["feed"]]
```

`chat_messages` testlerini sil (bileşen kalkıyor); `visible_dialogue`
testleri **kalıyor** — kural beslemeye taşındı ve hâlâ `console.py`'da.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_console.py -q`
Expected: FAIL — `assert tabs == ["CANLI", "RAPOR"]` beş etiket buluyor;
`SCREEN_SLOTS == 13` 15 buluyor.

- [ ] **Step 3: Write minimal implementation**

`gozcu/ui/console.py`:

1. `from gozcu.ui.feed import FEED_EMPTY, build_feed, feed_html` ekle.
2. `timeline_rows`, `timeline_html`, `chat_messages`, `intervention_html`,
   `TIMELINE_EMPTY` **sil**. `intervention_card`, `_card_row`, `_tool_line`,
   `visible_dialogue`, `tool_rows`, `tool_summary`, `handoff_rows`, KPI
   fonksiyonları **kalıyor**.
3. Yuvalar:

```python
#: Ekranın yuva sayısı — her işleyici tam bu kadar değer döndürmek zorunda.
#: Eksik bir çıktı Gradio'da hata vermiyor, o bileşen sessizce tazelenmiyor.
#: 26 Ağustos: 15 → 13. `timeline` → `feed`; `chat` ve `interventions`
#: beslemenin içine girdiği için kalktı.
SCREEN_SLOTS = 13

SLOT = {name: index for index, name in enumerate([
    "session", "badges", "feed", "approval_box", "approval_text", "ledger",
    "tool_count", "tools", "kpi", "payload", "report", "state", "note"])}
```

4. `Session.__init__` sonuna:

```python
        #: Koşudan ÖNCE depoda duran epizotlar — `load_history` arşivi.
        #: Beslemeye girmiyorlar: bu videonun olayı değiller.
        self.archived = {episode.id for episode in self.store.episodes()}
        #: En son çizilen besleme HTML'i — aynıysa bileşen atlanıyor, yoksa
        #: jürinin yukarı kaydırması her saniye bozulur (bkz. `_feed_slot`).
        self.last_feed: str | None = None
```

5. `_refresh` ve `_blank`:

```python
def _refresh(session: Session, state: str, note: str = ""):
    pending = _pending(session)
    return (session,
            status_badges(session.gw, session.store),
            _feed_slot(session),
            gr.update(visible=pending is not None),
            approval_text(pending),
            handoff_rows(session.store.handoffs()),
            tool_summary(session.store.actions()),
            tool_rows(session.store.actions()),
            kpi_markdown(session.store, session.elapsed_s()),
            payload_json(session.output),
            root_cause_markdown(session.output),
            state,
            note)


def _feed_slot(session: Session):
    """Besleme yuvası — dize değişmediyse bileşeni HİÇ güncellemez.

    `column-reverse` kaydırıcı her yeniden çizimde SIFIRDAN doğuyor ve
    `scrollTop = 0` ile, yani görsel altta başlıyor. İstenen sonuç bu, ama
    bedeli şu: jüri geçmişi okumak için yukarı kaydırdıysa bir sonraki kalp
    atışı onu en alta geri atar. `gr.skip()` bunu kapatıyor — kaydırma
    yalnız gerçekten yeni bir girdi düştüğünde sıfırlanıyor.

    `feed_html` bu yüzden kesinlikle deterministik olmak zorunda: çizim anı
    ya da duvar saati dizeye girerse atlama hiç çalışmaz.
    """
    drawn = feed_html(build_feed(session.store, session.escalated_ids(),
                                 session.archived))
    if drawn == session.last_feed:
        return gr.skip()
    session.last_feed = drawn
    return drawn


def _blank(state: str):
    return (None, "", feed_html([]), gr.update(visible=False), "", [],
            tool_summary([]), [], perception_markdown(), NO_RUN_YET,
            NO_RUN_YET, state, "")
```

6. `build()` — sekmeler:

```python
        with gr.Tabs():
            with gr.Tab("CANLI"):
                # TEK kolon: video ve kontroller yukarıda sabit, besleme
                # altta kendi içinde kayıyor. Besleme `column-reverse`
                # olduğu için kalp atışı yeniden çizimlerinde en yeni
                # girdide sabit kalıyor (bkz. `feed.feed_html`).
                video = gr.Video(label="Kamera kaydı")
                with gr.Row():
                    start_btn = gr.Button("Analizi başlat", variant="primary")
                    resume_btn = gr.Button("Devam et",
                                           visible=STEP_MODE_DEFAULT)
                    cut_btn = gr.Button("Bağlantıyı kes", variant="stop")
                    restore_btn = gr.Button("Bağlantıyı geri ver")
                step_toggle = gr.Checkbox(
                    value=STEP_MODE_DEFAULT,
                    label="Adım adım (kritik anda dur)",
                    info="Kapalıyken koşu durmaz; müdahale anları beslemede "
                         "kart olarak kaydedilir.")
                with gr.Row():
                    stress_buttons = {
                        key: gr.Button(label, size="sm")
                        for key, (label, _) in STRESS_PROMPTS.items()}
                with gr.Row():
                    operator_text = gr.Textbox(
                        placeholder="Operatör mesajı…", show_label=False,
                        scale=5)
                    send_btn = gr.Button("Gönder", scale=1)
                with gr.Group(visible=False) as approval_box:
                    approval_box_text = gr.Markdown("")
                    with gr.Row():
                        approve_btn = gr.Button("Onayla", variant="primary")
                        reject_btn = gr.Button("Reddet", variant="stop")
                approval_note = gr.Markdown("")
                feed = gr.HTML(feed_html([]))

            with gr.Tab("RAPOR"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Teslim edilen yük (dört anahtar)")
                        payload = gr.Code(value=NO_RUN_YET, language="json",
                                          label="JSON")
                    with gr.Column():
                        gr.Markdown("### Kök neden raporu")
                        report = gr.Markdown(NO_RUN_YET)
                gr.Markdown("### KPI — şartname §4")
                kpi = gr.Markdown(perception_markdown())
                # Besleme anlatı, bu iki tablo TAM KAYIT. Şartname §7 "mock
                # fonksiyonların ajanın araçları olarak kullanımı"nı doğrudan
                # puanlıyor ve jüri sayılabilir bir tablo istiyor.
                gr.Markdown("### Çağrılan saha araçları")
                tool_count = gr.Markdown(tool_summary([]))
                tools = gr.Dataframe(headers=TOOL_HEADERS, value=[],
                                     interactive=False, wrap=True)
                gr.Markdown("### Devir defteri")
                ledger = gr.Dataframe(headers=HANDOFF_HEADERS, value=[],
                                      interactive=False, wrap=True)

        screen = [session, badges, feed, approval_box, approval_box_text,
                  ledger, tool_count, tools, kpi, payload, report, state_box,
                  approval_note]
```

Bağlantılar (`start_btn.click` vb.) aynen kalıyor — `screen` listesi
değiştiği için ayrıca dokunmak gerekmiyor.

7. `build()` docstring'ini güncelle: sekme sayısı ve gerekçe.

8. `STATE_INTERVENED` artık olmayan bir sekmeyi işaret ediyor
   (`"kart **Müdahaleler** bölümünde"`). Metni düzelt:

```python
STATE_INTERVENED = ("⚠ **Müdahale anı kaydedildi.** Gerçek zamanlı bir "
                    "kurulumda ajan burada devreye girerdi; kart canlı "
                    "beslemede, olduğu anda. Video akmaya devam ediyor.")
```

9. Modül docstring'indeki *"Depoda kilit yok"* bölümü artık YANLIŞ — Task 1
   kilidi ekledi. O paragrafı düzelt: depo kilitli, tazeleme yine olay
   anlarında ve saniyelik kalp atışında.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/ -q` — **hepsi** yeşil olmalı.

- [ ] **Step 5: Commit**

```bash
git add gozcu/ui/console.py tests/test_console.py
git commit -m "feat(konsol): beş sekme yerine iki — CANLI besleme ve RAPOR"
```

---

### Task 6: Kaydetme

Bir görev, görev dosyası ve karar günlüğü onu söyleyene kadar bitmiş değil.

**Files:**
- Create: `docs/tasks/19-canli-akis.md`
- Modify: `docs/tasks/README.md`, `docs/05-decisions/decision-log.md`

**Interfaces:**
- Consumes: Task 1–5.
- Produces: —

- [ ] **Step 1: Görev dosyası**

`docs/tasks/19-canli-akis.md` — başında tamamlanma bandı
(`✅ TAMAMLANDI — 26 Ağustos 2026, <commit>`), bağlam, ne değişti, kabul
kutuları işaretli, ve **"Tamamlanma notları (gelecek görevleri bağlayan)"**:

- `Store` artık kilitli; yeni bir yazma metodu eklerken `with self._lock:`
  altına alınacak, yoksa çift `lastrowid` geri gelir.
- Beslemeye yeni bir kayıt türü eklemek = `build_feed`'e bir dal. Dal
  eklenmezse tür **sessizce görünmez** (tanınmayan `source` atlanıyor).
- `SLOT` haritası ile `build()`'deki `screen` listesi aynı sırayı paylaşıyor;
  yeni yuva ikisine birden eklenecek.

- [ ] **Step 2: Görev tablosu**

`docs/tasks/README.md` tablosuna satır: `| 19 | Canlı akış konsolu | 16 | ✅ 26 Ağu |`

- [ ] **Step 3: Karar günlüğü**

`docs/05-decisions/decision-log.md`'ye üç karar:

1. **Beş sekme → iki.** Sekmeler işi kaynağına göre bölüyordu; §7'nin
   puanladığı "çok adımlı karar zincirleri" hiçbir ekranda birlikte
   görünmüyordu.
2. **Sıra `seq`, `ts` değil.** `catch_up` sonradan yazılan bir kaydı önceki
   bir saniyeye koyuyor; `ts` sıralaması onu yaşanmadığı bir geçmişe taşır.
3. **Depo kilidi.** Kilitsiz iki yazar iş parçacığı çift `lastrowid`
   veriyordu (ölçüldü). Bugüne kadar gizli bir arızaydı; defterle ölümcül.

- [ ] **Step 4: Doğrula**

```bash
.venv/bin/pytest tests/ -q
uv run python scripts/check-tasks.py
```

- [ ] **Step 5: Commit**

```bash
git add docs/
git commit -m "docs(görev 19): canlı akış konsolu kaydedildi"
```
