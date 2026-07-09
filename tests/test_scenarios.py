import unittest
import math
from fastapi.testclient import TestClient
from app.main import app

class TestSimulationScenarios(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        # Clear in-memory session store before each test scenario
        from app.api.endpoints import sessions
        sessions.clear()

    def test_scenario_a_sovereign_storm(self):
        """Scenario A: 'The Sovereign Storm'
        Geopolitical headwind and economic surcharge resulting in BUDGET_OVERRUN constraint.
        """
        print("\n" + "="*80)
        print("SCENARIO A: THE SOVEREIGN STORM")
        print("="*80)

        # 1. Register profile
        payload = {
            "user_id": "user_scenario_a",
            "role": "Chief Technology Officer",
            "company_scale": "Enterprise",
            "industry": "Finance",
            "anchor_goal": {
                "title": "Scenario A Sovereign Storm Test",
                "target_timeline_months": 12,
                "budget_limit_usd": 200.0,  # Set budget low to trigger BUDGET_OVERRUN
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Balanced"
        }
        reg_resp = self.client.post("/api/v1/simulation/register", json=payload)
        self.assertEqual(reg_resp.status_code, 200)
        sim_id = reg_resp.json()["simulation_id"]
        print(f"[*] Registered session ID: {sim_id}")

        # 2. Turn 1: Israel-Iraq Conflict active (magnitude=5.0, heading=180.0 [South])
        # Intent: magnitude=10.0, heading=0.0 [North]
        print("\n--- Turn 1: Geopolitical Conflict Wind (Headwind 5.0 @ 180.0°) ---")
        eval_payload = {
            "simulation_id": sim_id,
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
            "declared_constraints": [],
            "active_storms": ["Israel-Iraq Conflict"]
        }
        response = self.client.post("/api/v1/simulation/evaluate-decision", json=eval_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Vector Math log
        telemetry = data["telemetry"]
        print(f"Intent Vector:     mag={telemetry['intent_vector']['magnitude']:.1f}, heading={telemetry['intent_vector']['heading_degrees']:.1f}°")
        print(f"Resultant Vector:  mag={telemetry['resultant_vector']['magnitude']:.1f}, heading={telemetry['resultant_vector']['heading_degrees']:.1f}°")
        print(f"Actual Position:   x={telemetry['current_position']['x']:.1f}, y={telemetry['current_position']['y']:.1f}")
        print(f"Turn Burn Rate:    {telemetry['actual_burn_rate']:.1f} USD")
        print(f"Angular Drift:     {telemetry['angular_drift_delta']:.1f}°")

        # Assertions
        # 10.0 North (dy=+10) + 5.0 South (dy=-5) = 5.0 North (dy=+5)
        self.assertAlmostEqual(telemetry["resultant_vector"]["magnitude"], 5.0)
        self.assertAlmostEqual(telemetry["resultant_vector"]["heading_degrees"], 0.0)
        self.assertAlmostEqual(telemetry["angular_drift_delta"], 0.0)
        self.assertEqual(telemetry["actual_burn_rate"], 100.0)
        self.assertEqual(data["status"], "RUNNING")
        self.assertNotIn("BUDGET_OVERRUN", data["active_constraints"])

        # 3. Turn 2: Conflict + Surging Petrol Prices (1.35x cost multiplier)
        print("\n--- Turn 2: Headwind + Petrol Surcharge (1.35x Multiplier) ---")
        eval_payload = {
            "simulation_id": sim_id,
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
            "declared_constraints": [],
            "active_storms": ["Israel-Iraq Conflict", "Surging Petrol Prices"]
        }
        response = self.client.post("/api/v1/simulation/evaluate-decision", json=eval_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Vector Math log
        telemetry = data["telemetry"]
        print(f"Intent Vector:     mag={telemetry['intent_vector']['magnitude']:.1f}, heading={telemetry['intent_vector']['heading_degrees']:.1f}°")
        print(f"Resultant Vector:  mag={telemetry['resultant_vector']['magnitude']:.1f}, heading={telemetry['resultant_vector']['heading_degrees']:.1f}°")
        print(f"Actual Position:   x={telemetry['current_position']['x']:.1f}, y={telemetry['current_position']['y']:.1f}")
        print(f"Turn Burn Rate:    {telemetry['actual_burn_rate']:.1f} USD (1.35x applied)")
        print(f"Angular Drift:     {telemetry['angular_drift_delta']:.1f}°")
        print(f"Active Constraints: {data['active_constraints']}")

        # Assertions
        self.assertAlmostEqual(telemetry["resultant_vector"]["magnitude"], 5.0)
        self.assertAlmostEqual(telemetry["resultant_vector"]["heading_degrees"], 0.0)
        self.assertEqual(telemetry["actual_burn_rate"], 135.0)
        # Budget limit was 200.0, accumulated is 100.0 + 135.0 = 235.0 > 200.0
        self.assertIn("BUDGET_OVERRUN", data["active_constraints"])
        print("[+] Budget overrun constraint verified!")

        # 4. Fetch and verify entire historical path timeline
        print("\n--- Verifying Historical Path Timeline (GET /history) ---")
        history_resp = self.client.get(f"/api/v1/simulation/{sim_id}/history")
        self.assertEqual(history_resp.status_code, 200)
        hist_data = history_resp.json()
        print(f"Total turns executed: {hist_data['total_turns_executed']}")
        
        self.assertEqual(hist_data["total_turns_executed"], 2)
        self.assertEqual(len(hist_data["history"]), 2)
        
        step_1 = hist_data["history"][0]
        step_2 = hist_data["history"][1]
        
        self.assertEqual(step_1["turn_number"], 1)
        self.assertEqual(step_1["active_storms"], ["Israel-Iraq Conflict"])
        self.assertEqual(step_1["telemetry_snapshot"]["actual_burn_rate"], 100.0)
        
        self.assertEqual(step_2["turn_number"], 2)
        self.assertEqual(step_2["active_storms"], ["Israel-Iraq Conflict", "Surging Petrol Prices"])
        self.assertEqual(step_2["telemetry_snapshot"]["actual_burn_rate"], 135.0)
        self.assertIn("BUDGET_OVERRUN", step_2["fracture_events"]["active_constraints"])
        print("[+] Chronological path timeline history verified successfully!")

    def test_scenario_b_lateral_cyclone(self):
        """Scenario B: 'The Lateral Cyclone'
        A severe crosswind causing angular track drift exceeding 15 degrees.
        """
        print("\n" + "="*80)
        print("SCENARIO B: THE LATERAL CYCLONE")
        print("="*80)

        # 1. Register profile
        payload = {
            "user_id": "user_scenario_b",
            "role": "Chief Technology Officer",
            "company_scale": "Enterprise",
            "industry": "Finance",
            "anchor_goal": {
                "title": "Scenario B Lateral Cyclone Test",
                "target_timeline_months": 12,
                "budget_limit_usd": 10000.0,
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Conservative"
        }
        reg_resp = self.client.post("/api/v1/simulation/register", json=payload)
        self.assertEqual(reg_resp.status_code, 200)
        sim_id = reg_resp.json()["simulation_id"]
        print(f"[*] Registered session ID: {sim_id}")

        # 2. Turn 1: Category 4 Cyclone (magnitude=12.0, heading=90.0 [East])
        # Intent: magnitude=10.0, heading=0.0 [North]
        print("\n--- Turn 1: Cyclone Crosswind (12.0 @ 90.0° [East]) ---")
        eval_payload = {
            "simulation_id": sim_id,
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
            "declared_constraints": [],
            "active_storms": ["Category 4 Cyclone"]
        }
        response = self.client.post("/api/v1/simulation/evaluate-decision", json=eval_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Vector Math log
        telemetry = data["telemetry"]
        print(f"Intent Vector:     mag={telemetry['intent_vector']['magnitude']:.1f}, heading={telemetry['intent_vector']['heading_degrees']:.1f}°")
        print(f"Resultant Vector:  mag={telemetry['resultant_vector']['magnitude']:.2f}, heading={telemetry['resultant_vector']['heading_degrees']:.2f}°")
        print(f"Actual Position:   x={telemetry['current_position']['x']:.2f}, y={telemetry['current_position']['y']:.2f}")
        print(f"Angular Drift:     {telemetry['angular_drift_delta']:.2f}°")
        print(f"Drift Warning Flag: {data['drift_warning']}")

        # Assertions
        # Vector addition: dx = 10 * sin(0) + 12 * sin(90) = 12
        # dy = 10 * cos(0) + 12 * cos(90) = 10
        # Resultant speed: sqrt(12^2 + 10^2) = sqrt(244) = 15.62
        # Resultant heading: atan2(12, 10) = 50.19°
        # Drift delta = 50.19° - 0° = 50.19°
        self.assertAlmostEqual(telemetry["resultant_vector"]["magnitude"], math.sqrt(244.0), places=4)
        self.assertAlmostEqual(telemetry["resultant_vector"]["heading_degrees"], math.degrees(math.atan2(12.0, 10.0)), places=4)
        self.assertTrue(data["drift_warning"])
        self.assertGreater(telemetry["angular_drift_delta"], 15.0)
        print("[+] Lateral cyclone drift delta and warnings verified!")

    def test_scenario_c_self_blocking_iceberg_crash(self):
        """Scenario C: 'The Self-Blocking Iceberg Crash'
        Opposing constraints trigger ENGINE_STALL, forcing intent to 0, causing a collision check.
        """
        print("\n" + "="*80)
        print("SCENARIO C: THE SELF-BLOCKING ICEBERG CRASH")
        print("="*80)

        # 1. Register profile
        payload = {
            "user_id": "user_scenario_c",
            "role": "Chief Technology Officer",
            "company_scale": "Enterprise",
            "industry": "Finance",
            "anchor_goal": {
                "title": "Scenario C Iceberg Crash Test",
                "target_timeline_months": 12,
                "budget_limit_usd": 10000.0,
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Balanced"
        }
        reg_resp = self.client.post("/api/v1/simulation/register", json=payload)
        self.assertEqual(reg_resp.status_code, 200)
        sim_id = reg_resp.json()["simulation_id"]
        print(f"[*] Registered session ID: {sim_id}")

        # 2. Turn 1: Category 4 Cyclone (magnitude=12.0, heading=90.0 [East])
        # Intent: magnitude=10.0, heading=0.0 [North]
        # Opposing Constraints: RIGID_TIMELINE + FREEZE_HEADCOUNT
        # Custom Iceberg: placed right in the path of the storm vector: x=20.0, y=10.0, radius=50.0
        print("\n--- Turn 1: Opposing Constraints + Custom Iceberg Collision Injected ---")
        eval_payload = {
            "simulation_id": sim_id,
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
            "declared_constraints": ["RIGID_TIMELINE", "FREEZE_HEADCOUNT"],
            "active_storms": ["Category 4 Cyclone"],
            "custom_icebergs": [
                {"name": "Compliance Deadlock Obstacle", "x": 20.0, "y": 10.0, "radius": 50.0}
            ]
        }
        response = self.client.post("/api/v1/simulation/evaluate-decision", json=eval_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Vector Math log
        telemetry = data["telemetry"]
        print(f"Intent Vector:     mag={telemetry['intent_vector']['magnitude']:.1f}, heading={telemetry['intent_vector']['heading_degrees']:.1f}°")
        print(f"Resultant Vector:  mag={telemetry['resultant_vector']['magnitude']:.1f}, heading={telemetry['resultant_vector']['heading_degrees']:.1f}° (Intent speed dropped to 0)")
        print(f"Actual Position:   x={telemetry['current_position']['x']:.1f}, y={telemetry['current_position']['y']:.1f}")
        print(f"Deadlocks Found:   {data['deadlocks']}")
        print(f"Active Constraints: {data['active_constraints']}")
        print(f"Status:            {data['status']}")
        print(f"Collision Threats: {data['collision_threats']}")
        if data["hitl_interception_data"]:
            print(f"HITL Reason:       {data['hitl_interception_data']['reason']}")

        # Assertions
        # 1. Deadlock should be returned
        self.assertEqual(data["deadlocks"], [["RIGID_TIMELINE", "FREEZE_HEADCOUNT"]])
        # 2. Intent velocity is overridden to 0. So Resultant Vector = Cyclone Storm (magnitude=12.0, heading=90.0)
        self.assertAlmostEqual(telemetry["resultant_vector"]["magnitude"], 12.0)
        self.assertAlmostEqual(telemetry["resultant_vector"]["heading_degrees"], 90.0)
        # 3. ENGINE_STALL constraint added
        self.assertIn("ENGINE_STALL", data["active_constraints"])
        # 4. Trajectory collision detects threat
        self.assertIn("Compliance Deadlock Obstacle", data["collision_threats"])
        # 5. Status is PAUSED_BY_GUARDRAIL
        self.assertEqual(data["status"], "PAUSED_BY_GUARDRAIL")
        # 6. HITL data is triggered
        self.assertIsNotNone(data["hitl_interception_data"])
        self.assertTrue(data["hitl_interception_data"]["requires_intervention"])
        print("[+] Self-blocking iceberg deadlock, engine stall, and capsule collision verified!")
