"""
Agent Memory — persistent investigation chain.

Prevents circular investigation by tracking:
  - Which services have already been investigated
  - Which tools have been called with which parameters
  - Previous findings and conclusions
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Optional


class AgentMemory:
    """Long/short-term memory for diagnosis sessions."""

    def __init__(self, db_path: str = "agent_memory.db"):
        self._lock = threading.Lock()
        self._db_path = db_path
        self._init_db()
        # Short-term (per-session)
        self._sessions: dict[str, dict[str, Any]] = {}

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS investigation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                diagnosis_id TEXT,
                step_number INTEGER,
                thought TEXT,
                action TEXT,
                action_input TEXT,
                observation TEXT,
                evidence_log_ids TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS past_diagnoses (
                diagnosis_id TEXT PRIMARY KEY,
                root_cause TEXT,
                summary TEXT,
                confidence REAL,
                evidence TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    # ── Short-term (per session) ──────────────────────────────────────────
    def init_session(self, diagnosis_id: str):
        self._sessions[diagnosis_id] = {
            "investigated_services": set(),
            "called_tools": [],
            "findings": [],
            "step_count": 0,
        }

    def get_session(self, diagnosis_id: str) -> Optional[dict]:
        return self._sessions.get(diagnosis_id)

    def record_step(
        self,
        diagnosis_id: str,
        thought: str,
        action: str,
        action_input: dict,
        observation: str,
        evidence_log_ids: list[str],
    ):
        session = self._sessions.get(diagnosis_id)
        if not session:
            self.init_session(diagnosis_id)
            session = self._sessions[diagnosis_id]

        session["step_count"] += 1
        step_number = session["step_count"]

        # Track what we've investigated
        if action_input.get("service"):
            session["investigated_services"].add(action_input["service"])
        session["called_tools"].append({
            "action": action,
            "input": action_input,
        })

        # Persist to SQLite
        with self._lock:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    "INSERT INTO investigation_history VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        diagnosis_id,
                        step_number,
                        thought,
                        action,
                        json.dumps(action_input),
                        observation[:2000],  # Truncate long observations
                        json.dumps(evidence_log_ids),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    def has_investigated(self, diagnosis_id: str, service: str) -> bool:
        """Check if a service has already been investigated in this session."""
        session = self._sessions.get(diagnosis_id, {})
        return service in session.get("investigated_services", set())

    def get_investigation_summary(self, diagnosis_id: str) -> str:
        """Build a summary of what has been investigated so far."""
        session = self._sessions.get(diagnosis_id)
        if not session:
            return "No investigation history."

        parts = [
            f"Steps taken: {session['step_count']}",
            f"Services investigated: {', '.join(session['investigated_services']) or 'none'}",
            f"Tools called: {len(session['called_tools'])}",
        ]
        return " | ".join(parts)

    # ── Long-term (cross-session) ─────────────────────────────────────────
    def save_diagnosis(self, diagnosis_id: str, root_cause: str, summary: str,
                       confidence: float, evidence: list[dict]):
        with self._lock:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    "INSERT OR REPLACE INTO past_diagnoses VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        diagnosis_id,
                        root_cause,
                        summary,
                        confidence,
                        json.dumps(evidence),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    def get_similar_past_diagnoses(self, description: str, limit: int = 5) -> list[dict]:
        """Retrieve past diagnoses that might be relevant."""
        with self._lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.execute(
                    "SELECT * FROM past_diagnoses ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
                results = []
                for row in cursor:
                    results.append({
                        "diagnosis_id": row[0],
                        "root_cause": row[1],
                        "summary": row[2],
                        "confidence": row[3],
                        "evidence": json.loads(row[4]) if row[4] else [],
                        "created_at": row[5],
                    })
                conn.close()
                return results
            except Exception:
                return []


# Singleton
_memory: AgentMemory | None = None


def get_agent_memory() -> AgentMemory:
    global _memory
    if _memory is None:
        _memory = AgentMemory()
    return _memory
