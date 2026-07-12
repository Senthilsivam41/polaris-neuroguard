import unittest
import asyncio
from google.adk.agents.context import Context
from google.adk.agents.invocation_context import InvocationContext
from google.adk.sessions import InMemorySessionService, Session as AdkSession
from google.adk.workflow._node_runner import NodeRunner
from google.adk.workflow._errors import NodeInterruptedError
from app.core.state import SimulationStateSchema, StormModel, Vector2D, IcebergModel
from app.core.nodes import weather_station, path_simulator, simulation_workflow

class TestWorkflow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session_service = InMemorySessionService()
        self.adk_session = await self.session_service.create_session(
            app_name="polaris-neuroguard",
            user_id="test-user",
            session_id="test-sim-id"
        )
        self.ic = InvocationContext(
            session_service=self.session_service,
            session=self.adk_session,
            invocation_id="test-inv-id"
        )
        self.ic._event_queue = asyncio.Queue()
        self.ctx = Context(
            self.ic,
            parent_ctx=None,
            node=None,
            run_id="1"
        )
        self.queue_processed = asyncio.Event()
        self.queue_task = asyncio.create_task(self._process_event_queue())

    async def asyncTearDown(self):
        self.queue_processed.set()
        await self.queue_task

    def _setup_context(self, state: SimulationStateSchema):
        self.adk_session.state.clear()
        self.adk_session.state.update(state.model_dump())
        from google.adk.sessions.state import State
        self.ctx._state = State(
            value=self.adk_session.state,
            delta=self.ctx._event_actions.state_delta,
            schema=state
        )

    async def _process_event_queue(self):
        import asyncio
        while not self.queue_processed.is_set():
            try:
                item = await asyncio.wait_for(self.ic._event_queue.get(), timeout=0.1)
                event, processed = item
                if processed is not None:
                    processed.set()
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    async def test_weather_station_preset_storm(self):
        """Verify weather station resolves preset storms successfully."""
        state = SimulationStateSchema(
            active_storms=["Category 4 Cyclone"]
        )
        self._setup_context(state)
        
        runner = NodeRunner(node=weather_station, parent_ctx=self.ctx)
        child_ctx = await runner.run(node_input={})
        resolved = child_ctx.output
        
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].name, "Category 4 Cyclone")
        self.assertEqual(resolved[0].cost_friction_multiplier, 1.0)
        self.assertEqual(resolved[0].force_vector.magnitude, 12.0)

    async def test_weather_station_custom_storm(self):
        """Verify weather station resolves custom storms successfully."""
        custom_storm = StormModel(
            storm_type="Magnetic Storm",
            name="Solar Flare",
            force_vector=Vector2D(magnitude=15.0, heading_degrees=180.0),
            cost_friction_multiplier=2.0
        )
        state = SimulationStateSchema(
            active_storms=["Solar Flare"],
            custom_storms={"Solar Flare": custom_storm}
        )
        self._setup_context(state)
        
        runner = NodeRunner(node=weather_station, parent_ctx=self.ctx)
        child_ctx = await runner.run(node_input={})
        resolved = child_ctx.output
        
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].name, "Solar Flare")
        self.assertEqual(resolved[0].cost_friction_multiplier, 2.0)

    async def test_weather_station_unknown_storm(self):
        """Verify weather station rejects unknown storms with ValueError."""
        state = SimulationStateSchema(
            active_storms=["Unknown Mystery Storm"]
        )
        self._setup_context(state)
        
        runner = NodeRunner(node=weather_station, parent_ctx=self.ctx)
        child_ctx = await runner.run(node_input={})
        self.assertIsInstance(child_ctx.error, ValueError)

    async def test_path_simulator_normal_execution(self):
        """Verify path simulator processes normal step simulation accurately."""
        state = SimulationStateSchema(
            intent_vector=Vector2D(magnitude=10.0, heading_degrees=0.0),
            resolved_storms=[],
            current_position={"x": 0.0, "y": 0.0},
            accumulated_burn=0.0
        )
        self._setup_context(state)
        
        runner = NodeRunner(node=path_simulator, parent_ctx=self.ctx)
        child_ctx = await runner.run(node_input={})
        output = child_ctx.output
        
        self.assertEqual(output["status"], "RUNNING")
        self.assertAlmostEqual(output["current_position"]["x"], 0.0)
        self.assertAlmostEqual(output["current_position"]["y"], 10.0)
        self.assertAlmostEqual(output["actual_burn_rate"], 100.0)
        self.assertFalse(self.ctx.state._schema.hitl_interrupted)

    async def test_path_simulator_deadlock_zeroes_velocity(self):
        """Verify path simulator zeroes intent velocity magnitude if a deadlock exists."""
        state = SimulationStateSchema(
            intent_vector=Vector2D(magnitude=10.0, heading_degrees=0.0),
            resolved_storms=[StormModel(
                storm_type="Wind",
                name="Blow",
                force_vector=Vector2D(magnitude=5.0, heading_degrees=90.0),
                cost_friction_multiplier=1.0
            )],
            current_position={"x": 0.0, "y": 0.0},
            accumulated_burn=0.0,
            active_deadlocks=[["RIGID_TIMELINE", "FREEZE_HEADCOUNT"]]
        )
        self._setup_context(state)
        
        runner = NodeRunner(node=path_simulator, parent_ctx=self.ctx)
        child_ctx = await runner.run(node_input={})
        
        # Deadlock is present, so the simulation will interrupt
        self.assertTrue(self.ctx.state._schema.hitl_interrupted)
            
        self.assertAlmostEqual(self.ctx.state._schema.resultant_vector.magnitude, 5.0)
        self.assertAlmostEqual(self.ctx.state._schema.resultant_vector.heading_degrees, 90.0)
        self.assertAlmostEqual(self.ctx.state._schema.current_position["x"], 5.0)
        self.assertAlmostEqual(self.ctx.state._schema.current_position["y"], 0.0)

    async def test_path_simulator_collision_threat(self):
        """Verify path simulator raises NodeInterruptedError on imminent iceberg collisions."""
        custom_iceberg = IcebergModel(
            name="Iceberg Alpha",
            x=0.0,
            y=100.0,
            radius=100.0
        )
        state = SimulationStateSchema(
            intent_vector=Vector2D(magnitude=50.0, heading_degrees=0.0),
            resolved_storms=[],
            current_position={"x": 0.0, "y": 0.0},
            accumulated_burn=0.0,
            custom_icebergs=[custom_iceberg]
        )
        self._setup_context(state)
        
        runner = NodeRunner(node=path_simulator, parent_ctx=self.ctx)
        child_ctx = await runner.run(node_input={})
        
        self.assertIsInstance(child_ctx.error, NodeInterruptedError)
        self.assertTrue(self.ctx.state._schema.hitl_interrupted)
        self.assertIn("Iceberg Alpha", self.ctx.state._schema.hitl_reason)
        self.assertIn("Iceberg Alpha", self.ctx.state._schema.collision_threats)
