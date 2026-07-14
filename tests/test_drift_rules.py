import unittest
from app.core.goal_contract import GoalContract, OutcomeCategorization
from app.core.drift_models import ExtractedChangeRequest, DriftSeverity
from app.core.drift_rules import evaluate_deterministic_rules


class TestDriftRules(unittest.TestCase):
    def setUp(self):
        self.contract = GoalContract(
            contract_id="contract-rules-test",
            contract_version=1,
            original_request_text="Build core payment system.",
            normalized_objective="Build payment gateway",
            constraints=["RIGID_TIMELINE", "REDUCE_COST"],
            explicit_exclusions=["Cryptocurrency Payments"],
            outcomes=OutcomeCategorization(
                required_outcomes=["PCI-DSS compliance"],
                excluded_outcomes=["Cryptocurrency Payments"]
            ),
            budget_limit_usd=500000.0,
            target_timeline_months=6,
            reliability_target_sla=99.9
        )

    def test_direct_constraint_contradiction(self):
        """Verify opposing constraint pair (e.g. RIGID_TIMELINE + EXTEND_SCHEDULE) triggers constraint conflict rule."""
        extracted = ExtractedChangeRequest(
            request_id="r1", contract_id=self.contract.contract_id, contract_version=1,
            raw_request_text="Request schedule extension",
            constraint_additions=["EXTEND_SCHEDULE"]
        )
        findings = evaluate_deterministic_rules(self.contract, extracted)
        categories = [f.category for f in findings]
        self.assertIn("DIRECT_CONSTRAINT_CONTRADICTION", categories)

    def test_excluded_outcome_conflict(self):
        """Verify adding scope explicitly listed in excluded outcomes triggers EXCLUDED_OUTCOME_CONFLICT."""
        extracted = ExtractedChangeRequest(
            request_id="r2", contract_id=self.contract.contract_id, contract_version=1,
            raw_request_text="Add support for Cryptocurrency Payments",
            scope_additions=["Cryptocurrency Payments Integration"]
        )
        findings = evaluate_deterministic_rules(self.contract, extracted)
        categories = [f.category for f in findings]
        self.assertIn("EXCLUDED_OUTCOME_CONFLICT", categories)

    def test_objective_replacement_rule(self):
        """Verify request changing baseline objective triggers OBJECTIVE_REPLACEMENT rule."""
        extracted = ExtractedChangeRequest(
            request_id="r3", contract_id=self.contract.contract_id, contract_version=1,
            raw_request_text="Pivot project to social media app",
            objective_changes="Build Social Media Sharing App"
        )
        findings = evaluate_deterministic_rules(self.contract, extracted)
        categories = [f.category for f in findings]
        self.assertIn("OBJECTIVE_REPLACEMENT", categories)

    def test_budget_and_timeline_rules(self):
        """Verify budget and timeline changes generate clear deterministic rule findings with evidence."""
        extracted = ExtractedChangeRequest(
            request_id="r4", contract_id=self.contract.contract_id, contract_version=1,
            raw_request_text="Increase budget and time",
            budget_limit_usd=750000.0,
            target_timeline_months=12
        )
        findings = evaluate_deterministic_rules(self.contract, extracted)
        categories = [f.category for f in findings]
        self.assertIn("BUDGET_CHANGE", categories)
        self.assertTrue(any("750,000.00" in f.evidence for f in findings))

    def test_no_change_clarification_rule(self):
        """Verify zero change request triggers COMPATIBLE_CLARIFICATION with severity NONE."""
        extracted = ExtractedChangeRequest(
            request_id="r5", contract_id=self.contract.contract_id, contract_version=1,
            raw_request_text="No change",
            is_no_change_detected=True
        )
        findings = evaluate_deterministic_rules(self.contract, extracted)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "COMPATIBLE_CLARIFICATION")
        self.assertEqual(findings[0].severity_contribution, DriftSeverity.NONE)


if __name__ == "__main__":
    unittest.main()
