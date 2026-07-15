import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.api.endpoints import sessions
from app.core.goal_contract_service import goal_contract_repo
from app.core.persistence import workflow_store


class TestChangeRequestAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        sessions.clear()
        goal_contract_repo.clear()
        workflow_store.clear()

        # Helper registration payload
        self.reg_payload = {
            "user_id": "owner-user-1",
            "role": "Chief Technology Officer",
            "company_scale": "Enterprise",
            "industry": "Finance",
            "anchor_goal": {
                "title": "Migrate Core Infrastructure",
                "target_timeline_months": 12,
                "budget_limit_usd": 1000000.0,
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Balanced"
        }

    def test_submit_valid_change_request_success(self):
        """Verify successful change request submission referencing current active version."""
        reg_resp = self.client.post("/api/v1/simulation/register", json=self.reg_payload)
        self.assertEqual(reg_resp.status_code, 200)
        reg_data = reg_resp.json()
        sim_id = reg_data["simulation_id"]
        active_version = reg_data["active_contract_version"]
        self.assertEqual(active_version, 1)

        req_payload = {
            "simulation_id": sim_id,
            "request_id": "req-001",
            "natural_language_request": "Accelerate timeline to 6 months and increase budget by 20%.",
            "expected_goal_contract_version": 1,
            "explicit_change_intent": "Schedule compression and resource expansion",
            "actor_id": "owner-user-1"
        }

        response = self.client.post("/api/v1/simulation/change-requests", json=req_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["request_id"], "req-001")
        self.assertEqual(data["active_contract_version"], 1)
        self.assertEqual(data["idempotency_result"], "accepted")
        self.assertEqual(data["request_acceptance_status"], "RECEIVED")
        self.assertEqual(data["classification_status"], "PENDING_DRIFT_ANALYSIS")
        self.assertIn("trace_id", data)

        # Verify no goal contract mutation occurred merely by submitting a request
        contract = goal_contract_repo.get_latest_contract(reg_data["active_contract_id"])
        self.assertEqual(contract.contract_version, 1)
        self.assertEqual(contract.target_timeline_months, 12)  # Still original 12 months

    def test_stale_expected_version_returns_http_409(self):
        """Verify stale expected goal-contract version returns HTTP 409 Conflict."""
        reg_resp = self.client.post("/api/v1/simulation/register", json=self.reg_payload)
        reg_data = reg_resp.json()
        sim_id = reg_data["simulation_id"]
        contract_id = reg_data["active_contract_id"]

        # Advance goal contract version out-of-band to v2
        from app.core.goal_contract_service import ContractAmendmentMetadata
        goal_contract_repo.create_amendment_version(
            contract_id=contract_id,
            amendment_metadata=ContractAmendmentMetadata(
                amendment_id="a1", actor_id="owner-user-1", reason="Pre-test amendment",
                source_request_id="pre-req", previous_version=1, new_version=2
            ),
            new_contract_fields={"target_timeline_months": 6}
        )

        # Submit change request expecting version 1 (now stale since current is 2)
        req_payload = {
            "simulation_id": sim_id,
            "request_id": "req-stale-001",
            "natural_language_request": "Update timeline requirement.",
            "expected_goal_contract_version": 1,
            "actor_id": "owner-user-1"
        }

        response = self.client.post("/api/v1/simulation/change-requests", json=req_payload)
        self.assertEqual(response.status_code, 409)
        error_detail = response.json()["detail"]
        self.assertEqual(error_detail["error"], "STALE_GOAL_CONTRACT_VERSION")
        self.assertEqual(error_detail["current_version"], 2)
        self.assertEqual(error_detail["expected_version"], 1)

    def test_duplicate_request_id_is_idempotent(self):
        """Verify duplicate submission of request ID returns cached response with idempotent_replay."""
        reg_resp = self.client.post("/api/v1/simulation/register", json=self.reg_payload)
        sim_id = reg_resp.json()["simulation_id"]

        req_payload = {
            "simulation_id": sim_id,
            "request_id": "req-idem-100",
            "natural_language_request": "Add backup data retention mandate.",
            "expected_goal_contract_version": 1,
            "actor_id": "owner-user-1"
        }

        res1 = self.client.post("/api/v1/simulation/change-requests", json=req_payload)
        self.assertEqual(res1.status_code, 200)
        d1 = res1.json()
        self.assertEqual(d1["idempotency_result"], "accepted")

        res2 = self.client.post("/api/v1/simulation/change-requests", json=req_payload)
        self.assertEqual(res2.status_code, 200)
        d2 = res2.json()
        self.assertEqual(d2["idempotency_result"], "idempotent_replay")
        self.assertEqual(d2["request_id"], d1["request_id"])
        self.assertEqual(d2["trace_id"], d1["trace_id"])

    def test_malformed_request_returns_http_422(self):
        """Verify malformed payload (empty request text or bad version) returns HTTP 422."""
        reg_resp = self.client.post("/api/v1/simulation/register", json=self.reg_payload)
        sim_id = reg_resp.json()["simulation_id"]

        # Empty natural_language_request
        bad_payload = {
            "simulation_id": sim_id,
            "request_id": "req-bad-1",
            "natural_language_request": "   ",
            "expected_goal_contract_version": 1
        }
        res = self.client.post("/api/v1/simulation/change-requests", json=bad_payload)
        self.assertEqual(res.status_code, 422)

    def test_unknown_simulation_returns_http_404(self):
        """Verify request referencing missing simulation returns HTTP 404."""
        req_payload = {
            "simulation_id": "nonexistent-sim-uuid",
            "request_id": "req-404",
            "natural_language_request": "Some change request",
            "expected_goal_contract_version": 1
        }
        res = self.client.post("/api/v1/simulation/change-requests", json=req_payload)
        self.assertEqual(res.status_code, 404)

    def test_actor_id_mismatch_returns_http_403(self):
        """Verify submitting change request with mismatched actor ID returns HTTP 403 Forbidden."""
        reg_resp = self.client.post("/api/v1/simulation/register", json=self.reg_payload)
        sim_id = reg_resp.json()["simulation_id"]

        req_payload = {
            "simulation_id": sim_id,
            "request_id": "req-auth-fail",
            "natural_language_request": "Unauthorized change attempt",
            "expected_goal_contract_version": 1,
            "actor_id": "unauthorized-hacker-id"
        }
        res = self.client.post("/api/v1/simulation/change-requests", json=req_payload)
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
