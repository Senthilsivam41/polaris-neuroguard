import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.api.endpoints import sessions, sessions_lock
from app.core.hitl.checkpoint_service import checkpoint_service
from app.core.hitl.interruption import InterruptionPayload, InterruptionReason


class TestPausedSessionBehavior(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        checkpoint_service.clear()
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


if __name__ == "__main__":
    unittest.main()
