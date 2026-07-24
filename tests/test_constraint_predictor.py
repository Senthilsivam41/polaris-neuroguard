import unittest
from unittest.mock import patch, AsyncMock
from google.genai.types import Content, Part
from google.adk.models.llm_response import LlmResponse
from google.adk.agents.invocation_context import InvocationContext
from google.adk.sessions import Session, InMemorySessionService
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.run_config import RunConfig
from google.adk.workflow._node_runner import NodeRunner
from app.core.state import SimulationStateSchema, Vector2D, get_typed_state
from app.core.agents import constraint_predictor, before_predictor_callback, ConstraintConflictAssessment

class TestConstraintPredictorAgent(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Pin the agent to a real Gemini model name so the Gemini patches in
        # these tests take effect even when OFFLINE_MODE swaps in the mock LLM.
        self._model_patcher = patch.object(constraint_predictor, "model", "gemini-2.0-flash")
        self._model_patcher.start()
        self.addCleanup(self._model_patcher.stop)
        self.session_service = InMemorySessionService()
        self.session = Session(id="test_session", app_name="test_app", user_id="test_user")
        self.session.state = {
            "declared_constraints": ["RIGID_TIMELINE", "FREEZE_HEADCOUNT"],
            "intent_vector": Vector2D(magnitude=10.0, heading_degrees=90.0).model_dump(),
            "active_deadlocks": []
        }
        self.ic = InvocationContext(
            session_service=self.session_service,
            session=self.session,
            invocation_id="test_inv",
            run_config=RunConfig()
        )
        import asyncio
        self.ic._event_queue = asyncio.Queue()
        self.ctx = CallbackContext(self.ic, node=constraint_predictor)
        self.consumer_task = asyncio.create_task(self._consume_event_queue())

    async def asyncTearDown(self):
        if hasattr(self, "consumer_task"):
            self.consumer_task.cancel()
            import asyncio
            await asyncio.gather(self.consumer_task, return_exceptions=True)

    async def _consume_event_queue(self):
        while True:
            try:
                item = await self.ic._event_queue.get()
                event, processed = item
                self.session.events.append(event)
                if processed:
                    processed.set()
            except Exception:
                break

    @patch("app.core.agents.after_predictor_callback")
    @patch("google.adk.models.google_llm.Gemini.generate_content_async")
    async def test_static_deadlock_detection(self, mock_generate_content_async, mock_after):
        """Verify static deadlock detection via before_predictor_callback short-circuit without LLM or after_callback execution."""
        # Run the agent node via NodeRunner
        runner = NodeRunner(node=constraint_predictor, parent_ctx=self.ctx)
        child_ctx = await runner.run(node_input={})
        
        # Verify LLM was short-circuited (never invoked) and after-callback did not execute
        mock_generate_content_async.assert_not_called()
        mock_after.assert_not_called()

        # Verify before_predictor_callback set the route to deadlock and zeroed the intent magnitude
        typed_state = get_typed_state(child_ctx.state)
        self.assertEqual(child_ctx.route, "deadlock")
        self.assertEqual(typed_state.active_deadlocks, [["RIGID_TIMELINE", "FREEZE_HEADCOUNT"]])
        self.assertEqual(typed_state.intent_vector.magnitude, 0.0)

        # Core assertion: after_predictor_callback was never invoked
        mock_after.assert_not_called()

    @patch("google.adk.models.google_llm.Gemini.generate_content_async")
    async def test_low_confidence_conflict_no_block(self, mock_generate_content_async):
        """Verify low-confidence semantic conflict does not block/route to deadlock."""
        async def mock_gen(*args, **kwargs):
            content = Content(
                role='model',
                parts=[Part(text='{"has_deadlock": false, "conflicts": [{"constraint_a": "RIGID_TIMELINE", "constraint_b": "EXTEND_SCHEDULE", "conflict_type": "semantic", "evidence": "Uncertain semantic conflict", "confidence": 0.5}]}')]
            )
            yield LlmResponse(
                model_version='gemini-2.0-flash',
                content=content
            )
            
        mock_generate_content_async.side_effect = mock_gen

        # Reset session state for no deadlocks and non-zero intent
        self.session.state["declared_constraints"] = ["RIGID_TIMELINE", "EXTEND_SCHEDULE"]
        self.session.state["intent_vector"] = Vector2D(magnitude=10.0, heading_degrees=90.0).model_dump()
        self.session.state["active_deadlocks"] = []
        self.ctx = CallbackContext(self.ic, node=constraint_predictor)

        # Run the agent node via NodeRunner
        runner = NodeRunner(node=constraint_predictor, parent_ctx=self.ctx)
        child_ctx = await runner.run(node_input={})

        typed_state = get_typed_state(child_ctx.state)
        self.assertEqual(child_ctx.route, "no_deadlock")
        self.assertEqual(typed_state.active_deadlocks, [])
        self.assertEqual(typed_state.intent_vector.magnitude, 10.0)

    @patch("google.adk.models.google_llm.Gemini.generate_content_async")
    async def test_high_confidence_semantic_deadlock(self, mock_generate_content_async):
        """Verify high-confidence semantic conflict routes to deadlock and updates state."""
        async def mock_gen(*args, **kwargs):
            content = Content(
                role='model',
                parts=[Part(text='{"has_deadlock": true, "conflicts": [{"constraint_a": "RIGID_TIMELINE", "constraint_b": "EXTEND_SCHEDULE", "conflict_type": "semantic", "evidence": "Highly confident semantic conflict", "confidence": 0.9}]}')]
            )
            yield LlmResponse(
                model_version='gemini-2.0-flash',
                content=content
            )
            
        mock_generate_content_async.side_effect = mock_gen

        self.session.state["declared_constraints"] = ["RIGID_TIMELINE", "EXTEND_SCHEDULE"]
        self.session.state["intent_vector"] = Vector2D(magnitude=10.0, heading_degrees=90.0).model_dump()
        self.session.state["active_deadlocks"] = []
        self.ctx = CallbackContext(self.ic, node=constraint_predictor)

        # Run the agent node via NodeRunner
        runner = NodeRunner(node=constraint_predictor, parent_ctx=self.ctx)
        child_ctx = await runner.run(node_input={})

        typed_state = get_typed_state(child_ctx.state)
        self.assertEqual(child_ctx.route, "deadlock")
        self.assertEqual(typed_state.active_deadlocks, [["RIGID_TIMELINE", "EXTEND_SCHEDULE"]])
        self.assertEqual(typed_state.intent_vector.magnitude, 0.0)

    @patch("google.adk.models.google_llm.Gemini.generate_content_async")
    async def test_no_conflict(self, mock_generate_content_async):
        """Verify clean execution when no static or semantic conflicts exist."""
        async def mock_gen(*args, **kwargs):
            content = Content(
                role='model',
                parts=[Part(text='{"has_deadlock": false, "conflicts": []}')]
            )
            yield LlmResponse(
                model_version='gemini-2.0-flash',
                content=content
            )
            
        mock_generate_content_async.side_effect = mock_gen

        self.session.state["declared_constraints"] = ["RIGID_TIMELINE"]
        self.session.state["intent_vector"] = Vector2D(magnitude=10.0, heading_degrees=90.0).model_dump()
        self.session.state["active_deadlocks"] = []
        self.ctx = CallbackContext(self.ic, node=constraint_predictor)

        runner = NodeRunner(node=constraint_predictor, parent_ctx=self.ctx)
        child_ctx = await runner.run(node_input={})

        typed_state = get_typed_state(child_ctx.state)
        self.assertEqual(child_ctx.route, "no_deadlock")
        self.assertEqual(typed_state.active_deadlocks, [])
        self.assertEqual(typed_state.intent_vector.magnitude, 10.0)

    @patch("app.core.agents.after_predictor_callback")
    @patch("google.adk.models.google_llm.Gemini.generate_content_async")
    async def test_multiple_static_conflicts(self, mock_generate_content_async, mock_after):
        """Verify multiple static opposing constraint pairs are all detected and short-circuited."""
        self.session.state["declared_constraints"] = [
            "RIGID_TIMELINE", "FREEZE_HEADCOUNT", "REDUCE_COST", "EXPAND_SCOPE"
        ]
        self.session.state["intent_vector"] = Vector2D(magnitude=15.0, heading_degrees=180.0).model_dump()
        self.session.state["active_deadlocks"] = []
        self.ctx = CallbackContext(self.ic, node=constraint_predictor)

        runner = NodeRunner(node=constraint_predictor, parent_ctx=self.ctx)
        child_ctx = await runner.run(node_input={})

        mock_generate_content_async.assert_not_called()
        mock_after.assert_not_called()
        typed_state = get_typed_state(child_ctx.state)
        self.assertEqual(child_ctx.route, "deadlock")
        self.assertEqual(len(typed_state.active_deadlocks), 2)
        self.assertIn(["RIGID_TIMELINE", "FREEZE_HEADCOUNT"], typed_state.active_deadlocks)
        self.assertIn(["REDUCE_COST", "EXPAND_SCOPE"], typed_state.active_deadlocks)
        self.assertEqual(typed_state.intent_vector.magnitude, 0.0)
