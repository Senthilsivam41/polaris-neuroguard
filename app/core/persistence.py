"""Durable simulation state and idempotency records (PROD-001..003)."""

import hashlib
import json
import os
import sqlite3
import threading
from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class VersionConflictError(Exception):
    """Raised when a state update was based on an obsolete session version."""


class IdempotencyConflictError(Exception):
    """Raised when one key is reused for a different request body."""


class SQLiteWorkflowStore:
    """Small SQLite repository with atomic compare-and-swap updates.

    The database path is configurable so deployments can mount durable storage.
    SQLite transactions use ``BEGIN IMMEDIATE`` to serialize competing writers.
    """

    def __init__(self, path: Optional[str] = None):
        configured = path or os.getenv("POLARIS_DB_PATH", "polaris-neuroguard.sqlite")
        self.path = str(Path(configured))
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS simulation_sessions (
                    simulation_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS idempotency_records (
                    operation TEXT NOT NULL,
                    simulation_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    response_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (operation, simulation_id, request_id)
                )"""
            )

    @staticmethod
    def canonical_hash(payload: Dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=SQLiteWorkflowStore._json_default)
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return str(value)

    def create_session(self, simulation_id: str, payload: Dict[str, Any]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        encoded = json.dumps(payload, sort_keys=True, default=self._json_default)
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO simulation_sessions VALUES (?, ?, 1, ?, ?)",
                    (simulation_id, encoded, now, now),
                )
            except Exception:
                conn.rollback()
                raise
            conn.commit()
        return 1

    def get_session(self, simulation_id: str) -> Optional[Tuple[Dict[str, Any], int]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json, version FROM simulation_sessions WHERE simulation_id = ?",
                (simulation_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload_json"]), int(row["version"])

    def list_sessions(self) -> list[Tuple[str, Dict[str, Any], int]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT simulation_id, payload_json, version FROM simulation_sessions").fetchall()
        return [(row["simulation_id"], json.loads(row["payload_json"]), int(row["version"])) for row in rows]

    def save_session(self, simulation_id: str, payload: Dict[str, Any], expected_version: int) -> int:
        now = datetime.now(timezone.utc).isoformat()
        encoded = json.dumps(payload, sort_keys=True, default=self._json_default)
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            result = conn.execute(
                """UPDATE simulation_sessions
                   SET payload_json = ?, version = version + 1, updated_at = ?
                   WHERE simulation_id = ? AND version = ?""",
                (encoded, now, simulation_id, expected_version),
            )
            if result.rowcount != 1:
                conn.rollback()
                raise VersionConflictError(f"Session '{simulation_id}' was updated by another request.")
            conn.commit()
        return expected_version + 1

    def reserve_idempotency(self, operation: str, simulation_id: str, request_id: str,
                            payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Atomically reserve a key, or return its completed response."""
        payload_hash = self.canonical_hash(payload)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT payload_hash, response_json FROM idempotency_records WHERE operation=? AND simulation_id=? AND request_id=?",
                (operation, simulation_id, request_id),
            ).fetchone()
            if row:
                conn.commit()
                if row["payload_hash"] != payload_hash:
                    raise IdempotencyConflictError("Idempotency key was reused with a different request payload.")
                if row["response_json"] is None:
                    raise VersionConflictError("An equivalent request is already in progress.")
                return json.loads(row["response_json"])
            conn.execute(
                "INSERT INTO idempotency_records VALUES (?, ?, ?, ?, NULL, ?, ?)",
                (operation, simulation_id, request_id, payload_hash, now, now),
            )
            conn.commit()
        return None

    def complete_idempotency(self, operation: str, simulation_id: str, request_id: str,
                             response: Dict[str, Any]) -> None:
        encoded = json.dumps(response, sort_keys=True, default=self._json_default)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE idempotency_records SET response_json=?, updated_at=? WHERE operation=? AND simulation_id=? AND request_id=?",
                (encoded, now, operation, simulation_id, request_id),
            )
            conn.commit()

    def clear(self) -> None:
        """Test-only cleanup method."""
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM idempotency_records")
            conn.execute("DELETE FROM simulation_sessions")


workflow_store = SQLiteWorkflowStore()
