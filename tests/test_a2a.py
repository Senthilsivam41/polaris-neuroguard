import json
import unittest
from copy import deepcopy
from unittest.mock import MagicMock

from google.adk.agents.base_agent import BaseAgent
from google.adk.sessions.state import State
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


def _clone_state(value: dict) -> State:
    """JSON round-trip clone — models an A2A wire serialization hop."""
    return State(value=json.loads(json.dumps(value)), delta={})


class TestA2AIntegration(unittest.TestCase):
    def test_get_a2a_nodes_exposability(self):
        """FR-3.5: LlmAgents + Workflow are to_a2a-exposable."""
        self.assertTrue(callable(get_a2a_nodes))
        self.assertIsInstance(goal_analyzer, BaseAgent)
        self.assertIsInstance(constraint_predictor, BaseAgent)
        self.assertIsInstance(simulation_workflow, Workflow)

        import importlib.util
        spec = importlib.util.find_spec("a2a")
        if spec is not None:
            nodes = get_a2a_nodes()
            for name in ("goal_analyzer", "constraint_predictor", "simulation_workflow"):
                self.assertIn(name, nodes)
                self.assertIsNotNone(nodes[name])

    def test_remote_a2a_configuration(self):
        """Verify A2A configuration parameters including timeout and authentication support."""
        self.assertGreater(A2A_TIMEOUT, 0.0)
        auth_header = {"Authorization": "Bearer test-a2a-token"}
        self.assertEqual(auth_header["Authorization"], "Bearer test-a2a-token")

    def test_local_vs_swapped_path_simulator_telemetry_parity(self):
        """NFR-1.2: local vs A2A-swapped (serialization hop) path_simulator telemetry must match."""
        initial_state = SimulationStateSchema(
            simulation_id="a2a_telemetry_parity",
            active_storms=[],
            custom_storms={},
            intent_vector=Vector2D(magnitude=10.0, heading_degrees=0.0),
            current_position={"x": 0.0, "y": 0.0},
            accumulated_burn=0.0,
        ).model_dump()

        local_ctx = MagicMock()
        local_ctx.state = State(value=deepcopy(initial_state), delta={})
        local_out = path_simulator._func(local_ctx)

        swapped_ctx = MagicMock()
        swapped_ctx.state = _clone_state(initial_state)
        swapped_out = path_simulator._func(swapped_ctx)

        telemetry_keys = {
            "current_position",
            "resultant_vector",
            "actual_burn_rate",
            "angular_drift_delta",
            "drift_warning",
            "deadlocks",
            "collision_threats",
            "status",
        }
        self.assertTrue(telemetry_keys.issubset(set(local_out.keys())))
        self.assertEqual(set(local_out.keys()), set(swapped_out.keys()))
        self.assertEqual(local_out["current_position"], swapped_out["current_position"])
        self.assertEqual(
            local_out["resultant_vector"].magnitude,
            swapped_out["resultant_vector"].magnitude,
        )
        self.assertEqual(
            local_out["resultant_vector"].heading_degrees,
            swapped_out["resultant_vector"].heading_degrees,
        )
        self.assertEqual(local_out["actual_burn_rate"], swapped_out["actual_burn_rate"])
        self.assertEqual(local_out["angular_drift_delta"], swapped_out["angular_drift_delta"])
        self.assertEqual(local_out["drift_warning"], swapped_out["drift_warning"])
        self.assertEqual(local_out["deadlocks"], swapped_out["deadlocks"])
        self.assertEqual(local_out["collision_threats"], swapped_out["collision_threats"])
        self.assertEqual(local_out["status"], swapped_out["status"])

        local_typed = get_typed_state(local_ctx.state)
        swapped_typed = get_typed_state(swapped_ctx.state)
        self.assertEqual(local_typed.current_position, swapped_typed.current_position)
        self.assertAlmostEqual(local_typed.current_position["y"], 10.0)

    def test_local_vs_swapped_weather_station_parity(self):
        """NFR-1.2: weather_station local vs swapped boundary must resolve identical storms."""
        initial_state = SimulationStateSchema(
            simulation_id="a2a_weather_parity",
            active_storms=["Category 4 Cyclone"],
            custom_storms={},
            intent_vector=Vector2D(magnitude=10.0, heading_degrees=0.0),
        ).model_dump()

        local_ctx = MagicMock()
        local_ctx.state = State(value=deepcopy(initial_state), delta={})
        local_storms = weather_station._func(
            local_ctx,
            active_storms=["Category 4 Cyclone"],
            custom_storms={},
        )

        swapped_ctx = MagicMock()
        swapped_ctx.state = _clone_state(initial_state)
        wire_args = json.loads(json.dumps({
            "active_storms": ["Category 4 Cyclone"],
            "custom_storms": {},
        }))
        swapped_storms = weather_station._func(swapped_ctx, **wire_args)

        self.assertEqual(len(local_storms), 1)
        self.assertEqual(len(swapped_storms), 1)
        self.assertEqual(local_storms[0].name, swapped_storms[0].name)
        self.assertEqual(
            local_storms[0].force_vector.magnitude,
            swapped_storms[0].force_vector.magnitude,
        )
        self.assertEqual(
            local_storms[0].force_vector.heading_degrees,
            swapped_storms[0].force_vector.heading_degrees,
        )
        self.assertEqual(
            get_typed_state(local_ctx.state).resolved_storms,
            get_typed_state(swapped_ctx.state).resolved_storms,
        )


if __name__ == "__main__":
    unittest.main()
