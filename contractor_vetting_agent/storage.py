"""Persistent Session State, Audit Trail, and Dossier Database.

Provides reliable persistence for conversation turns, contractor vetting dossiers,
compliance certificates, and immutable audit logs across sessions.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DATABASE_PATH
from .telemetry import PIIRedactionService, get_structured_logger

logger = get_structured_logger("contractor_vetting.storage")


class PersistentVettingStore:
    """Relational SQLite database managing persistent sessions, dossiers, and audit trails."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DATABASE_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        """Initialize relational database schemas if not present."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    contractor_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    context_summary TEXT
                )
            """)

            # Conversational turns table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS turns (
                    turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)

            # Vetting dossiers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dossiers (
                    dossier_id TEXT PRIMARY KEY,
                    contractor_id TEXT NOT NULL,
                    contractor_name TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    composite_risk_score INTEGER NOT NULL,
                    risk_level TEXT NOT NULL,
                    pillar_scores TEXT NOT NULL,
                    audit_hash TEXT NOT NULL,
                    certificate_text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # Immutable audit trail table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    contractor_id TEXT,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    details TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()

    def create_or_get_session(self, session_id: str, contractor_id: Optional[str] = None) -> Dict[str, Any]:
        """Create or retrieve a persistent session."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)

            cursor.execute(
                """INSERT INTO sessions (session_id, contractor_id, created_at, updated_at, status, context_summary)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, contractor_id or "", now_iso, now_iso, "ACTIVE", "")
            )
            conn.commit()
            return {
                "session_id": session_id,
                "contractor_id": contractor_id or "",
                "created_at": now_iso,
                "updated_at": now_iso,
                "status": "ACTIVE",
                "context_summary": ""
            }

    def save_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Persist a conversation turn with PII scrubbing."""
        clean_content = PIIRedactionService.redact_text(content)
        clean_tools = PIIRedactionService.redact_data(tool_calls or [])
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO turns (session_id, role, content, tool_calls, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, role, clean_content, json.dumps(clean_tools), now_iso)
            )
            cursor.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now_iso, session_id)
            )
            conn.commit()

    def get_session_history(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve chronological conversational history for a session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT role, content, tool_calls, timestamp FROM turns
                   WHERE session_id = ? ORDER BY turn_id ASC LIMIT ?""",
                (session_id, limit)
            )
            rows = cursor.fetchall()
            history = []
            for r in rows:
                history.append({
                    "role": r["role"],
                    "content": r["content"],
                    "tool_calls": json.loads(r["tool_calls"]) if r["tool_calls"] else [],
                    "timestamp": r["timestamp"],
                })
            return history

    def update_session_summary(self, session_id: str, summary: str) -> None:
        """Update compacted context summary for a session."""
        clean_summary = PIIRedactionService.redact_text(summary)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sessions SET context_summary = ?, updated_at = ? WHERE session_id = ?",
                (clean_summary, now_iso, session_id)
            )
            conn.commit()

    def save_dossier(self, dossier_data: Dict[str, Any]) -> str:
        """Save a certified vetting dossier into permanent database."""
        now_iso = datetime.now(timezone.utc).isoformat()
        dossier_id = dossier_data["dossier_id"]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO dossiers
                   (dossier_id, contractor_id, contractor_name, decision,
                    composite_risk_score, risk_level, pillar_scores, audit_hash, certificate_text, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    dossier_id,
                    dossier_data["contractor_id"],
                    dossier_data["contractor_name"],
                    str(dossier_data["final_decision"]),
                    dossier_data["composite_risk_score"],
                    str(dossier_data["composite_risk_level"]),
                    json.dumps(dossier_data.get("compliance_pillar_scores", {})),
                    dossier_data["audit_hash"],
                    dossier_data["certificate_text"],
                    now_iso
                )
            )
            conn.commit()

        self.record_audit_event(
            session_id=None,
            contractor_id=dossier_data["contractor_id"],
            event_type="DOSSIER_CERTIFIED",
            actor="contractor_vetting_coordinator",
            details=f"Issued dossier {dossier_id} with decision {dossier_data['final_decision']}"
        )
        return dossier_id

    def get_dossier(self, dossier_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a certified dossier by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dossiers WHERE dossier_id = ?", (dossier_id,))
            row = cursor.fetchone()
            if row:
                res = dict(row)
                res["pillar_scores"] = json.loads(res["pillar_scores"])
                return res
            return None

    def search_contractor_history(self, contractor_id: str) -> List[Dict[str, Any]]:
        """Find past vetting evaluations and dossiers for a given contractor."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM dossiers WHERE contractor_id = ? ORDER BY created_at DESC",
                (contractor_id,)
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def record_audit_event(
        self,
        session_id: Optional[str],
        contractor_id: Optional[str],
        event_type: str,
        actor: str,
        details: str,
    ) -> None:
        """Record an immutable audit log entry."""
        clean_details = PIIRedactionService.redact_text(details)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO audit_logs (session_id, contractor_id, event_type, actor, details, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id or "", contractor_id or "", event_type, actor, clean_details, now_iso)
            )
            conn.commit()

    def get_audit_trail(self, contractor_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve immutable audit log events."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if contractor_id:
                cursor.execute(
                    "SELECT * FROM audit_logs WHERE contractor_id = ? ORDER BY log_id DESC LIMIT ?",
                    (contractor_id, limit)
                )
            else:
                cursor.execute("SELECT * FROM audit_logs ORDER BY log_id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]


# Global storage instance
storage = PersistentVettingStore()
