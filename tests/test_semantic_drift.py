import unittest
from app.core.goal_contract import GoalContract
from app.core.drift_models import ExtractedChangeRequest
from app.core.semantic_drift import FakeSemanticScorer, GeminiSemanticScorer


class TestSemanticDriftScoring(unittest.TestCase):
    def setUp(self):
        self.contract = GoalContract(
            contract_id="contract-semantic-test",
            contract_version=1,
            original_request_text="Build secure banking app.",
            normalized_objective="Develop iOS and Android banking application."
        )

    def test_fake_semantic_scorer_bounded_output(self):
        """Verify FakeSemanticScorer returns normalized score and confidence between 0.0 and 1.0."""
        scorer = FakeSemanticScorer(default_score=0.35, default_confidence=0.9)
        extracted = ExtractedChangeRequest(
            request_id="s1", contract_id=self.contract.contract_id, contract_version=1,
            raw_request_text="Add dark mode toggle to UI."
        )
        res = scorer.compute_semantic_drift(self.contract, extracted)
        
        self.assertEqual(res.drift_score, 0.35)
        self.assertEqual(res.confidence, 0.9)
        self.assertFalse(res.is_fallback)
        self.assertTrue(len(res.matched_concepts) > 0)

    def test_fake_semantic_scorer_zero_change(self):
        """Verify FakeSemanticScorer returns 0.0 score for zero-change request."""
        scorer = FakeSemanticScorer()
        extracted = ExtractedChangeRequest(
            request_id="s2", contract_id=self.contract.contract_id, contract_version=1,
            raw_request_text="Proceed as planned.",
            is_no_change_detected=True
        )
        res = scorer.compute_semantic_drift(self.contract, extracted)
        self.assertEqual(res.drift_score, 0.0)

    def test_gemini_semantic_scorer_fallback_on_invalid_credentials(self):
        """Verify GeminiSemanticScorer falls back gracefully to conservative review score if service fails."""
        scorer = GeminiSemanticScorer(model_name="invalid-mock-model-name")
        extracted = ExtractedChangeRequest(
            request_id="s3", contract_id=self.contract.contract_id, contract_version=1,
            raw_request_text="Expand scope to include AI chatbot."
        )
        res = scorer.compute_semantic_drift(self.contract, extracted)
        
        self.assertTrue(res.is_fallback)
        self.assertEqual(res.drift_score, 0.6)
        self.assertIn("fallback", res.semantic_evidence.lower())


if __name__ == "__main__":
    unittest.main()
