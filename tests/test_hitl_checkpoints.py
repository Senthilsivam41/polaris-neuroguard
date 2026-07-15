import unittest
from app.core.hitl.interruption import InterruptionReason, InterruptionPayload
from app.core.hitl.checkpoint import WorkflowCheckpoint, sanitize_and_fingerprint_state
from app.core.hitl.checkpoint_service import (
    CheckpointService,
    CheckpointNotFoundError,
    CheckpointVersionConflictError,
    CheckpointCorruptError,
    CheckpointExpiredError,
)
from app.core.state import SimulationStateSchema, Vector2D


class TestHITLCheckpoints(unittest.TestCase):
    def setUp(self):
        self.service = CheckpointService()
        self.payload = InterruptionPayload(
            interruption_id="int-100",
            simulation_id="sim-100",
            invocation_id="inv-100",
            workflow_node="path_simulator",
            reason=InterruptionReason.COLLISION_THREAT,
            severity="HIGH",
            explanation="Collision threat detected with Iceberg.",
            safe_telemetry_snapshot={"x": 10.0, "y": 20.0},
            goal_contract_id="contract-sim-100",
            active_contract_version=1,
            required_resolution_action="Avert collision",
        )
        self.state_dict = SimulationStateSchema(
            simulation_id="sim-100",
            user_id="user-1",
            intent_vector=Vector2D(magnitude=10.0, heading_degrees=0.0),
            current_position={"x": 10.0, "y": 20.0},
            hitl_interrupted=True,
            hitl_reason="Collision threat detected with Iceberg.",
            hitl_telemetry_snapshot={"x": 10.0, "y": 20.0}
        ).model_dump()

    def test_checkpoint_creation_and_fingerprint(self):
        """Verify atomic creation, state validation, redaction, and SHA-256 fingerprinting."""
        raw_state = self.state_dict.copy()
        raw_state["api_key"] = "secret_key_12345"
        raw_state["raw_prompt"] = "Hidden chain of thought logic"

        chk = self.service.create_checkpoint(
            simulation_id="sim-100",
            invocation_id="inv-100",
            node_position="path_simulator",
            state_dict=raw_state,
            interruption_payload=self.payload,
            active_contract_id="contract-sim-100",
            active_contract_version=1,
            completed_nodes={"weather_station": [{"name": "Storm A"}]}
        )

        self.assertIsNotNone(chk.checkpoint_id)
        self.assertEqual(chk.checkpoint_version, 1)
        self.assertEqual(chk.checkpoint_status, "ACTIVE")
        self.assertNotIn("api_key", chk.validated_state)
        self.assertNotIn("raw_prompt", chk.validated_state)
        self.assertTrue(len(chk.state_fingerprint) == 64)  # SHA-256 hex digest length
        self.assertEqual(chk.completed_nodes, {"weather_station": [{"name": "Storm A"}]})

    def test_single_active_checkpoint_enforcement(self):
        """Verify only one active checkpoint may exist per simulation."""
        chk1 = self.service.create_checkpoint(
            simulation_id="sim-200",
            invocation_id="inv-200",
            node_position="path_simulator",
            state_dict=self.state_dict,
            interruption_payload=self.payload
        )
        self.assertEqual(chk1.checkpoint_status, "ACTIVE")

        payload2 = self.payload.model_copy(update={"interruption_id": "int-101"})
        chk2 = self.service.create_checkpoint(
            simulation_id="sim-200",
            invocation_id="inv-201",
            node_position="path_simulator",
            state_dict=self.state_dict,
            interruption_payload=payload2
        )

        # chk1 should be marked SUPERSEDED / CANCELLED and chk2 should be ACTIVE
        prior_chk1 = self.service.get_by_id(chk1.checkpoint_id)
        self.assertEqual(prior_chk1.checkpoint_status, "SUPERSEDED")

        active = self.service.get_active_checkpoint("sim-200")
        self.assertIsNotNone(active)
        self.assertEqual(active.checkpoint_id, chk2.checkpoint_id)

    def test_optimistic_versioning_and_resolution(self):
        """Verify optimistic versioning and marking checkpoint resolved."""
        chk = self.service.create_checkpoint(
            simulation_id="sim-300",
            invocation_id="inv-300",
            node_position="path_simulator",
            state_dict=self.state_dict,
            interruption_payload=self.payload
        )

        # Stale version attempt raises CheckpointVersionConflictError
        with self.assertRaises(CheckpointVersionConflictError):
            self.service.mark_resolved(chk.checkpoint_id, expected_version=99, resolution_details="Fixed")

        resolved_chk = self.service.mark_resolved(chk.checkpoint_id, expected_version=1, resolution_details="Fixed")
        self.assertEqual(resolved_chk.checkpoint_status, "RESOLVED")
        self.assertEqual(resolved_chk.checkpoint_version, 2)
        self.assertIsNone(self.service.get_active_checkpoint("sim-300"))

    def test_mark_expired_or_cancelled(self):
        """Verify marking checkpoint as expired or cancelled."""
        chk = self.service.create_checkpoint(
            simulation_id="sim-400",
            invocation_id="inv-400",
            node_position="path_simulator",
            state_dict=self.state_dict,
            interruption_payload=self.payload
        )

        cancelled_chk = self.service.mark_expired_or_cancelled(chk.checkpoint_id, status="CANCELLED")
        self.assertEqual(cancelled_chk.checkpoint_status, "CANCELLED")

        # Trying to resolve an expired/cancelled checkpoint throws CheckpointExpiredError
        with self.assertRaises(CheckpointExpiredError):
            self.service.mark_resolved(chk.checkpoint_id, expected_version=cancelled_chk.checkpoint_version, resolution_details="Late attempt")

    def test_auditable_checkpoint_history(self):
        """Verify retrieving full auditable history for a simulation."""
        self.service.create_checkpoint("sim-500", "inv-500", "path_simulator", self.state_dict, self.payload)
        self.service.create_checkpoint("sim-500", "inv-501", "path_simulator", self.state_dict, self.payload)

        history = self.service.get_checkpoint_history("sim-500")
        self.assertEqual(len(history), 2)

    def test_corrupt_checkpoint_detection(self):
        """Verify corrupt state is detected and rejected."""
        invalid_state = {"simulation_id": "sim-600", "accumulated_burn": -999.0}  # Invalid negative burn
        with self.assertRaises(CheckpointCorruptError):
            self.service.create_checkpoint("sim-600", "inv-600", "path_simulator", invalid_state, self.payload)


    def test_idempotency_key_stored_on_checkpoint(self):
        """Verify idempotency key is stored and retrievable on checkpoint."""
        chk = self.service.create_checkpoint(
            simulation_id="sim-700",
            invocation_id="inv-700",
            node_position="path_simulator",
            state_dict=self.state_dict,
            interruption_payload=self.payload,
            idempotency_key="req-idem-abc-123"
        )
        self.assertEqual(chk.idempotency_key, "req-idem-abc-123")
        retrieved = self.service.get_by_id(chk.checkpoint_id)
        self.assertEqual(retrieved.idempotency_key, "req-idem-abc-123")

    def test_checkpoint_history_safe_list_no_secrets(self):
        """Verify checkpoint history list never contains secret/prohibited keys."""
        import copy
        raw_state = copy.deepcopy(self.state_dict)
        raw_state["api_key"] = "should_be_redacted"
        raw_state["token"] = "jwt_secret_value"

        chk = self.service.create_checkpoint(
            simulation_id="sim-800",
            invocation_id="inv-800",
            node_position="path_simulator",
            state_dict=raw_state,
            interruption_payload=self.payload
        )

        history = self.service.get_checkpoint_history("sim-800")
        self.assertEqual(len(history), 1)
        validated = history[0].validated_state
        self.assertNotIn("api_key", validated)
        self.assertNotIn("token", validated)

    def test_completed_nodes_cached_in_checkpoint(self):
        """Verify completed_nodes dict is stored in checkpoint to prevent side-effect replay."""
        completed = {
            "weather_station": [{"name": "Storm A", "cost_friction_multiplier": 1.5}],
            "goal_analyzer": {"is_consistent": True},
        }
        chk = self.service.create_checkpoint(
            simulation_id="sim-900",
            invocation_id="inv-900",
            node_position="path_simulator",
            state_dict=self.state_dict,
            interruption_payload=self.payload,
            completed_nodes=completed
        )
        retrieved = self.service.get_by_id(chk.checkpoint_id)
        self.assertIn("weather_station", retrieved.completed_nodes)
        self.assertIn("goal_analyzer", retrieved.completed_nodes)
        self.assertEqual(retrieved.completed_nodes["weather_station"][0]["name"], "Storm A")


if __name__ == "__main__":
    unittest.main()
