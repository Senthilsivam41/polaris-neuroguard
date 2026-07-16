import os
# Configure environment variables before importing app modules to pass validation check
os.environ["OFFLINE_MODE"] = "true"
os.environ["POLARIS_API_TOKENS"] = '{"token-owner":{"actor_id":"user-owner","roles":["operator"]}}'

import unittest
import asyncio
import time
import json
import sqlite3
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.api.endpoints import sessions, sessions_lock
from app.core.config import API_TOKENS
from app.core.security import redact, audit_event, Principal, current_principal
from app.core.persistence import workflow_store


class TestSecurityHardening(unittest.TestCase):
    def setUp(self):
        # Clean session store and persistence DB before each test
        workflow_store.clear()
        with sessions_lock:
            sessions.clear()

        # Define test tokens
        self.tokens_patch = {
            "token-owner": {"actor_id": "user-owner", "roles": ["operator"]},
            "token-other": {"actor_id": "user-other", "roles": ["operator"]},
            "token-reviewer": {"actor_id": "user-reviewer", "roles": ["reviewer"]},
            "token-override": {"actor_id": "user-override", "roles": ["override"]},
            "token-admin": {"actor_id": "user-admin", "roles": ["admin"]},
        }
        self.api_tokens_patcher = patch("app.core.security.API_TOKENS", self.tokens_patch)
        self.api_tokens_patcher.start()

        self.auth_required_patcher = patch("app.core.security.AUTH_REQUIRED", True)
        self.auth_required_patcher.start()

        self.client = TestClient(app)

    def tearDown(self):
        self.api_tokens_patcher.stop()
        self.auth_required_patcher.stop()

    def test_authentication_token_validation(self):
        """Verify endpoints reject requests without valid Bearer credentials."""
        # 1. No authorization header -> 401
        resp = self.client.post("/api/v1/simulation/register", json={
            "user_id": "user-owner",
            "role": "CTO",
            "company_scale": "Enterprise",
            "industry": "Tech",
            "anchor_goal": {
                "title": "Migrate Database",
                "target_timeline_months": 12,
                "budget_limit_usd": 50000.0,
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Balanced"
        })
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["detail"]["error_code"], "AUTHENTICATION_REQUIRED")

        # 2. Invalid bearer token -> 401
        headers = {"Authorization": "Bearer invalid-token"}
        resp = self.client.post("/api/v1/simulation/register", headers=headers, json={
            "user_id": "user-owner",
            "role": "CTO",
            "company_scale": "Enterprise",
            "industry": "Tech",
            "anchor_goal": {
                "title": "Migrate Database",
                "target_timeline_months": 12,
                "budget_limit_usd": 50000.0,
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Balanced"
        })
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["detail"]["error_code"], "INVALID_CREDENTIALS")

        # 3. Valid bearer token -> 200
        headers = {"Authorization": "Bearer token-owner"}
        resp = self.client.post("/api/v1/simulation/register", headers=headers, json={
            "user_id": "user-owner",
            "role": "CTO",
            "company_scale": "Enterprise",
            "industry": "Tech",
            "anchor_goal": {
                "title": "Migrate Database",
                "target_timeline_months": 12,
                "budget_limit_usd": 50000.0,
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Balanced"
        })
        self.assertEqual(resp.status_code, 200)

    def test_simulation_ownership_enforcement(self):
        """Verify simulation actions enforce ownership or specific override roles."""
        # Register a simulation as user-owner
        headers_owner = {"Authorization": "Bearer token-owner"}
        reg_resp = self.client.post("/api/v1/simulation/register", headers=headers_owner, json={
            "user_id": "user-owner",
            "role": "CTO",
            "company_scale": "Enterprise",
            "industry": "Tech",
            "anchor_goal": {
                "title": "Migrate Database",
                "target_timeline_months": 12,
                "budget_limit_usd": 50000.0,
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Balanced"
        })
        self.assertEqual(reg_resp.status_code, 200)
        sim_id = reg_resp.json()["simulation_id"]

        # 1. Other operator attempts access -> 403 Ownership Required
        headers_other = {"Authorization": "Bearer token-other"}
        eval_resp = self.client.post("/api/v1/simulation/evaluate-decision", headers=headers_other, json={
            "simulation_id": sim_id,
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
            "declared_constraints": []
        })
        self.assertEqual(eval_resp.status_code, 403)
        self.assertEqual(eval_resp.json()["detail"]["error_code"], "SIMULATION_OWNERSHIP_REQUIRED")

        # 2. Reviewer role attempts access -> Allowed
        headers_reviewer = {"Authorization": "Bearer token-reviewer"}
        # Patch Gemini model invocation to avoid calling real API
        async def mock_generate(self_inner, llm_request, stream=False):
            from google.adk.models.llm_response import LlmResponse
            from google.genai.types import Content, Part
            text = '{"is_consistent": true, "evidence": "Mock", "confidence": 1.0}'
            if "conflict" in str(llm_request).lower() or "deadlock" in str(llm_request).lower():
                text = '{"has_deadlock": false, "conflicts": []}'
            yield LlmResponse(content=Content(role="model", parts=[Part(text=text)]))

        with patch("google.adk.models.google_llm.Gemini.generate_content_async", new=mock_generate):
            eval_resp = self.client.post("/api/v1/simulation/evaluate-decision", headers=headers_reviewer, json={
                "simulation_id": sim_id,
                "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
                "declared_constraints": []
            })
            self.assertEqual(eval_resp.status_code, 200)

        # 3. Override role attempts access -> Allowed
        headers_override = {"Authorization": "Bearer token-override"}
        with patch("google.adk.models.google_llm.Gemini.generate_content_async", new=mock_generate):
            eval_resp = self.client.post("/api/v1/simulation/evaluate-decision", headers=headers_override, json={
                "simulation_id": sim_id,
                "intent_vector": {"magnitude": 10.0, "heading_degrees": 0.0},
                "declared_constraints": []
            })
            self.assertEqual(eval_resp.status_code, 200)

    def test_cors_preflight_headers(self):
        """Verify preflight requests return required CORS response headers."""
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        }
        resp = self.client.options("/api/v1/simulation/register", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://localhost:3000")
        self.assertIn("POST", resp.headers.get("access-control-allow-methods", ""))

    def test_payload_size_limiter(self):
        """Verify requests exceeding MAX_REQUEST_BYTES are rejected with 413 Payload Too Large."""
        with patch("app.main.MAX_REQUEST_BYTES", 50):
            headers = {"Authorization": "Bearer token-owner"}
            resp = self.client.post("/api/v1/simulation/register", headers=headers, json={
                "user_id": "very-long-user-id-to-exceed-the-limit-of-fifty-bytes-here",
                "role": "CTO",
                "company_scale": "Enterprise",
                "industry": "Tech",
                "anchor_goal": {
                    "title": "Migrate Database",
                    "target_timeline_months": 12,
                    "budget_limit_usd": 50000.0,
                    "reliability_target_sla": 99.9
                },
                "risk_tolerance": "Balanced"
            })
            self.assertEqual(resp.status_code, 413)
            self.assertEqual(resp.json()["detail"]["error_code"], "PAYLOAD_TOO_LARGE")

    def test_rate_limiting_protection(self):
        """Verify clients exceeding RATE_LIMIT_PER_MINUTE are blocked with 429 Rate Limited."""
        from app.main import _request_windows
        _request_windows.clear()

        headers = {"Authorization": "Bearer token-owner"}
        with patch("app.main.RATE_LIMIT_PER_MINUTE", 3):
            # Send 3 requests (allowed)
            for _ in range(3):
                resp = self.client.get("/health")
                self.assertEqual(resp.status_code, 200)

            # 4th request must be rate limited
            resp = self.client.get("/health")
            self.assertEqual(resp.status_code, 429)
            self.assertEqual(resp.json()["detail"]["error_code"], "RATE_LIMITED")
            self.assertEqual(resp.headers.get("Retry-After"), "60")

    def test_request_timeout_protection(self):
        """Verify requests taking longer than REQUEST_TIMEOUT_SECONDS return HTTP 504."""
        # Add a temporary route to test timeout middleware behavior
        @app.get("/test-timeout-route")
        async def slow_route():
            await asyncio.sleep(2)
            return {"status": "slow"}

        with patch("app.main.REQUEST_TIMEOUT_SECONDS", 0.1):
            resp = self.client.get("/test-timeout-route")
            self.assertEqual(resp.status_code, 504)
            self.assertEqual(resp.json()["detail"]["error_code"], "REQUEST_TIMEOUT")

    def test_audit_records_redaction_and_chaining(self):
        """Verify audit logging redacts sensitive info and correctly chains hashes."""
        details = {
            "api_key": "sensitive-gemini-key",
            "secret_token": "token-123",
            "authorization_header": "Bearer token-abc",
            "normal_field": "public-data"
        }
        # Log first event
        audit_event(
            event_type="test_event_1",
            actor_id="user-owner",
            request_id="req-1",
            simulation_id="sim-1",
            details=details
        )

        # Log second event to test hash chaining
        audit_event(
            event_type="test_event_2",
            actor_id="user-owner",
            request_id="req-2",
            simulation_id="sim-1",
            details={"foo": "bar"}
        )

        # Read database directly to inspect audit records
        with sqlite3.connect(workflow_store.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM audit_records ORDER BY sequence").fetchall()

        self.assertTrue(len(rows) >= 2)
        target_rows = rows[-2:]

        # Inspect redaction in first record
        record1_details = json.loads(target_rows[0]["details_json"])
        self.assertEqual(record1_details["api_key"], "[REDACTED]")
        self.assertEqual(record1_details["secret_token"], "[REDACTED]")
        self.assertEqual(record1_details["authorization_header"], "[REDACTED]")
        self.assertEqual(record1_details["normal_field"], "public-data")

        # Inspect hash chaining
        self.assertEqual(target_rows[1]["previous_hash"], target_rows[0]["record_hash"])

    def test_strict_api_validation(self):
        """Verify strict validations check domain boundaries for vectors, storms, and icebergs."""
        headers = {"Authorization": "Bearer token-owner"}

        # 1. Invalid heading degrees (must be 0-360)
        resp = self.client.post("/api/v1/simulation/evaluate-decision", headers=headers, json={
            "simulation_id": "sim-123",
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 380.0},
            "declared_constraints": []
        })
        self.assertEqual(resp.status_code, 422)

        # 2. Invalid magnitude (must be positive)
        resp = self.client.post("/api/v1/simulation/evaluate-decision", headers=headers, json={
            "simulation_id": "sim-123",
            "intent_vector": {"magnitude": -5.0, "heading_degrees": 90.0},
            "declared_constraints": []
        })
        self.assertEqual(resp.status_code, 422)

        # 3. Invalid iceberg radius (must be positive)
        resp = self.client.post("/api/v1/simulation/evaluate-decision", headers=headers, json={
            "simulation_id": "sim-123",
            "intent_vector": {"magnitude": 10.0, "heading_degrees": 90.0},
            "declared_constraints": [],
            "custom_icebergs": [{"name": "Berg", "x": 0.0, "y": 10.0, "radius": -10.0}]
        })
        self.assertEqual(resp.status_code, 422)

        # 4. Unknown storm in WeatherStation (raise UnknownStormError)
        # Create a simulation session first so we can evaluate on it
        reg_resp = self.client.post("/api/v1/simulation/register", headers=headers, json={
            "user_id": "user-owner",
            "role": "CTO",
            "company_scale": "Enterprise",
            "industry": "Tech",
            "anchor_goal": {
                "title": "Migrate Database",
                "target_timeline_months": 12,
                "budget_limit_usd": 50000.0,
                "reliability_target_sla": 99.9
            },
            "risk_tolerance": "Balanced"
        })
        sim_id = reg_resp.json()["simulation_id"]

        async def mock_generate(self_inner, llm_request, stream=False):
            from google.adk.models.llm_response import LlmResponse
            from google.genai.types import Content, Part
            text = '{"is_consistent": true, "evidence": "Mock", "confidence": 1.0}'
            if "conflict" in str(llm_request).lower() or "deadlock" in str(llm_request).lower():
                text = '{"has_deadlock": false, "conflicts": []}'
            yield LlmResponse(content=Content(role="model", parts=[Part(text=text)]))

        with patch("google.adk.models.google_llm.Gemini.generate_content_async", new=mock_generate):
            # Pass active storm that doesn't exist
            resp = self.client.post("/api/v1/simulation/evaluate-decision", headers=headers, json={
                "simulation_id": sim_id,
                "intent_vector": {"magnitude": 10.0, "heading_degrees": 90.0},
                "declared_constraints": [],
                "active_storms": ["Unknown Mystery Storm"]
            })
            # It should trigger UnknownStormError which maps to HTTP 422 Unprocessable Entity
            self.assertEqual(resp.status_code, 422)
            self.assertEqual(resp.json()["detail"]["error_code"], "UNKNOWN_STORM")
