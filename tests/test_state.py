import unittest
from pydantic import ValidationError
from app.core.state import (
    SimulationStateSchema,
    GoalModel,
    Vector2D,
    validate_state_transition
)

class TestStateValidation(unittest.TestCase):
    def test_valid_state_initialization(self):
        """Verify that a valid state is instantiated correctly."""
        state = SimulationStateSchema(
            simulation_id="test_sim",
            user_id="test_user",
            anchor_goal=GoalModel(
                title="Migrate Core",
                target_timeline_months=12,
                budget_limit_usd=100000.0,
                reliability_target_sla=99.9
            ),
            intent_vector=Vector2D(magnitude=10.0, heading_degrees=180.0)
        )
        self.assertEqual(state.simulation_id, "test_sim")
        self.assertEqual(state.anchor_goal.title, "Migrate Core")
        self.assertEqual(state.intent_vector.magnitude, 10.0)

    def test_invalid_bounds(self):
        """Verify that out-of-bounds parameters raise ValidationError."""
        # Negative burn rate
        with self.assertRaises(ValidationError):
            SimulationStateSchema(accumulated_burn=-10.0)

        # Negative vector magnitude
        with self.assertRaises(ValidationError):
            SimulationStateSchema(intent_vector=Vector2D(magnitude=-5.0, heading_degrees=90.0))

        # Vector heading out of bounds
        with self.assertRaises(ValidationError):
            SimulationStateSchema(intent_vector=Vector2D(magnitude=10.0, heading_degrees=370.0))

    def test_hitl_state_consistency(self):
        """Verify that inconsistent HITL interruption states raise ValidationError."""
        # Interrupted but missing reason or telemetry snapshot
        with self.assertRaises(ValidationError):
            SimulationStateSchema(hitl_interrupted=True, hitl_reason="", hitl_telemetry_snapshot={"pos": 0})

        with self.assertRaises(ValidationError):
            SimulationStateSchema(hitl_interrupted=True, hitl_reason="Imminent collision", hitl_telemetry_snapshot=None)

        # Not interrupted but reason is populated
        with self.assertRaises(ValidationError):
            SimulationStateSchema(hitl_interrupted=False, hitl_reason="Imminent collision")

        # Consistent interrupted state
        state = SimulationStateSchema(
            hitl_interrupted=True,
            hitl_reason="Imminent collision",
            hitl_telemetry_snapshot={"x": 0.0, "y": 0.0}
        )
        self.assertTrue(state.hitl_interrupted)

    def test_transition_validation(self):
        """Verify that invalid state transitions are rejected."""
        old_state = SimulationStateSchema(accumulated_burn=100.0)
        
        # Valid transition (burn increases)
        new_state_valid = SimulationStateSchema(accumulated_burn=150.0)
        validate_state_transition(old_state, new_state_valid)

        # Invalid transition (burn decreases)
        new_state_invalid = SimulationStateSchema(accumulated_burn=50.0)
        with self.assertRaises(ValueError):
            validate_state_transition(old_state, new_state_invalid)

    def test_state_serialization_and_compatibility(self):
        """Verify that state schema serializes/deserializes correctly and handles version compatibility."""
        state = SimulationStateSchema(
            simulation_id="test_sim",
            goal_contract_version="2.0.0",
            intent_vector=Vector2D(magnitude=15.0, heading_degrees=45.0)
        )
        
        # Serialize to dict (simulates database persistence)
        serialized = state.model_dump()
        self.assertEqual(serialized["simulation_id"], "test_sim")
        self.assertEqual(serialized["goal_contract_version"], "2.0.0")
        self.assertEqual(serialized["intent_vector"]["magnitude"], 15.0)
        
        # Deserialize from dict (simulates load from database)
        deserialized = SimulationStateSchema.model_validate(serialized)
        self.assertEqual(deserialized.simulation_id, "test_sim")
        self.assertEqual(deserialized.goal_contract_version, "2.0.0")
        self.assertEqual(deserialized.intent_vector.magnitude, 15.0)



