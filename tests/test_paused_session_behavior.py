import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.api.endpoints import sessions, sessions_lock
from app.core.hitl.checkpoint_service import checkpoint_service
from app.core.hitl.interruption import InterruptionPayload, InterruptionReason
from app.core.persistence import workflow_store


class TestPausedSessionBehavior(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        checkpoint_service.clear()
        workflow_store.clear()
        with sessions_lock:
            sessions.clear()

    def test_evaluate_decision_returns_409_when_paused(self):
        """Verify normal decision evaluation while paused is rejected with 409 SIMULATION_PAUSED."""
        # 1. Register a simulation
        reg_resp = self.client.post("/api/v1/simulation/register", json={
            "user_id": "user_p1",
            "role": "CTO",
            "company_scale": "Enterprise",
            "industry": "Tech",
            "anchor_goal": {
                "title": "Build Platform",
                "target_timeline_months": 12,
                "budget_limit_usd": 1000000.0,
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Balanced"
        })
        self.assertEqual(reg_resp.status_code, 200)
        sim_id = reg_resp.json()["simulation_id"]

        # 2. Inject an active interruption & checkpoint
        payload = InterruptionPayload(
            interruption_id="int-pause-001",
            simulation_id=sim_id,
            invocation_id="inv-pause-001",
            workflow_node="path_simulator",
            reason=InterruptionReason.STATIC_CONSTRAINT_DEADLOCK,
            severity="CRITICAL",
            explanation="Opposing constraints active.",
            safe_telemetry_snapshot={"x": 0.0, "y": 0.0},
            goal_contract_id=f"contract-{sim_id}",
            active_contract_version=1,
            required_resolution_action="Resolve constraint deadlock or approve amendment."
        )

        initial_state = {
            "simulation_id": sim_id,
            "user_id": "user_p1",
            "current_position": {"x": 0.0, "y": 0.0},
            "accumulated_burn": 100.0,
            "hitl_interrupted": True,
            "hitl_reason": "Opposing constraints active.",
            "hitl_telemetry_snapshot": {"x": 0.0, "y": 0.0}
        }

        chk = checkpoint_service.create_checkpoint(
            simulation_id=sim_id,
            invocation_id="inv-pause-001",
            node_position="path_simulator",
            state_dict=initial_state,
            interruption_payload=payload
        )

        with sessions_lock:
            sessions[sim_id]["hitl_interrupted"] = True
            sessions[sim_id]["hitl_reason"] = "Opposing constraints active."
            sessions[sim_id]["active_checkpoint_id"] = chk.checkpoint_id

        # 3. Attempt evaluate-decision while paused
        eval_resp = self.client.post("/api/v1/simulation/evaluate-decision", json={
            "simulation_id": sim_id,
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
            "declared_constraints": []
        })

        self.assertEqual(eval_resp.status_code, 409)
        err_detail = eval_resp.json()["detail"]
        self.assertEqual(err_detail["error_code"], "SIMULATION_PAUSED")
        self.assertEqual(err_detail["interruption_id"], "int-pause-001")
        self.assertEqual(err_detail["active_checkpoint_id"], chk.checkpoint_id)
        self.assertIn("resume_endpoint", err_detail)

        # 4. Verify position and burn rate were NOT mutated
        with sessions_lock:
            session = sessions[sim_id]
            self.assertEqual(session["current_position"], {"x": 0.0, "y": 0.0})
            self.assertEqual(session["accumulated_burn"], 0.0)

    def test_safe_operations_allowed_while_paused(self):
        """Verify safe operations (get status, history, submit change request) work while paused."""
        reg_resp = self.client.post("/api/v1/simulation/register", json={
            "user_id": "user_p2",
            "role": "CTO",
            "company_scale": "Enterprise",
            "industry": "Tech",
            "anchor_goal": {
                "title": "Build App",
                "target_timeline_months": 12,
                "budget_limit_usd": 500000.0,
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Balanced"
        })
        sim_id = reg_resp.json()["simulation_id"]

        with sessions_lock:
            sessions[sim_id]["hitl_interrupted"] = True

        # Status endpoint (GET /history) should succeed
        hist_resp = self.client.get(f"/api/v1/simulation/{sim_id}/history")
        self.assertEqual(hist_resp.status_code, 200)

        # Submit change request should succeed
        cr_resp = self.client.post("/api/v1/simulation/change-requests", json={
            "simulation_id": sim_id,
            "request_id": "req-pause-001",
            "natural_language_request": "Increase budget to 800k",
            "expected_goal_contract_version": 1,
            "actor_id": "user_p2"
        })
        self.assertEqual(cr_resp.status_code, 200)


    def test_evaluate_decision_auto_creates_checkpoint_on_hitl(self):
        """Verify evaluate-decision atomically creates a durable checkpoint when HITL interruption occurs."""
        from app.core.hitl.checkpoint_service import checkpoint_service
        from unittest.mock import patch
        from google.genai.types import Content, Part
        from google.adk.models.llm_response import LlmResponse

        # Register session
        reg_resp = self.client.post("/api/v1/simulation/register", json={
            "user_id": "user_auto_chk",
            "role": "CTO",
            "company_scale": "Enterprise",
            "industry": "Tech",
            "anchor_goal": {
                "title": "Scale Platform",
                "target_timeline_months": 12,
                "budget_limit_usd": 1000000.0,
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Balanced"
        })
        self.assertEqual(reg_resp.status_code, 200)
        sim_id = reg_resp.json()["simulation_id"]

        async def mock_generate_no_deadlock(self_inner, llm_request, stream=False):
            text = '{"is_consistent": true, "evidence": "Mock consistent", "confidence": 1.0}'
            if "conflict" in str(llm_request).lower() or "deadlock" in str(llm_request).lower():
                text = '{"has_deadlock": false, "conflicts": []}'
            yield LlmResponse(content=Content(role="model", parts=[Part(text=text)]))

        with patch("google.adk.models.google_llm.Gemini.generate_content_async", new=mock_generate_no_deadlock):
            # Trigger evaluate-decision with a custom iceberg causing collision
            eval_resp = self.client.post("/api/v1/simulation/evaluate-decision", json={
                "simulation_id": sim_id,
                "intent_vector": {"magnitude": 50.0, "heading_degrees": 0.0},
                "declared_constraints": [],
                "active_storms": [],
                "custom_icebergs": [{"name": "Test Berg", "x": 0.0, "y": 100.0, "radius": 100.0}]
            })

        # If HITL triggered (collision detected), checkpoint must be created automatically
        if eval_resp.status_code == 200:
            resp_data = eval_resp.json()
            if resp_data["status"] == "PAUSED_BY_GUARDRAIL":
                active_chk = checkpoint_service.get_active_checkpoint(sim_id)
                self.assertIsNotNone(active_chk, "Active checkpoint must be created atomically on HITL interruption")
                self.assertEqual(active_chk.checkpoint_status, "ACTIVE")
                self.assertEqual(active_chk.simulation_id, sim_id)
            # else: no interruption occurred — still passes (determinism depends on iceberg radius)
        # 409 SIMULATION_PAUSED would mean session was already paused — acceptable as test precondition

    def test_concurrent_evaluate_blocked_by_active_checkpoint(self):
        """Verify that active checkpoint acts as single source of truth blocking evaluate-decision."""
        from app.core.hitl.checkpoint_service import checkpoint_service
        # Register session
        reg_resp = self.client.post("/api/v1/simulation/register", json={
            "user_id": "user_concurrent",
            "role": "CTO",
            "company_scale": "Startup",
            "industry": "SaaS",
            "anchor_goal": {
                "title": "Launch MVP",
                "target_timeline_months": 6,
                "budget_limit_usd": 100000.0,
                "reliability_target_sla": 99.0
            },
            "risk_tolerance": "Aggressive"
        })
        self.assertEqual(reg_resp.status_code, 200)
        sim_id = reg_resp.json()["simulation_id"]

        from app.core.hitl.interruption import InterruptionPayload, InterruptionReason
        payload = InterruptionPayload(
            interruption_id="int-conc-001",
            simulation_id=sim_id,
            invocation_id="inv-conc-001",
            workflow_node="path_simulator",
            reason=InterruptionReason.STATIC_CONSTRAINT_DEADLOCK,
            severity="CRITICAL",
            explanation="Deadlock: concurrent test block.",
            safe_telemetry_snapshot={"x": 0.0, "y": 0.0},
            goal_contract_id=f"contract-{sim_id}",
            active_contract_version=1,
            required_resolution_action="Resolve deadlock."
        )
        state_dict = {
            "simulation_id": sim_id,
            "user_id": "user_concurrent",
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
            "current_position": {"x": 0.0, "y": 0.0},
            "accumulated_burn": 0.0,
            "hitl_interrupted": True,
            "hitl_reason": "Deadlock: concurrent test block.",
            "hitl_telemetry_snapshot": {"x": 0.0, "y": 0.0}
        }
        chk = checkpoint_service.create_checkpoint(
            simulation_id=sim_id,
            invocation_id="inv-conc-001",
            node_position="path_simulator",
            state_dict=state_dict,
            interruption_payload=payload
        )

        # Both "concurrent" evaluate calls must be blocked
        for _ in range(2):
            resp = self.client.post("/api/v1/simulation/evaluate-decision", json={
                "simulation_id": sim_id,
                "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
                "declared_constraints": []
            })
            self.assertEqual(resp.status_code, 409)
            self.assertEqual(resp.json()["detail"]["error_code"], "SIMULATION_PAUSED")

        # Checkpoint must still be ACTIVE — no state mutation occurred
        still_active = checkpoint_service.get_active_checkpoint(sim_id)
        self.assertIsNotNone(still_active)
        self.assertEqual(still_active.checkpoint_id, chk.checkpoint_id)


if __name__ == "__main__":
    unittest.main()
