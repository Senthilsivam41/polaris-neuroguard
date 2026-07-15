"""Focused PROD-001..003 tests without application-framework dependencies."""

import os
import tempfile
import unittest

from app.core.persistence import (
    IdempotencyConflictError,
    SQLiteWorkflowStore,
    VersionConflictError,
)


class TestSQLiteWorkflowStore(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.gettempdir(), "polaris-phase5-test.sqlite")
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        self.store = SQLiteWorkflowStore(self.path)

    def test_durable_session_read_and_optimistic_concurrency(self):
        self.store.create_session("sim-1", {"position": {"x": 0}})
        state, version = self.store.get_session("sim-1")
        self.assertEqual(state["position"]["x"], 0)
        self.assertEqual(self.store.save_session("sim-1", {"position": {"x": 1}}, version), 2)
        with self.assertRaises(VersionConflictError):
            self.store.save_session("sim-1", {"position": {"x": 2}}, version)

    def test_completed_idempotency_replays_and_mismatched_body_conflicts(self):
        self.assertIsNone(self.store.reserve_idempotency("evaluate", "sim-1", "req-1", {"value": 1}))
        self.store.complete_idempotency("evaluate", "sim-1", "req-1", {"status": "RUNNING"})
        self.assertEqual(
            self.store.reserve_idempotency("evaluate", "sim-1", "req-1", {"value": 1}),
            {"status": "RUNNING"},
        )
        with self.assertRaises(IdempotencyConflictError):
            self.store.reserve_idempotency("evaluate", "sim-1", "req-1", {"value": 2})

