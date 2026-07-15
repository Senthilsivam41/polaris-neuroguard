import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.api.endpoints import sessions, sessions_lock
from app.core.hitl.checkpoint_service import checkpoint_service
from app.core.hitl.interruption import InterruptionPayload, InterruptionReason
from app.core.hitl.resume_service import resume_service


class TestHITLResumeAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        checkpoint_service.clear()
        resume_service.clear()
        with sessions_lock:
            sessions.clear()

        # Helper: register simulation
        reg_resp = self.client.post("/api/v1/simulation/register", json={
            "user_id": "owner_user",
            "role": "CTO",
            "company_scale": "Enterprise",
            "industry": "Tech",
            "anchor_goal": {
                "title": "Migrate Cloud",
                "target_timeline_months": 12,
                "budget_limit_usd": 1000000.0,
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Balanced"
        })
        self.assertEqual(reg_resp.status_code, 200)
        self.sim_id = reg_resp.json()["simulation_id"]
        self.contract_id = f"contract-{self.sim_id}"

    def _create_active_interruption_and_checkpoint(self, sim_id: str, invocation_id="inv-r-1"):
        from app.api.endpoints import runner
        adk_sess = runner.session_service.get_session_sync(app_name="polaris-neuroguard", user_id="owner_user", session_id=sim_id)
        if adk_sess is None:
            runner.session_service.create_session_sync(app_name="polaris-neuroguard", user_id="owner_user", session_id=sim_id)

        payload = InterruptionPayload(
            interruption_id="int-res-001",
            simulation_id=sim_id,
            invocation_id=invocation_id,
            workflow_node="path_simulator",
            reason=InterruptionReason.STATIC_CONSTRAINT_DEADLOCK,
            severity="CRITICAL",
            explanation="Deadlock detected.",
            safe_telemetry_snapshot={"x": 0.0, "y": 0.0},
            goal_contract_id=f"contract-{sim_id}",
            active_contract_version=1,
            required_resolution_action="Resolve deadlock condition"
        )
        state_dict = {
            "simulation_id": sim_id,
            "user_id": "owner_user",
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
            "current_position": {"x": 0.0, "y": 0.0},
            "accumulated_burn": 0.0,
            "active_deadlocks": [["RIGID_TIMELINE", "FREEZE_HEADCOUNT"]],
            "hitl_interrupted": True,
            "hitl_reason": "Deadlock detected.",
            "hitl_telemetry_snapshot": {"x": 0.0, "y": 0.0}
        }
        chk = checkpoint_service.create_checkpoint(
            simulation_id=sim_id,
            invocation_id=invocation_id,
            node_position="path_simulator",
            state_dict=state_dict,
            interruption_payload=payload,
            active_contract_id=f"contract-{sim_id}",
            active_contract_version=1
        )
        with sessions_lock:
            sessions[sim_id]["hitl_interrupted"] = True
            sessions[sim_id]["hitl_reason"] = "Deadlock detected."
            sessions[sim_id]["paused_invocation_id"] = invocation_id
            sessions[sim_id]["active_checkpoint_id"] = chk.checkpoint_id
        return chk

    def test_resume_missing_checkpoint_404(self):
        """Verify resume returns HTTP 404 CHECKPOINT_NOT_FOUND when checkpoint ID does not exist."""
        resp = self.client.post(f"/api/v1/simulation/{self.sim_id}/resume", json={
            "checkpoint_id": "chk-nonexistent",
            "resume_request_id": "req-r-1",
            "actor_id": "owner_user",
            "resolution_action": "Resolved deadlock",
            "expected_checkpoint_version": 1
        })
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"]["error_code"], "CHECKPOINT_NOT_FOUND")

    def test_resume_unauthorized_actor_403(self):
        """Verify resume returns HTTP 403 UNAUTHORIZED_RESUME when actor is not owner."""
        chk = self._create_active_interruption_and_checkpoint(self.sim_id)
        resp = self.client.post(f"/api/v1/simulation/{self.sim_id}/resume", json={
            "checkpoint_id": chk.checkpoint_id,
            "resume_request_id": "req-r-2",
            "actor_id": "impostor_user",
            "resolution_action": "Resolved deadlock",
            "expected_checkpoint_version": 1
        })
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["error_code"], "UNAUTHORIZED_RESUME")

    def test_resume_stale_checkpoint_version_409(self):
        """Verify resume returns HTTP 409 CHECKPOINT_VERSION_CONFLICT when expected checkpoint version is stale."""
        chk = self._create_active_interruption_and_checkpoint(self.sim_id)
        resp = self.client.post(f"/api/v1/simulation/{self.sim_id}/resume", json={
            "checkpoint_id": chk.checkpoint_id,
            "resume_request_id": "req-r-3",
            "actor_id": "owner_user",
            "resolution_action": "Resolved deadlock",
            "expected_checkpoint_version": 999
        })
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["detail"]["error_code"], "CHECKPOINT_VERSION_CONFLICT")

    def test_resume_successful_and_idempotent_replay(self):
        """Verify successful resume resolves checkpoint, clears paused state, and supports idempotent replay."""
        chk = self._create_active_interruption_and_checkpoint(self.sim_id)

        # First resume call -> Resolves blocking condition
        resp1 = self.client.post(f"/api/v1/simulation/{self.sim_id}/resume", json={
            "checkpoint_id": chk.checkpoint_id,
            "resume_request_id": "req-r-4",
            "actor_id": "owner_user",
            "resolution_action": "Resolved deadlock by removing declared constraint",
            "expected_checkpoint_version": 1,
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
            "declared_constraints": []  # Cleared constraints so no longer deadlocked
        })

        self.assertEqual(resp1.status_code, 200)
        res_data1 = resp1.json()
        self.assertEqual(res_data1["resume_status"], "RUNNING")
        self.assertEqual(res_data1["checkpoint_id"], chk.checkpoint_id)

        # Session should no longer be hitl_interrupted
        with sessions_lock:
            self.assertFalse(sessions[self.sim_id].get("hitl_interrupted"))

        # Second resume call with SAME resume_request_id -> Replays original response idempotently
        resp2 = self.client.post(f"/api/v1/simulation/{self.sim_id}/resume", json={
            "checkpoint_id": chk.checkpoint_id,
            "resume_request_id": "req-r-4",
            "actor_id": "owner_user",
            "resolution_action": "Resolved deadlock by removing declared constraint",
            "expected_checkpoint_version": 1,
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
            "declared_constraints": []
        })

        self.assertEqual(resp2.status_code, 200)
        res_data2 = resp2.json()
        self.assertEqual(res_data2["correlation_id"], res_data1["correlation_id"])
        self.assertEqual(res_data2["resume_status"], res_data1["resume_status"])

    def test_resume_insufficient_resolution_keeps_paused(self):
        """Verify resume with insufficient resolution keeps session paused and returns structured error or paused status."""
        chk = self._create_active_interruption_and_checkpoint(self.sim_id)

        # Attempt to resume without providing any resolution (deadlocks still present)
        resp = self.client.post(f"/api/v1/simulation/{self.sim_id}/resume", json={
            "checkpoint_id": chk.checkpoint_id,
            "resume_request_id": "req-r-5",
            "actor_id": "owner_user",
            "resolution_action": "",  # Empty resolution
            "expected_checkpoint_version": 1
        })

        self.assertIn(resp.status_code, [400, 409])
        if resp.status_code == 400:
            self.assertEqual(resp.json()["detail"]["error_code"], "RESOLUTION_REQUIRED")
        
        # Session must remain interrupted
        with sessions_lock:
            self.assertTrue(sessions[self.sim_id].get("hitl_interrupted"))


if __name__ == "__main__":
    unittest.main()
