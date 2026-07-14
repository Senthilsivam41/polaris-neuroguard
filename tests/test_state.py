import unittest
from pydantic import ValidationError
from app.core.state import (
    SimulationStateSchema,
    GoalModel,
    Vector2D,
    validate_state_transition,
    get_typed_state,
    update_typed_state
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

    def test_get_typed_state(self):
        """Verify get_typed_state extracts and validates schema from dict or objects."""
        raw = {"simulation_id": "sim_123", "accumulated_burn": 50.0}
        typed = get_typed_state(raw)
        self.assertIsInstance(typed, SimulationStateSchema)
        self.assertEqual(typed.simulation_id, "sim_123")
        self.assertEqual(typed.accumulated_burn, 50.0)

    def test_update_typed_state_valid_and_invalid(self):
        """Verify update_typed_state validates updates and transition integrity."""
        from app.core.state import update_typed_state
        
        target = {"simulation_id": "sim_1", "accumulated_burn": 100.0}
        
        # Valid update (accumulated burn increases)
        updated = update_typed_state(target, {"accumulated_burn": 120.0})
        self.assertEqual(updated.accumulated_burn, 120.0)
        self.assertEqual(target["accumulated_burn"], 120.0)
        
        # Invalid update (out of bounds burn rate)
        with self.assertRaises(ValidationError):
            update_typed_state(target, {"accumulated_burn": -10.0})
            
        # Invalid transition (accumulated burn decreases)
        with self.assertRaises(ValueError):
            update_typed_state(target, {"accumulated_burn": 50.0}, validate_transition=True)

    def test_node_context_state_boundary_enforcement(self):
        """Verify state boundary enforcement over mock node context dictionary."""
        from unittest.mock import MagicMock
        from google.adk.sessions.state import State
        from app.core.nodes import weather_station, path_simulator
        from app.core.state import StormModel, Vector2D
        
        initial_state = SimulationStateSchema(
            simulation_id="sim_node_test",
            active_storms=[],
            custom_storms={},
            intent_vector=Vector2D(magnitude=10.0, heading_degrees=90.0)
        ).model_dump()
        
        ctx = MagicMock()
        ctx.state = State(value=initial_state, delta={})
        
        # weather_station boundary check
        weather_station._func(ctx, active_storms=[], custom_storms={})
        self.assertIn("resolved_storms", ctx.state)
        
        # path_simulator boundary check
        res = path_simulator._func(ctx)
        self.assertEqual(res["status"], "RUNNING")
        self.assertGreater(ctx.state["accumulated_burn"], 0.0)
        
        # Illegal state delta update attempt (negative burn) throws ValidationError
        with self.assertRaises(ValidationError):
            update_typed_state(ctx.state, {"accumulated_burn": -5.0})




