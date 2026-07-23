"""Version-controlled drift benchmark and false-positive/negative reporting."""
import json
from pathlib import Path
import unittest

from app.core.drift_extraction import extract_structured_changes
from app.core.drift_rules import evaluate_deterministic_rules
from app.core.goal_contract import GoalContract, OutcomeCategorization


class TestDriftBenchmark(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((Path(__file__).parent / "fixtures" / "drift_benchmark.json").read_text())
        cls.contract = GoalContract(
            contract_id="benchmark", contract_version=1, original_request_text="Migrate core platform",
            normalized_objective="Migrate core platform", deliverables=["platform migration"],
            in_scope_items=["platform migration"], outcomes=OutcomeCategorization(required_outcomes=["migration"]),
            budget_limit_usd=100, target_timeline_months=12, reliability_target_sla=99,
            risk_tolerance="Balanced", creator_id="benchmark", acceptance_criteria=["complete migration"],
        )

    def test_labeled_cases_have_expected_evidence_category(self):
        results = []
        for case in self.cases:
            extraction = extract_structured_changes(case["id"], case["request"], self.contract)
            rules = evaluate_deterministic_rules(self.contract, extraction)
            labels = {finding.category for finding in rules}
            predicted = "PROMPT_INJECTION" if extraction.prompt_injection_flag else (
                "AMBIGUOUS" if extraction.ambiguity_flags else (
                    "OBJECTIVE_REPLACEMENT" if "OBJECTIVE_REPLACEMENT" in labels else
                    "CONSTRAINT_CONFLICT" if labels.intersection({"CONSTRAINT_CONFLICT", "DIRECT_CONSTRAINT_CONTRADICTION"}) else
                    "SCOPE_EXTENSION" if (extraction.scope_additions or extraction.deliverable_additions) else "NO_DRIFT"))
            results.append(predicted == case["expected"])
        self.assertGreaterEqual(sum(results) / len(results), 0.75, "benchmark pass-rate below release threshold")
