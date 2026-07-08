import unittest
from fastapi.testclient import TestClient
from app.main import app

class TestPolarisAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        # Clear in-memory session store before each test to maintain isolation
        from app.api.endpoints import sessions
        sessions.clear()

    def test_health(self):
        """Verify the main health check endpoint."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_status(self):
        """Verify the API router status endpoint."""
        response = self.client.get("/api/v1/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready"})

    def test_register_simulation_success(self):
        """Verify simulation registration succeeds with valid profile fields."""
        payload = {
            "user_id": "test_user_1",
            "role": "Chief Technology Officer",
            "company_scale": "Enterprise",
            "industry": "Finance",
            "anchor_goal": {
                "title": "Migrate Core Infrastructure",
                "target_timeline_months": 18,
                "budget_limit_usd": 5000000.0,
                "reliability_target_sla": 99.95
            },
            "risk_tolerance": "Balanced"
        }
        response = self.client.post("/api/v1/simulation/register", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("simulation_id", data)
        self.assertEqual(data["quantum_mountain_coordinates"], {"x": 0.0, "y": 1000.0})
        self.assertEqual(data["user_profile"]["user_id"], "test_user_1")

    def test_register_simulation_validation_error(self):
        """Verify registration fails with 422 if profile SLA value exceeds 100.0."""
        payload = {
            "user_id": "test_user_1",
            "role": "Chief Technology Officer",
            "company_scale": "Enterprise",
            "industry": "Finance",
            "anchor_goal": {
                "title": "Migrate Core Infrastructure",
                "target_timeline_months": 18,
                "budget_limit_usd": 5000000.0,
                "reliability_target_sla": 105.0  # Invalid SLA rate
            },
            "risk_tolerance": "Balanced"
        }
        response = self.client.post("/api/v1/simulation/register", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_evaluate_decision_normal(self):
        """Verify standard path evaluation works correctly and updates position."""
        # 1. Register session
        reg_payload = {
            "user_id": "test_user_2",
            "role": "CTO",
            "company_scale": "Scaleup",
            "industry": "Logistics",
            "anchor_goal": {
                "title": "Optimize Routes",
                "target_timeline_months": 6,
                "budget_limit_usd": 250000.0,
                "reliability_target_sla": 99.0
            },
            "risk_tolerance": "Conservative"
        }
        reg_resp = self.client.post("/api/v1/simulation/register", json=reg_payload)
        sim_id = reg_resp.json()["simulation_id"]

        # 2. Evaluate normal decision going East
        eval_payload = {
            "simulation_id": sim_id,
            "intent_vector": {"magnitude": 15.0, "heading_degrees": 90.0},
            "declared_constraints": [],
            "active_storms": []
        }
        response = self.client.post("/api/v1/simulation/evaluate-decision", json=eval_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["simulation_id"], sim_id)
        # Position should advance by (dx=15, dy=0)
        self.assertAlmostEqual(data["telemetry"]["current_position"]["x"], 15.0)
        self.assertAlmostEqual(data["telemetry"]["current_position"]["y"], 0.0)
        self.assertFalse(data["drift_warning"])
        self.assertEqual(data["deadlocks"], [])
        self.assertEqual(data["collision_threats"], [])
        self.assertIsNone(data["hitl_interception_data"])

    def test_evaluate_decision_deadlock(self):
        """Verify logical deadlock active state drops intent to 0 and raises HITL."""
        reg_resp = self.client.post("/api/v1/simulation/register", json={
            "user_id": "user3", "role": "CTO", "company_scale": "Large", "industry": "Energy",
            "anchor_goal": {"title": "Build Green Grid", "target_timeline_months": 24, "budget_limit_usd": 10000000.0, "reliability_target_sla": 99.99},
            "risk_tolerance": "Balanced"
        })
        sim_id = reg_resp.json()["simulation_id"]

        eval_payload = {
            "simulation_id": sim_id,
            "intent_vector": {"magnitude": 25.0, "heading_degrees": 0.0},
            "declared_constraints": ["RIGID_TIMELINE", "FREEZE_HEADCOUNT"],  # OPPOSING pair
            "active_storms": ["Category 4 Cyclone"]  # East crosswind: mag=12, heading=90
        }
        response = self.client.post("/api/v1/simulation/evaluate-decision", json=eval_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Deadlock should be active
        self.assertEqual(data["deadlocks"], [["RIGID_TIMELINE", "FREEZE_HEADCOUNT"]])
        # Intent drops to 0. Position advances only by cyclone storm vector (12, 0)
        self.assertAlmostEqual(data["telemetry"]["current_position"]["x"], 12.0)
        self.assertAlmostEqual(data["telemetry"]["current_position"]["y"], 0.0)
        self.assertIsNotNone(data["hitl_interception_data"])
        self.assertTrue(data["hitl_interception_data"]["requires_intervention"])
        self.assertIn("Active logical deadlocks", data["hitl_interception_data"]["reason"])

    def test_evaluate_decision_collision(self):
        """Verify capsule trajectory look-ahead detects threat and triggers HITL warning."""
        reg_resp = self.client.post("/api/v1/simulation/register", json={
            "user_id": "user4", "role": "CTO", "company_scale": "Large", "industry": "Energy",
            "anchor_goal": {"title": "Test Collision", "target_timeline_months": 12, "budget_limit_usd": 100000.0, "reliability_target_sla": 99.0},
            "risk_tolerance": "Aggressive"
        })
        sim_id = reg_resp.json()["simulation_id"]

        # Default Iceberg: "Scope Creep" at (-200, 100), radius 100
        # Segment starts at (0,0), goes West (270 deg) with magnitude 100 (ends at -300, 0)
        # Passing point (-200, 0) has distance 100.0 to iceberg (-200, 100), triggering collision
        eval_payload = {
            "simulation_id": sim_id,
            "intent_vector": {"magnitude": 100.0, "heading_degrees": 270.0},
            "declared_constraints": [],
            "active_storms": []
        }
        response = self.client.post("/api/v1/simulation/evaluate-decision", json=eval_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertIn("Scope Creep", data["collision_threats"])
        self.assertIsNotNone(data["hitl_interception_data"])
        self.assertTrue(data["hitl_interception_data"]["requires_intervention"])
        self.assertIn("Imminent collision threat", data["hitl_interception_data"]["reason"])

    def test_evaluate_decision_session_not_found(self):
        """Verify endpoint returns 404 when simulation session UUID does not exist."""
        eval_payload = {
            "simulation_id": "nonexistent-uuid",
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
            "declared_constraints": [],
            "active_storms": []
        }
        response = self.client.post("/api/v1/simulation/evaluate-decision", json=eval_payload)
        self.assertEqual(response.status_code, 404)
