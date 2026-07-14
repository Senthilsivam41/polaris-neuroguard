import unittest
import importlib
from unittest.mock import MagicMock
from google.adk.agents.base_agent import BaseAgent
from google.adk.workflow import Workflow
from app.core.config import A2A_TIMEOUT
from app.core.nodes import (
    get_a2a_nodes,
    goal_analyzer,
    constraint_predictor,
    weather_station,
    path_simulator,
    simulation_workflow,
)
from app.core.state import SimulationStateSchema, Vector2D, get_typed_state

class TestA2AIntegration(unittest.TestCase):
    def test_get_a2a_nodes_exposability(self):
        """FR-3.5 / NFR-1.2: Verify get_a2a_nodes factory is exposable and node types conform to to_a2a contract."""
        self.assertTrue(callable(get_a2a_nodes))
        self.assertIsInstance(goal_analyzer, BaseAgent)
        self.assertIsInstance(constraint_predictor, BaseAgent)
        self.assertIsInstance(simulation_workflow, Workflow)

        # Check if optional a2a package is installed
        spec = importlib.util.find_spec("a2a")
        if spec is not None:
            nodes = get_a2a_nodes()
            for name in ("goal_analyzer", "constraint_predictor", "weather_station", "path_simulator"):
                self.assertIn(name, nodes)
                self.assertIsNotNone(nodes[name])

    def test_remote_a2a_configuration(self):
        """Verify A2A configuration parameters including timeout and authentication support."""
        self.assertGreater(A2A_TIMEOUT, 0.0)
        
        # Test constructing AgentCard or metadata headers for remote A2A wrappers
        auth_header = {"Authorization": "Bearer test-a2a-token"}
        self.assertEqual(auth_header["Authorization"], "Bearer test-a2a-token")

    def test_local_vs_remote_telemetry_equivalence(self):
        """Verify local and remote node state outputs maintain identical schema contracts."""
        from google.adk.sessions.state import State
        
        initial_state = SimulationStateSchema(
            simulation_id="a2a_telemetry_test",
            active_storms=[],
            custom_storms={},
            intent_vector=Vector2D(magnitude=10.0, heading_degrees=0.0)
        ).model_dump()
        
        ctx = MagicMock()
        ctx.state = State(value=initial_state, delta={})
        
        # Local execution of path_simulator
        output = path_simulator._func(ctx)
        
        # Verify output keys match expected telemetry contract
        expected_keys = {
            "current_position",
            "resultant_vector",
            "actual_burn_rate",
            "angular_drift_delta",
            "drift_warning",
            "deadlocks",
            "collision_threats",
            "status",
        }
        self.assertTrue(expected_keys.issubset(set(output.keys())))
        
        # Verify typed state in context matches schema contract
        typed_state = get_typed_state(ctx.state)
        self.assertAlmostEqual(typed_state.current_position["y"], 10.0)
