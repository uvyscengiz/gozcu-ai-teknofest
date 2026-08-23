"""Ajanların birbirine konuştuğu olay deposu.

Ajan sınırını geçen her kayıt buraya tipli olarak yazılır; serbest metin
geçmez. Model başına bir tablo, iç içe yapılar JSON `payload` sütununda.
Sorgulanan alanlar (ts, state, episode_id) ayrı sütuna da kopyalanır.
"""

import json
import sqlite3
from pathlib import Path

from gozcu.models import (ActionRecord, Correction, DialogueTurn, Episode,
                          Handoff, Interpretation, Observation, RiskAssessment)

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
        slots = ", ".join(["?"] * (1 + len(columns)))
        cur = self.db.execute(
            f"INSERT INTO {table} ({names}) VALUES ({slots})",
            (payload, *columns.values()))
        self.db.commit()
        return cur.lastrowid

    def _read(self, table: str, model_type, where: str = "", *params) -> list:
        rows = self.db.execute(
            f"SELECT id, payload FROM {table} {where} ORDER BY id", params)
        return [model_type(**{**json.loads(v), "id": i}) for i, v in rows]

    def save_observation(self, observation: Observation) -> int:
        return self._insert("observation", observation, ts=observation.ts)

    def observations(self) -> list[Observation]:
        return self._read("observation", Observation)

    def save_interpretation(self, interpretation: Interpretation) -> int:
        return self._insert("interpretation", interpretation)

    def interpretations(self) -> list[Interpretation]:
        return self._read("interpretation", Interpretation)

    def create_episode(self, episode: Episode) -> int:
        return self._insert("episode", episode, state=episode.state)

    def update_episode(self, episode_id: int, **fields) -> None:
        row = self.db.execute(
            "SELECT payload FROM episode WHERE id = ?", (episode_id,)).fetchone()
        episode = Episode(**{**json.loads(row[0]), **fields})
        self.db.execute("UPDATE episode SET payload = ?, state = ? WHERE id = ?",
                        (episode.model_dump_json(exclude={"id"}), episode.state,
                         episode_id))
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

    def save_handoff(self, handoff: Handoff) -> int:
        return self._insert("handoff", handoff)

    def handoffs(self) -> list[Handoff]:
        return self._read("handoff", Handoff)

    def save_action(self, action: ActionRecord) -> int:
        return self._insert("action", action)

    def actions(self) -> list[ActionRecord]:
        return self._read("action", ActionRecord)

    def set_action_approval(self, action_id: int, state: str) -> None:
        """Onay akışı buna dayanır: yeni satır açmaz, mevcut satırı günceller."""
        row = self.db.execute(
            "SELECT payload FROM action WHERE id = ?", (action_id,)).fetchone()
        action = ActionRecord(**{**json.loads(row[0]), "approval": state})
        self.db.execute("UPDATE action SET payload = ? WHERE id = ?",
                        (action.model_dump_json(exclude={"id"}), action_id))
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
        self.db.execute(
            "INSERT OR REPLACE INTO episode_embedding VALUES (?, ?)",
            (episode_id, json.dumps(vector)))
        self.db.commit()

    def embeddings(self) -> list[tuple[int, list[float]]]:
        return [(i, json.loads(v)) for i, v in
                self.db.execute("SELECT episode_id, vector FROM episode_embedding")]
