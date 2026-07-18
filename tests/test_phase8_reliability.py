"""TEST-005 durable-store concurrency, replay, restart, and recovery coverage."""
import os
import tempfile
import threading
import unittest

from app.core.persistence import SQLiteWorkflowStore, VersionConflictError


class TestPhase8Reliability(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.gettempdir(), "polaris-phase8-reliability.sqlite")
        try: os.unlink(self.path)
        except FileNotFoundError: pass
        self.store = SQLiteWorkflowStore(self.path)
        self.store.create_session("sim", {"turns": 0, "interrupted": True})

    def test_simultaneous_updates_do_not_lose_the_winning_update(self):
        initial, version = self.store.get_session("sim")
        outcomes = []
        def update(turns):
            try:
                self.store.save_session("sim", {"turns": turns, "interrupted": True}, version)
                outcomes.append("saved")
            except VersionConflictError:
                outcomes.append("conflict")
        workers = [threading.Thread(target=update, args=(n,)) for n in (1, 2)]
        [worker.start() for worker in workers]; [worker.join() for worker in workers]
        self.assertEqual(sorted(outcomes), ["conflict", "saved"])
        self.assertIn(self.store.get_session("sim")[0]["turns"], {1, 2})

    def test_duplicate_request_replays_after_store_reopen(self):
        self.assertIsNone(self.store.reserve_idempotency("resume", "sim", "req", {"x": 1}))
        self.store.complete_idempotency("resume", "sim", "req", {"status": "RUNNING"})
        restarted = SQLiteWorkflowStore(self.path)
        self.assertEqual(restarted.reserve_idempotency("resume", "sim", "req", {"x": 1}), {"status": "RUNNING"})
        self.assertTrue(restarted.get_session("sim")[0]["interrupted"])
