"""
In-memory log database with SQLite persistence.

For Phase 1 we keep logs in memory for fast access and also persist
to a SQLite file so they survive restarts.
"""

import json
import sqlite3
import threading
from typing import Any, Optional

from app.models.log_entry import LogEntry


class LogDatabase:
    """Thread-safe in-memory + SQLite log store."""

    def __init__(self, db_path: str = "sentinel_logs.db"):
        self._lock = threading.Lock()
        self._logs: list[dict[str, Any]] = []
        self._by_id: dict[str, dict[str, Any]] = {}
        self._db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id TEXT PRIMARY KEY,
                timestamp TEXT,
                service TEXT,
                level TEXT,
                message TEXT,
                stack_trace TEXT,
                extra TEXT
            )
        """)
        conn.commit()
        # Load existing logs into memory
        cursor = conn.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 10000")
        for row in cursor:
            entry = {
                "log_id": row[0],
                "timestamp": row[1],
                "service": row[2],
                "level": row[3],
                "message": row[4],
                "stack_trace": row[5],
                "extra": json.loads(row[6]) if row[6] else {},
            }
            self._logs.append(entry)
            self._by_id[entry["log_id"]] = entry
        conn.close()

    def add(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self._logs.append(entry)
            self._by_id[entry["log_id"]] = entry
            # Persist
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    "INSERT OR IGNORE INTO logs VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        entry["log_id"],
                        entry.get("timestamp", ""),
                        entry.get("service", ""),
                        entry.get("level", ""),
                        entry.get("message", ""),
                        entry.get("stack_trace"),
                        json.dumps(entry.get("extra", {})),
                    ),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass  # Non-critical — memory store is source of truth

    def get_by_id(self, log_id: str) -> Optional[dict[str, Any]]:
        return self._by_id.get(log_id)

    def query(
        self,
        service: Optional[str] = None,
        level: Optional[str] = None,
        limit: int = 100,
        search: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        results = self._logs
        if service:
            results = [r for r in results if r.get("service") == service]
        if level:
            results = [r for r in results if r.get("level") == level.upper()]
        if search:
            search_lower = search.lower()
            results = [r for r in results if search_lower in r.get("message", "").lower()]
        return results[-limit:]  # Most recent first

    def stats(self) -> dict[str, Any]:
        by_service: dict[str, int] = {}
        by_level: dict[str, int] = {}
        for log in self._logs:
            svc = log.get("service", "unknown")
            lvl = log.get("level", "unknown")
            by_service[svc] = by_service.get(svc, 0) + 1
            by_level[lvl] = by_level.get(lvl, 0) + 1
        return {
            "total_logs": len(self._logs),
            "by_service": by_service,
            "by_level": by_level,
            "latest_timestamp": self._logs[-1]["timestamp"] if self._logs else None,
        }

    def count(self) -> int:
        return len(self._logs)


# Singleton
_db: LogDatabase | None = None


def get_log_database() -> LogDatabase:
    global _db
    if _db is None:
        _db = LogDatabase()
    return _db
