import unittest
from google.adk.tools import ToolContext
from google.adk.agents import InvocationContext
from google.adk.sessions import Session
from google.adk.sessions import InMemorySessionService
from app.core.tools import (
    resultant_vector_tool,
    logical_deadlocks_tool,
    trajectory_collision_tool,
    burn_rate_tool,
    position_advancer_tool
)

class TestSimulationTools(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Build mock ToolContext required by run_async
        session_service = InMemorySessionService()
        session = Session(id="test_session", app_name="test_app", user_id="test_user")
        self.ic = InvocationContext(
            session_service=session_service,
            session=session,
            invocation_id="test_inv"
        )
        self.ctx = ToolContext(self.ic)

    async def test_resultant_vector_tool(self):
        """Verify resultant vector summation tool."""
        args = {
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
            "active_storms": [
                {
                    "storm_type": "Meteorological",
                    "name": "Cyclone",
                    "magnitude": 12.0,
                    "heading_degrees": 90.0,
                    "cost_friction_multiplier": 1.0
                }
            ]
        }
        res = await resultant_vector_tool.run_async(args=args, tool_context=self.ctx)
        self.assertAlmostEqual(res.magnitude, 15.62049935, places=4)
        self.assertAlmostEqual(res.heading_degrees, 50.1944289, places=4)

    async def test_logical_deadlocks_tool(self):
        """Verify systemic deadlock detection tool."""
        args = {
            "declared_constraints": ["RIGID_TIMELINE", "FREEZE_HEADCOUNT"]
        }
        res = await logical_deadlocks_tool.run_async(args=args, tool_context=self.ctx)
        self.assertEqual(res, [("RIGID_TIMELINE", "FREEZE_HEADCOUNT")])

    async def test_trajectory_collision_tool(self):
        """Verify look-ahead iceberg collision tool."""
        args = {
            "start_x": 0.0,
            "start_y": 550.0,
            "resultant_vector": {"magnitude": 20.0, "heading_degrees": 90.0}, # moving East
            "custom_icebergs": [
                {
                    "name": "Custom Deadlock Obstacle",
                    "x": 30.0,
                    "y": 550.0,
                    "radius": 50.0
                }
            ]
        }
        res = await trajectory_collision_tool.run_async(args=args, tool_context=self.ctx)
        # It projects 3 turns forward (3 * 20 = 60). Circle center is at 30.0 (inside projection path).
        self.assertIn("Custom Deadlock Obstacle", res)

    async def test_burn_rate_tool(self):
        """Verify burn-rate calculation applying economic multipliers."""
        args = {
            "base_burn_rate": 100.0,
            "active_storms": [
                {
                    "storm_type": "Economic",
                    "name": "Surging Petrol Prices",
                    "magnitude": 0.0,
                    "heading_degrees": 0.0,
                    "cost_friction_multiplier": 1.35
                }
            ]
        }
        res = await burn_rate_tool.run_async(args=args, tool_context=self.ctx)
        self.assertEqual(res, 135.0)

    async def test_position_advancer_tool(self):
        """Verify coordinates advancement tool."""
        args = {
            "current_x": 10.0,
            "current_y": 20.0,
            "resultant_vector": {"magnitude": 10.0, "heading_degrees": 90.0} # Moving East
        }
        res = await position_advancer_tool.run_async(args=args, tool_context=self.ctx)
        self.assertAlmostEqual(res.x, 20.0, places=4)
        self.assertAlmostEqual(res.y, 20.0, places=4)

    async def test_invalid_tool_inputs(self):
        """Verify that FunctionTools reject invalid domain inputs."""
        from pydantic import ValidationError

        # 1. Negative intent vector magnitude
        args_neg_mag = {
            "intent_vector": {"magnitude": -10.0, "heading_degrees": 0.0},
            "active_storms": []
        }
        with self.assertRaises(ValidationError):
            await resultant_vector_tool.run_async(args=args_neg_mag, tool_context=self.ctx)

        # 2. Invalid heading degrees (out of 0-360 range)
        args_invalid_heading = {
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 380.0},
            "active_storms": []
        }
        with self.assertRaises(ValidationError):
            await resultant_vector_tool.run_async(args=args_invalid_heading, tool_context=self.ctx)

        # 3. Negative iceberg radius
        args_neg_radius = {
            "start_x": 0.0,
            "start_y": 0.0,
            "resultant_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
            "custom_icebergs": [
                {
                    "name": "Invalid Iceberg",
                    "x": 0.0,
                    "y": 10.0,
                    "radius": -5.0
                }
            ]
        }
        with self.assertRaises(ValidationError):
            await trajectory_collision_tool.run_async(args=args_neg_radius, tool_context=self.ctx)

        # 4. Negative friction multiplier
        args_neg_friction = {
            "base_burn_rate": 100.0,
            "active_storms": [
                {
                    "storm_type": "Economic",
                    "name": "Bad Storm",
                    "magnitude": 0.0,
                    "heading_degrees": 0.0,
                    "cost_friction_multiplier": -1.5
                }
            ]
        }
        with self.assertRaises(ValidationError):
            await burn_rate_tool.run_async(args=args_neg_friction, tool_context=self.ctx)

        # 5. Negative base burn rate (ValueError inside tool function)
        args_neg_burn = {
            "base_burn_rate": -100.0,
            "active_storms": []
        }
        with self.assertRaises(ValueError):
            await burn_rate_tool.run_async(args=args_neg_burn, tool_context=self.ctx)

