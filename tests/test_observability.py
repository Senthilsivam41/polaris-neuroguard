import os
# Configure environment variables before importing app modules
os.environ["OFFLINE_MODE"] = "true"
os.environ["POLARIS_API_TOKENS"] = '{"token-owner":{"actor_id":"user-owner","roles":["operator"]}}'

import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.observability import AlertEvaluator, MetricsRegistry, metrics, alerts


class TestObservability(unittest.TestCase):
    def setUp(self):
        # Reset global metrics for clean test state
        metrics.counters.clear()
        metrics.latencies.clear()
        
        self.tokens_patch = {
            "token-owner": {"actor_id": "user-owner", "roles": ["operator"]},
        }
        self.api_tokens_patcher = patch("app.core.security.API_TOKENS", self.tokens_patch)
        self.api_tokens_patcher.start()
        
        self.client = TestClient(app)

    def tearDown(self):
        self.api_tokens_patcher.stop()

    def test_prometheus_export_contains_percentiles_and_environment(self):
        registry = MetricsRegistry()
        for value in (0.1, 0.2, 0.3):
            registry.observe("workflow", value, {"environment": "test", "status": "RUNNING"})
        output = registry.prometheus()
        self.assertIn('quantile="p50"', output)
        self.assertIn('environment="test"', output)
        self.assertNotIn("\\\\", output)

    def test_alert_thresholds_have_owners(self):
        registry = MetricsRegistry()
        registry.increment("workflow_failures_total")
        registry.increment("hitl_interruptions_total", value=5)
        active = AlertEvaluator(registry).evaluate()
        self.assertTrue(active)
        self.assertTrue(all(alert.owner for alert in active))

    def test_a2a_and_cost_alerts_are_evaluated(self):
        registry = MetricsRegistry()
        registry.increment("a2a_failures_total")
        registry.increment("model_cost_usd_total", value=100)
        names = {alert.name for alert in AlertEvaluator(registry).evaluate()}
        self.assertEqual({"a2a_outage", "model_cost"}, names)

    def test_trace_id_propagation_middleware(self):
        """Verify X-Trace-Id propagation and generation on requests."""
        # 1. Provide an incoming trace ID -> should be propagated back in the header
        custom_trace_id = "test-trace-id-1234"
        resp = self.client.get("/health", headers={"X-Trace-Id": custom_trace_id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-Trace-Id"), custom_trace_id)

        # 2. Missing trace ID -> a new UUID is generated and returned
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        generated_trace_id = resp.headers.get("X-Trace-Id")
        self.assertIsNotNone(generated_trace_id)
        self.assertEqual(len(generated_trace_id), 36) # UUID string length

    def test_prometheus_metrics_endpoint(self):
        """Verify the /metrics endpoint returns prometheus format."""
        # Record some dummy metrics to registry
        metrics.increment("dummy_counter", {"environment": "development"})
        metrics.observe("dummy_latency", 0.5, {"environment": "development"})

        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/plain", resp.headers.get("content-type", ""))
        body = resp.text
        self.assertIn("polaris_dummy_counter{environment=\"development\"} 1", body)
        self.assertIn("polaris_dummy_latency_seconds_count{environment=\"development\"} 1", body)

    def test_operations_alerts_auth_and_thresholds(self):
        """Verify /api/v1/operations/alerts endpoint authentication and evaluation."""
        with patch("app.core.security.AUTH_REQUIRED", True):
            # 1. Access without token should be rejected (401)
            resp = self.client.get("/api/v1/operations/alerts")
            self.assertEqual(resp.status_code, 401)

            # 2. Access with valid token should return 200
            headers = {"Authorization": "Bearer token-owner"}
            resp = self.client.get("/api/v1/operations/alerts", headers=headers)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json(), {"alerts": []})

            # 3. Simulate hitting alert thresholds
            metrics.increment("workflow_failures_total")
            metrics.increment("session_version_conflicts_total", value=5)
            
            # Access again to get triggered alerts
            resp = self.client.get("/api/v1/operations/alerts", headers=headers)
            self.assertEqual(resp.status_code, 200)
            alerts_data = resp.json()["alerts"]
            self.assertEqual(len(alerts_data), 2)
            alert_names = {a["name"] for a in alerts_data}
            self.assertEqual(alert_names, {"workflow_failure", "version_conflicts"})
            # Confirm that alert owner is present
            for alert in alerts_data:
                self.assertEqual(alert["owner"], "platform-oncall")

    def test_high_latency_alert(self):
        """Verify that high latency triggers high_latency alert."""
        # Record a latency value > 2 seconds for workflow
        metrics.observe("workflow", 2.5, {"environment": "development"})
        
        headers = {"Authorization": "Bearer token-owner"}
        with patch("app.core.security.AUTH_REQUIRED", True):
            resp = self.client.get("/api/v1/operations/alerts", headers=headers)
            self.assertEqual(resp.status_code, 200)
            alerts_data = resp.json()["alerts"]
            alert_names = {a["name"] for a in alerts_data}
            self.assertIn("high_latency", alert_names)
            
            # Confirm description details
            high_lat_alert = [a for a in alerts_data if a["name"] == "high_latency"][0]
            self.assertEqual(high_lat_alert["severity"], "warning")
            self.assertEqual(high_lat_alert["owner"], "platform-oncall")
            self.assertIn("exceeds 2 seconds", high_lat_alert["message"])
