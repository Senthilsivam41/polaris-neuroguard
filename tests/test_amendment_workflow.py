import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.api.endpoints import sessions
from app.core.goal_contract_service import goal_contract_repo
from app.core.amendment_workflow import amendment_workflow_service


class TestAmendmentWorkflow(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        sessions.clear()
        goal_contract_repo.clear()
        amendment_workflow_service.clear()

        # Registration baseline
        self.reg_payload = {
            "user_id": "cto-lead-1",
            "role": "Chief Technology Officer",
            "company_scale": "Enterprise",
            "industry": "Finance",
            "anchor_goal": {
                "title": "Migrate Core Database",
                "target_timeline_months": 12,
                "budget_limit_usd": 1000000.0,
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Balanced"
        }

    def test_e2e_baseline_to_evaluation_to_confirmation_to_version_2(self):
        """End-to-End: baseline v1 -> change request -> evaluation -> confirm -> active GoalContract version 2."""
        # 1. Register simulation session
        reg_resp = self.client.post("/api/v1/simulation/register", json=self.reg_payload)
        sim_id = reg_resp.json()["simulation_id"]
        contract_id = reg_resp.json()["active_contract_id"]

        # 2. Submit change request
        submit_payload = {
            "simulation_id": sim_id,
            "request_id": "req-amend-001",
            "natural_language_request": "Increase budget to $1,500,000 USD and add Multi-Region Backup deliverable.",
            "expected_goal_contract_version": 1,
            "actor_id": "cto-lead-1"
        }
        sub_resp = self.client.post("/api/v1/simulation/change-requests", json=submit_payload)
        self.assertEqual(sub_resp.status_code, 200)

        # 3. Evaluate drift
        eval_resp = self.client.post(f"/api/v1/simulation/change-requests/req-amend-001/evaluate")
        self.assertEqual(eval_resp.status_code, 200)
        eval_data = eval_resp.json()
        self.assertEqual(eval_data["active_contract_version"], 1)
        self.assertEqual(eval_data["amendment_status"], "PENDING_CONFIRMATION")
        self.assertTrue(eval_data["contract_unchanged"])  # Evaluation did NOT mutate contract

        # 4. Confirm amendment
        confirm_payload = {
            "actor_id": "cto-lead-1",
            "decision": "APPROVE",
            "rationale": "Board approved budget increase for multi-region backup."
        }
        conf_resp = self.client.post(f"/api/v1/simulation/change-requests/req-amend-001/confirm", json=confirm_payload)
        self.assertEqual(conf_resp.status_code, 200)
        conf_data = conf_resp.json()

        self.assertEqual(conf_data["amendment_status"], "APPROVED")
        self.assertEqual(conf_data["active_contract_version"], 2)
        self.assertFalse(conf_data["idempotent_replay"])

        # 5. Verify active contract is now version 2
        latest_contract = goal_contract_repo.get_latest_contract(contract_id)
        self.assertEqual(latest_contract.contract_version, 2)
        self.assertEqual(latest_contract.budget_limit_usd, 1500000.0)
        self.assertIn("Multi-Region Backup", latest_contract.in_scope_items)

        # 6. Verify version 1 remains unchanged in repository
        v1_contract = goal_contract_repo.get_contract_version(contract_id, 1)
        self.assertEqual(v1_contract.budget_limit_usd, 1000000.0)

    def test_e2e_conflict_request_rejection(self):
        """End-to-End: baseline -> direct constraint conflict request -> rejection leaves version 1 active."""
        reg_resp = self.client.post("/api/v1/simulation/register", json=self.reg_payload)
        sim_id = reg_resp.json()["simulation_id"]
        contract_id = reg_resp.json()["active_contract_id"]

        # Add RIGID_TIMELINE constraint to baseline v1
        v1 = goal_contract_repo.get_latest_contract(contract_id)
        v1.constraints.append("RIGID_TIMELINE")

        submit_payload = {
            "simulation_id": sim_id,
            "request_id": "req-conflict-002",
            "natural_language_request": "Extend schedule and add EXTEND_SCHEDULE constraint.",
            "expected_goal_contract_version": 1,
            "actor_id": "cto-lead-1"
        }
        self.client.post("/api/v1/simulation/change-requests", json=submit_payload)
        eval_resp = self.client.post("/api/v1/simulation/change-requests/req-conflict-002/evaluate")
        self.assertEqual(eval_resp.status_code, 200)

        # Confirm with REJECT decision
        rej_resp = self.client.post(
            "/api/v1/simulation/change-requests/req-conflict-002/reject",
            json={"actor_id": "cto-lead-1", "decision": "REJECT", "rationale": "Violates rigid timeline constraint."}
        )
        self.assertEqual(rej_resp.status_code, 200)
        self.assertEqual(rej_resp.json()["amendment_status"], "REJECTED")

        # Verify active contract is still version 1
        latest = goal_contract_repo.get_latest_contract(contract_id)
        self.assertEqual(latest.contract_version, 1)

    def test_idempotent_confirmation_handling(self):
        """Verify duplicate confirmation call returns cached response with idempotent_replay=True."""
        reg_resp = self.client.post("/api/v1/simulation/register", json=self.reg_payload)
        sim_id = reg_resp.json()["simulation_id"]

        submit_payload = {
            "simulation_id": sim_id,
            "request_id": "req-idem-003",
            "natural_language_request": "Increase budget to $1,200,000 USD",
            "expected_goal_contract_version": 1,
            "actor_id": "cto-lead-1"
        }
        self.client.post("/api/v1/simulation/change-requests", json=submit_payload)
        self.client.post("/api/v1/simulation/change-requests/req-idem-003/evaluate")

        conf_payload = {"actor_id": "cto-lead-1", "decision": "APPROVE", "rationale": "Approve once"}
        r1 = self.client.post("/api/v1/simulation/change-requests/req-idem-003/confirm", json=conf_payload)
        self.assertEqual(r1.status_code, 200)
        self.assertFalse(r1.json()["idempotent_replay"])

        r2 = self.client.post("/api/v1/simulation/change-requests/req-idem-003/confirm", json=conf_payload)
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json()["idempotent_replay"])

    def test_change_requests_history_endpoint(self):
        """Verify GET /api/v1/simulation/{id}/change-requests/history returns complete timeline logs."""
        reg_resp = self.client.post("/api/v1/simulation/register", json=self.reg_payload)
        sim_id = reg_resp.json()["simulation_id"]

        self.client.post("/api/v1/simulation/change-requests", json={
            "simulation_id": sim_id, "request_id": "req-hist-1",
            "natural_language_request": "Request 1", "expected_goal_contract_version": 1, "actor_id": "cto-lead-1"
        })
        self.client.post("/api/v1/simulation/change-requests/req-hist-1/evaluate")

        hist_resp = self.client.get(f"/api/v1/simulation/{sim_id}/change-requests/history")
        self.assertEqual(hist_resp.status_code, 200)
        data = hist_resp.json()
        self.assertEqual(data["simulation_id"], sim_id)
        self.assertEqual(data["total_change_requests"], 1)
        self.assertIsNotNone(data["change_requests_history"][0]["evaluation"])


if __name__ == "__main__":
    unittest.main()
