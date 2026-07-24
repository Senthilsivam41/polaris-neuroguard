import unittest
from unittest.mock import patch
from google.genai.types import Content, Part
from google.adk.models.llm_response import LlmResponse
from google.adk.agents.invocation_context import InvocationContext
from google.adk.sessions import Session, InMemorySessionService
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.run_config import RunConfig
from google.adk.workflow._node_runner import NodeRunner
from app.core.state import SimulationStateSchema, Vector2D, GoalModel
from app.core.agents import goal_analyzer, GoalAnalysisResult

class TestGoalAnalyzerAgent(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Pin the agent to a real Gemini model name so the Gemini patches in
        # these tests take effect even when OFFLINE_MODE swaps in the mock LLM.
        self._model_patcher = patch.object(goal_analyzer, "model", "gemini-2.0-flash")
        self._model_patcher.start()
        self.addCleanup(self._model_patcher.stop)
        self.session_service = InMemorySessionService()
        self.session = Session(id="test_session", app_name="test_app", user_id="test_user")
        self.session.state = {
            "risk_tolerance": "Balanced",
            "anchor_goal": GoalModel(
                title="Migrate Core Infrastructure",
                target_timeline_months=12,
                budget_limit_usd=1000000.0,
                reliability_target_sla=99.9
            ),
            "intent_vector": Vector2D(magnitude=10.0, heading_degrees=90.0),
            "declared_constraints": ["RIGID_TIMELINE"]
        }
        self.ic = InvocationContext(
            session_service=self.session_service,
            session=self.session,
            invocation_id="test_inv",
            run_config=RunConfig()
        )
        import asyncio
        self.ic._event_queue = asyncio.Queue()
        self.ctx = CallbackContext(self.ic, node=goal_analyzer)
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

    @patch("google.adk.models.google_llm.Gemini.generate_content_async")
    async def test_consistent_goal_evaluation(self, mock_generate_content_async):
        """Verify that a consistent request routes to 'consistent'."""
        async def mock_gen(*args, **kwargs):
            content = Content(
                role='model',
                parts=[Part(text='{"is_consistent": true, "evidence": "The steering velocity and constraints are within safe margins.", "confidence": 0.95}')]
            )
            yield LlmResponse(
                model_version='gemini-2.0-flash',
                content=content
            )
            
        mock_generate_content_async.side_effect = mock_gen

        # Run the agent node via NodeRunner
        runner = NodeRunner(node=goal_analyzer, parent_ctx=self.ctx)
        child_ctx = await runner.run(node_input={})
        
        # Verify route is set to consistent
        self.assertEqual(child_ctx.route, "consistent")

    @patch("google.adk.models.google_llm.Gemini.generate_content_async")
    async def test_inconsistent_goal_evaluation(self, mock_generate_content_async):
        """Verify that an inconsistent request (e.g. violating risk tolerance) routes to 'inconsistent'."""
        async def mock_gen(*args, **kwargs):
            content = Content(
                role='model',
                parts=[Part(text='{"is_consistent": false, "evidence": "High magnitude intent violates Conservative risk tolerance.", "confidence": 0.98}')]
            )
            yield LlmResponse(
                model_version='gemini-2.0-flash',
                content=content
            )
            
        mock_generate_content_async.side_effect = mock_gen

        # Change risk tolerance to Conservative
        self.session.state["risk_tolerance"] = "Conservative"
        self.ctx = CallbackContext(self.ic, node=goal_analyzer)

        # Run the agent node via NodeRunner
        runner = NodeRunner(node=goal_analyzer, parent_ctx=self.ctx)
        child_ctx = await runner.run(node_input={})

        # Verify route is set to inconsistent
        self.assertEqual(child_ctx.route, "inconsistent")
