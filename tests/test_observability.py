import unittest

from app.core.observability import AlertEvaluator, MetricsRegistry


class TestObservability(unittest.TestCase):
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
