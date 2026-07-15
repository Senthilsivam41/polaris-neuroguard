import unittest
import asyncio
from datetime import datetime
from google.adk.agents.context import Context
from google.adk.agents.invocation_context import InvocationContext
from google.adk.sessions import InMemorySessionService
from google.adk.workflow._node_runner import NodeRunner
from google.adk.workflow._errors import NodeInterruptedError

from app.core.hitl.interruption import (
    InterruptionReason,
    InterruptionPayload,
    ADKInterruptionError,
)
from app.core.state import SimulationStateSchema, Vector2D, StormModel, IcebergModel
from app.core.nodes import path_simulator


class TestHITLInterruptions(unittest.IsolatedAsyncioTestCase):
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

    def test_interruption_reason_enum(self):
        """Verify InterruptionReason enum members exist."""
        expected_reasons = [
            "STATIC_CONSTRAINT_DEADLOCK",
            "SEMANTIC_CONSTRAINT_DEADLOCK",
            "COLLISION_THREAT",
            "DRIFT_REQUIRES_CONFIRMATION",
            "DRIFT_REQUIRES_HITL_REVIEW",
            "AMENDMENT_REJECTED",
            "POLICY_VIOLATION",
            "AUTHORIZATION_FAILURE",
            "UNKNOWN",
        ]
        for reason_name in expected_reasons:
            self.assertTrue(hasattr(InterruptionReason, reason_name))
            self.assertEqual(getattr(InterruptionReason, reason_name).value, reason_name)

    def test_interruption_payload_model(self):
        """Verify InterruptionPayload model structure and validation."""
        payload = InterruptionPayload(
            interruption_id="int-001",
            simulation_id="sim-001",
            invocation_id="inv-001",
            workflow_node="path_simulator",
            reason=InterruptionReason.COLLISION_THREAT,
            severity="CRITICAL",
            explanation="Imminent collision with iceberg.",
            safe_telemetry_snapshot={"x": 0.0, "y": 10.0},
            goal_contract_id="contract-sim-001",
            active_contract_version=1,
            required_resolution_action="Steer clear of collision threat or amend contract.",
        )
        self.assertEqual(payload.interruption_id, "int-001")
        self.assertEqual(payload.reason, InterruptionReason.COLLISION_THREAT)
        self.assertEqual(payload.status, "ACTIVE")
        self.assertTrue(isinstance(payload.created_at, str))

    def test_adk_interruption_error_subclass(self):
        """Verify ADKInterruptionError subclasses NodeInterruptedError."""
        payload = InterruptionPayload(
            interruption_id="int-002",
            simulation_id="sim-001",
            invocation_id="inv-001",
            workflow_node="path_simulator",
            reason=InterruptionReason.STATIC_CONSTRAINT_DEADLOCK,
            severity="HIGH",
            explanation="Opposing constraints active.",
            safe_telemetry_snapshot={},
            goal_contract_id="contract-sim-001",
            active_contract_version=1,
            required_resolution_action="Resolve constraint conflict.",
        )
        err = ADKInterruptionError(payload)
        self.assertIsInstance(err, NodeInterruptedError)
        self.assertEqual(err.payload, payload)

    async def test_path_simulator_raises_adk_interruption_on_deadlock(self):
        """Verify path simulator raises ADKInterruptionError on deadlock."""
        state = SimulationStateSchema(
            intent_vector=Vector2D(magnitude=10.0, heading_degrees=0.0),
            resolved_storms=[],
            current_position={"x": 0.0, "y": 0.0},
            accumulated_burn=0.0,
            active_deadlocks=[["RIGID_TIMELINE", "FREEZE_HEADCOUNT"]],
            hitl_interrupted=False
        )
        self._setup_context(state)

        runner = NodeRunner(node=path_simulator, parent_ctx=self.ctx)
        
        # When runner.run executes, the node raises ADKInterruptionError
        # NodeRunner catches NodeInterruptedError, sets output=None, and returns child_ctx
        child_ctx = await runner.run(node_input={})
        
        # NodeRunner's exception handler catches NodeInterruptedError
        # Verify interrupt_ids contain active interruption
        self.assertTrue(len(child_ctx.interrupt_ids) > 0 or child_ctx.state.get("hitl_interrupted"))
        self.assertTrue(child_ctx.state.get("hitl_interrupted"))
        self.assertIn("interruption_payload", child_ctx.state)

    async def test_path_simulator_raises_adk_interruption_on_collision(self):
        """Verify path simulator creates complete interruption payload on collision."""
        custom_iceberg = IcebergModel(
            name="Alpha Berg",
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

        self.assertTrue(child_ctx.state.get("hitl_interrupted"))
        payload_dict = child_ctx.state.get("interruption_payload")
        self.assertIsNotNone(payload_dict)
        self.assertEqual(payload_dict["reason"], InterruptionReason.COLLISION_THREAT.value)
        self.assertIn("Alpha Berg", payload_dict["explanation"])


if __name__ == "__main__":
    unittest.main()
