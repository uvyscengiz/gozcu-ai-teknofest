"""Ajanların birbirine konuştuğu olay deposu.

Ajan sınırını geçen her kayıt buraya tipli olarak yazılır; serbest metin
geçmez. Model başına bir tablo, iç içe yapılar JSON `payload` sütununda.
Sorgulanan alanlar (ts, state, episode_id) ayrı sütuna da kopyalanır.
"""

import json
import sqlite3
import threading
from pathlib import Path

from gozcu.models import (ActionPlan, ActionRecord, Correction, DialogueTurn,
                          Episode, Handoff, Interpretation, JournalEntry,
                          Observation, RiskAssessment, WindowRecord)

SCHEMA = """
CREATE TABLE IF NOT EXISTS observation (id INTEGER PRIMARY KEY, ts REAL, payload TEXT);
CREATE TABLE IF NOT EXISTS interpretation (id INTEGER PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS episode (id INTEGER PRIMARY KEY, state TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS episode_embedding (episode_id INTEGER PRIMARY KEY, vector TEXT);
CREATE TABLE IF NOT EXISTS risk (id INTEGER PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS handoff (id INTEGER PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS action (id INTEGER PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS action_plan (id INTEGER PRIMARY KEY, payload TEXT);
CREATE TABLE IF NOT EXISTS correction (id INTEGER PRIMARY KEY, episode_id INTEGER, payload TEXT);
CREATE TABLE IF NOT EXISTS dialogue (id INTEGER PRIMARY KEY, payload TEXT);
-- Tablo adı `window` DEĞİL: `window` SQLite 3.25+'ta anahtar kelime
-- (pencere fonksiyonları) ve tırnaksız kullanılamaz.
CREATE TABLE IF NOT EXISTS window_record (id INTEGER PRIMARY KEY, ts REAL, payload TEXT);
CREATE TABLE IF NOT EXISTS journal (seq INTEGER PRIMARY KEY AUTOINCREMENT,
                                    source TEXT, row_id INTEGER, kind TEXT,
                                    snapshot TEXT);
"""


def _episode_snapshot(episode: Episode, origin: str) -> dict:
    """Beslemenin epizottan bastığı alanlar — hepsi bu, fazlası defteri şişirir.

    `end_ts` DAHİL: epizodun bitişi sonraki her kaynaşmada ileri kayıyor ve
    damga canlı satırdan okunursa erken bir girdi olayın SONUNDAKİ bitişini
    gösterir — anlık görüntünün önlemek için var olduğu kaymanın ta kendisi.

    `origin` `update_episode`'un iki çağıranını ayırıyor: sentezleyici
    kaynaştırıyor, süpervizör operatörün sözüyle özeti DÜZELTİYOR. Tek satıra
    düşerlerse insan müdahalesi model çıktısı gibi görünür.

    `beats` DE dahil: epizot kendi içinde bir zaman çizelgesi taşıyor ve
    besleme onu tek satıra düşürürse operatör olayın SEYRİNİ göremez —
    yalnız pencerenin sınırını görür. Anlık görüntüde durmaları şart, çünkü
    kaynaşma her pencerede yeni an ekliyor: canlı okunursa koşunun
    başındaki bir girdi olayın sonunda öğrenilen anları gösterir.
    """
    return {"summary_tr": episode.summary_tr,
            "preliminary_risk": episode.preliminary_risk,
            "phase": episode.phase, "state": episode.state,
            "start_ts": episode.start_ts, "end_ts": episode.end_ts,
            "origin": origin,
            "beats": [[beat.ts, beat.text] for beat in episode.beats]}


class Store:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        #: Konsolda İKİ iş parçacığı aynı bağlantıya yazıyor: boru hattı
        #: (`run_pipeline`, ayrı thread) ve Gradio olay iş parçacığı
        #: (`nobetci.talk()`, onay kararı, `catch_up`). `sqlite3.threadsafety`
        #: 3 (serialized) tek bir `execute`i güvenli kılıyor ama iki ardışık
        #: `execute` + `lastrowid` okumasını KILMIYOR — ölçüldü: kilitsiz
        #: 400+400 yazmada aynı satır kimliği iki kez dağıtıldı ve
        #: `InterfaceError` atıldı.
        #:
        #: RLock, düz Lock değil: `create_episode` gibi genel metotlar
        #: `_insert`i, `open_episode` `_read`i çağırıyor — düz kilit kendini
        #: kilitlerdi.
        self._lock = threading.RLock()
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.db.commit()

    def _journal(self, source: str, row_id: int, kind: str,
                 snapshot: dict | None = None) -> None:
        """Deftere tek satır. Çağıranın commit'i İÇİNDE koşuyor.

        Ayrı bir commit olsaydı, ikisinin arasında düşen bir istisna tipli
        satırı beslemeye sonsuza dek görünmez bırakırdı.
        """
        self.db.execute(
            "INSERT INTO journal (source, row_id, kind, snapshot) "
            "VALUES (?, ?, ?, ?)",
            (source, row_id, kind,
             json.dumps(snapshot, ensure_ascii=False)
             if snapshot is not None else None))

    def journal(self) -> list[JournalEntry]:
        """Yazma sırası — beslemenin tek sıralama kaynağı."""
        with self._lock:
            rows = self.db.execute(
                "SELECT seq, source, row_id, kind, snapshot FROM journal "
                "ORDER BY seq").fetchall()
        return [JournalEntry(seq=seq, source=source, row_id=row_id, kind=kind,
                             snapshot=json.loads(snap) if snap else None)
                for seq, source, row_id, kind, snap in rows]

    def _insert(self, table: str, model, *, journal: bool = True,
                snapshot: dict | None = None, **columns) -> int:
        """`journal=False` yalnız gözlem için: 3 fps'te defteri boğar ve
        gözlem bir ajan sınırını geçmiyor."""
        payload = model.model_dump_json(exclude={"id"})
        names = ", ".join(["payload", *columns])
        slots = ", ".join(["?"] * (1 + len(columns)))
        with self._lock:
            try:
                cur = self.db.execute(
                    f"INSERT INTO {table} ({names}) VALUES ({slots})",
                    (payload, *columns.values()))
                row_id = cur.lastrowid
                if journal:
                    self._journal(table, row_id, "create", snapshot)
                self.db.commit()
            except Exception:
                # sqlite3 işlemleri BAĞLANTI genelinde: geri alınmazsa
                # bekleyen tipli satır bir başka thread'in commit'iyle
                # deftersiz olarak diske düşer ve beslemede sonsuza dek
                # görünmez kalır.
                self.db.rollback()
                raise
            return row_id

    def _read(self, table: str, model_type, where: str = "", *params) -> list:
        with self._lock:
            rows = self.db.execute(
                f"SELECT id, payload FROM {table} {where} ORDER BY id",
                params).fetchall()
        return [model_type(**{**json.loads(v), "id": i}) for i, v in rows]

    def save_observation(self, observation: Observation) -> int:
        # Defterlenmiyor: 3 fps'te on saniyelik bir pencere ~30 satır eder ve
        # gözlem bir ajan sınırını geçmiyor — algının ham maddesi. Beslemenin
        # algı satırı `window_record`'dan geliyor.
        return self._insert("observation", observation, ts=observation.ts,
                            journal=False)

    def observations(self) -> list[Observation]:
        return self._read("observation", Observation)

    def save_window(self, record: WindowRecord) -> int:
        # Anlık görüntü ŞART: `set_window_outcome` bu satırı YERİNDE yeniden
        # yazıyor (kesinti sonradan öğreniliyor), yani ilk satır akıbeti
        # canlı okursa "yönlendiriciye gitti" derken geriye dönük "telafiye
        # alındı" görünür — anlık görüntünün önlemek için var olduğu kayma.
        return self._insert("window_record", record, ts=record.ts,
                            snapshot={"outcome": record.outcome})

    def window_records(self) -> list[WindowRecord]:
        return self._read("window_record", WindowRecord)

    def set_window_outcome(self, window_id: int, outcome: str) -> None:
        """Pencerenin akıbetini düzeltir — kesinti sonradan öğreniliyor.

        Kayıt işleme BAŞLAMADAN yazılıyor ki beslemede algı satırı
        yönlendiriciden önce gelsin. Ama erteleme ancak görü kademesi
        düştükten sonra biliniyor. Düzeltmesiz hâlde besleme, telafi
        kuyruğuna alınmış bir pencere için "yönlendiriciye gitti" diyor —
        yani kesintiyi gizliyor, üstelik tam da onu göstermesi gereken demo
        anında.

        Deftere AYRI bir `update` satırı düşüyor: pencere gerçekten
        işlendi, sonra ertelendi ve ikisi de olmuş şeyler.
        """
        with self._lock:
            try:
                row = self.db.execute(
                    "SELECT payload FROM window_record WHERE id = ?",
                    (window_id,)).fetchone()
                record = WindowRecord(**{**json.loads(row[0]),
                                         "outcome": outcome})
                self.db.execute(
                    "UPDATE window_record SET payload = ? WHERE id = ?",
                    (record.model_dump_json(exclude={"id"}), window_id))
                self._journal("window_record", window_id, "update",
                              {"outcome": outcome})
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def save_interpretation(self, interpretation: Interpretation) -> int:
        return self._insert("interpretation", interpretation)

    def interpretations(self) -> list[Interpretation]:
        return self._read("interpretation", Interpretation)

    def create_episode(self, episode: Episode) -> int:
        return self._insert("episode", episode, state=episode.state,
                            snapshot=_episode_snapshot(episode, "anomaly_analyst"))

    def update_episode(self, episode_id: int, *,
                       origin: str = "anomaly_analyst", **fields) -> None:
        """`origin` çağıranın sorumluluğu: süpervizör özeti düzeltirken
        `origin="supervisor"` geçiyor, sentezleyici varsayılanı kullanıyor.
        İkisi beslemede AYRI satırlar — biri model çıktısı, öbürü insan
        müdahalesi."""
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

    def open_episode(self) -> Episode | None:
        """En son açılan epizot; hiç açık epizot yoksa None."""
        open_rows = self._read("episode", Episode, "WHERE state = ?", "open")
        return open_rows[-1] if open_rows else None

    def episodes(self) -> list[Episode]:
        return self._read("episode", Episode)

    def save_risk(self, risk: RiskAssessment) -> int:
        return self._insert("risk", risk)

    def risks(self) -> list[RiskAssessment]:
        return self._read("risk", RiskAssessment)

    def save_action_plan(self, plan: ActionPlan) -> int:
        return self._insert("action_plan", plan)

    def action_plans(self) -> list[ActionPlan]:
        return self._read("action_plan", ActionPlan)

    def save_handoff(self, handoff: Handoff) -> int:
        return self._insert("handoff", handoff)

    def handoffs(self) -> list[Handoff]:
        return self._read("handoff", Handoff)

    def save_action(self, action: ActionRecord) -> int:
        # Anlık görüntü ŞART: `set_action_approval` bu satırı YERİNDE yeniden
        # yazıyor, yani çağrı satırı durumu canlı okursa çağrıldığı anda
        # `pending` olan bir araç geriye dönük `onaylandı` görünür.
        return self._insert("action", action,
                            snapshot={"approval": action.approval})

    def actions(self) -> list[ActionRecord]:
        return self._read("action", ActionRecord)

    def set_action_approval(self, action_id: int, state: str) -> None:
        """Onay akışı buna dayanır: yeni satır açmaz, mevcut satırı günceller."""
        with self._lock:
            row = self.db.execute(
                "SELECT payload FROM action WHERE id = ?",
                (action_id,)).fetchone()
            action = ActionRecord(**{**json.loads(row[0]), "approval": state})
            self.db.execute("UPDATE action SET payload = ? WHERE id = ?",
                            (action.model_dump_json(exclude={"id"}), action_id))
            # AYRI bir defter girdisi: çağrının kendi satırını oynatmak onu
            # beslemede çağrıldığı andan koparırdı.
            self._journal("action", action_id, "approval", {"approval": state})
            self.db.commit()

    def save_correction(self, correction: Correction) -> int:
        return self._insert("correction", correction,
                            episode_id=correction.episode_id)

    def corrections(self, episode_id: int) -> list[Correction]:
        return self._read("correction", Correction, "WHERE episode_id = ?",
                          episode_id)

    def save_dialogue(self, turn: DialogueTurn) -> int:
        return self._insert("dialogue", turn)

    def dialogue(self) -> list[DialogueTurn]:
        return self._read("dialogue", DialogueTurn)

    def save_embedding(self, episode_id: int, vector: list[float]) -> None:
        with self._lock:
            self.db.execute(
                "INSERT OR REPLACE INTO episode_embedding VALUES (?, ?)",
                (episode_id, json.dumps(vector)))
            self.db.commit()

    def embeddings(self) -> list[tuple[int, list[float]]]:
        with self._lock:
            rows = self.db.execute(
                "SELECT episode_id, vector FROM episode_embedding").fetchall()
        return [(i, json.loads(v)) for i, v in rows]
