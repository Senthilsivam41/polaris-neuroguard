import unittest
from datetime import datetime, timezone
from pydantic import ValidationError
from app.core.goal_contract import GoalContract, OutcomeCategorization


class TestGoalContractSchema(unittest.TestCase):
    def test_valid_goal_contract_creation(self):
        """Verify instantiation of a valid GoalContract with all required and optional fields."""
        contract = GoalContract(
            contract_id="contract-101",
            schema_version="1.0.0",
            contract_version=1,
            original_request_text="Migrate core payment database to cloud within 6 months.",
            normalized_objective="Migrate payment infrastructure to AWS Aurora.",
            deliverables=["Database schema migration script", "Staging environment validation report"],
            in_scope_items=["Aurora MySQL migration", "PCI-DSS compliance re-certification"],
            explicit_exclusions=["Legacy data archiving"],
            constraints=["ZERO_DOWNTIME_DEPLOYMENT"],
            outcomes=OutcomeCategorization(
                required_outcomes=["Zero transaction loss during cutover"],
                optional_outcomes=["Performance boost under 50ms latency"],
                excluded_outcomes=["On-premise hardware upgrades"]
            ),
            budget_limit_usd=500000.0,
            target_timeline_months=6,
            reliability_target_sla=99.99,
            risk_tolerance="Balanced",
            assumptions=["AWS infrastructure account provisioned"],
            acceptance_criteria=["SLA >= 99.99%", "Latency <= 50ms"],
            creator_id="user-cto-1"
        )
        self.assertEqual(contract.contract_id, "contract-101")
        self.assertEqual(contract.contract_version, 1)
        self.assertTrue(len(contract.content_fingerprint) > 0)
        self.assertIsNone(contract.parent_contract_version)
        self.assertEqual(contract.creation_timestamp.tzinfo, timezone.utc)

    def test_outcome_categorization_representation(self):
        """Verify required vs optional vs excluded outcomes are distinctly represented."""
        outcomes = OutcomeCategorization(
            required_outcomes=["Req 1", "Req 2"],
            optional_outcomes=["Opt 1"],
            excluded_outcomes=["Ex 1"]
        )
        self.assertEqual(outcomes.required_outcomes, ["Req 1", "Req 2"])
        self.assertEqual(outcomes.optional_outcomes, ["Opt 1"])
        self.assertEqual(outcomes.excluded_outcomes, ["Ex 1"])

    def test_missing_or_empty_original_request_text(self):
        """Verify ValidationError is raised when original_request_text is missing or empty."""
        with self.assertRaises(ValidationError):
            GoalContract(
                contract_id="contract-102",
                original_request_text="",
                normalized_objective="Valid objective"
            )

        with self.assertRaises(ValidationError):
            GoalContract(
                contract_id="contract-103",
                original_request_text="   \n \t  ",
                normalized_objective="Valid objective"
            )

    def test_missing_or_empty_normalized_objective(self):
        """Verify ValidationError is raised when normalized_objective is missing or empty."""
        with self.assertRaises(ValidationError):
            GoalContract(
                contract_id="contract-104",
                original_request_text="Valid request text",
                normalized_objective=""
            )

    def test_deterministic_fingerprint_generation(self):
        """Verify identical domain contract contents compute identical content fingerprints."""
        c1 = GoalContract(
            contract_id="contract-a",
            contract_version=1,
            original_request_text="Build scalable API",
            normalized_objective="Build REST API",
            budget_limit_usd=100000.0,
            target_timeline_months=3,
            creator_id="dev-1"
        )
        c2 = GoalContract(
            contract_id="contract-b",  # Different ID, same domain content
            contract_version=1,
            original_request_text="Build scalable API",
            normalized_objective="Build REST API",
            budget_limit_usd=100000.0,
            target_timeline_months=3,
            creator_id="dev-1"
        )
        self.assertEqual(c1.content_fingerprint, c2.content_fingerprint)

    def test_fingerprint_changes_on_content_mutation(self):
        """Verify content fingerprint changes when contract content differs."""
        c1 = GoalContract(
            contract_id="contract-a",
            contract_version=1,
            original_request_text="Build scalable API",
            normalized_objective="Build REST API",
            budget_limit_usd=100000.0,
            target_timeline_months=3
        )
        c2 = GoalContract(
            contract_id="contract-a",
            contract_version=1,
            original_request_text="Build scalable API",
            normalized_objective="Build GraphQL API",  # Different objective
            budget_limit_usd=100000.0,
            target_timeline_months=3
        )
        self.assertNotEqual(c1.content_fingerprint, c2.content_fingerprint)

    def test_utc_timestamp_enforcement(self):
        """Verify naive timestamps are converted to timezone-aware UTC."""
        naive_dt = datetime(2026, 7, 14, 12, 0, 0)
        contract = GoalContract(
            contract_id="contract-utc",
            original_request_text="Request",
            normalized_objective="Objective",
            creation_timestamp=naive_dt
        )
        self.assertIsNotNone(contract.creation_timestamp.tzinfo)
        self.assertEqual(contract.creation_timestamp.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
