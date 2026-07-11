import unittest
from unittest.mock import patch
import app.core.config as config

class TestConfigBehavior(unittest.TestCase):
    def test_redact_secrets(self):
        """Verify that Gemini API key secret redaction masks values correctly."""
        # 1. Test empty key
        with patch("app.core.config.GEMINI_API_KEY", ""):
            self.assertEqual(config.get_redacted_api_key(), "")

        # 2. Test short key
        with patch("app.core.config.GEMINI_API_KEY", "abc"):
            self.assertEqual(config.get_redacted_api_key(), "********")

        # 3. Test long key
        with patch("app.core.config.GEMINI_API_KEY", "AIzaSyD-123456789-xyz"):
            redacted = config.get_redacted_api_key()
            self.assertTrue(redacted.startswith("AIza"))
            self.assertTrue(redacted.endswith("-xyz"))
            self.assertIn("...", redacted)
            self.assertNotIn("123456789", redacted)

    def test_invalid_config_values(self):
        """Verify that invalid config values raise ValueError on validation."""
        # Negative base burn rate
        with patch("app.core.config.BASE_BURN_RATE", -50.0):
            with self.assertRaises(ValueError):
                config.validate_config()

        # Out of bounds port
        with patch("app.core.config.PORT", 99999):
            with self.assertRaises(ValueError):
                config.validate_config()

        # Negative timeout
        with patch("app.core.config.GEMINI_TIMEOUT", -10.0):
            with self.assertRaises(ValueError):
                config.validate_config()

    def test_missing_credentials_online(self):
        """Verify that missing credentials raise ValueError when online mode is active."""
        with patch("app.core.config.GEMINI_API_KEY", ""), \
             patch("app.core.config.OFFLINE_MODE", False), \
             patch("app.core.config.MOCK_MODE", False):
            with self.assertRaises(ValueError):
                config.validate_config()

    def test_missing_credentials_offline(self):
        """Verify that missing credentials do not raise error when OFFLINE_MODE=True."""
        with patch("app.core.config.GEMINI_API_KEY", ""), \
             patch("app.core.config.OFFLINE_MODE", True):
            # Should not raise any error
            config.validate_config()

    def test_dependency_smoke_imports(self):
        """Verify that ADK packages and dependencies are successfully importable."""
        from google.adk.workflow import Workflow, Edge, START, node
        from google.adk.agents import LlmAgent
        from google.adk.tools import FunctionTool
        from google.adk.sessions import Session, InMemorySessionService
        self.assertIsNotNone(Workflow)
        self.assertIsNotNone(LlmAgent)
        self.assertIsNotNone(FunctionTool)
        self.assertIsNotNone(Session)
