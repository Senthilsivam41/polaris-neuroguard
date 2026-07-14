import unittest
from datetime import datetime, timezone
from app.core.goal_contract import GoalContract, OutcomeCategorization
from app.core.goal_contract_service import (
    GoalContractRepository,
    ContractAmendmentMetadata,
    ContractNotFoundError,
    ContractVersionNotFoundError,
    StaleVersionError,
    VersionConflictError,
)


class TestGoalContractVersioning(unittest.TestCase):
    def setUp(self):
        self.repo = GoalContractRepository()

    def _create_sample_baseline(self, contract_id: str = "contract-v1-test") -> GoalContract:
        return GoalContract(
            contract_id=contract_id,
            contract_version=1,
            original_request_text="Initial project requirements for launch.",
            normalized_objective="Launch MVP Platform v1.0",
            deliverables=["Auth service", "Database schema"],
            budget_limit_usd=100000.0,
            target_timeline_months=3,
            creator_id="cto-user"
        )

    def test_initial_baseline_contract_creation(self):
        """Verify creation of initial baseline contract at version 1."""
        baseline = self._create_sample_baseline()
        saved = self.repo.create_baseline_contract(baseline)
        
        self.assertEqual(saved.contract_id, "contract-v1-test")
        self.assertEqual(saved.contract_version, 1)
        self.assertIsNone(saved.parent_contract_version)
        self.assertIsNone(saved.parent_version_id)
        
        fetched = self.repo.get_latest_contract("contract-v1-test")
        self.assertEqual(fetched.content_fingerprint, saved.content_fingerprint)

    def test_baseline_cannot_be_overwritten(self):
        """Verify attempting to overwrite an existing baseline contract raises VersionConflictError."""
        baseline = self._create_sample_baseline("contract-duplicate-test")
        self.repo.create_baseline_contract(baseline)
        
        # Duplicate attempt
        with self.assertRaises(VersionConflictError):
            self.repo.create_baseline_contract(baseline)

    def test_approved_amendment_creates_version_2(self):
        """Verify approved amendment creates version 2 linked to parent version 1 metadata."""
        baseline = self._create_sample_baseline("contract-amend-test")
        v1 = self.repo.create_baseline_contract(baseline)

        amendment_meta = ContractAmendmentMetadata(
            amendment_id="amend-101",
            actor_id="cto-user",
            reason="Expand budget to support multi-region deployment.",
            source_request_id="req-change-001",
            previous_version=1,
            new_version=2
        )

        v2 = self.repo.create_amendment_version(
            contract_id="contract-amend-test",
            amendment_metadata=amendment_meta,
            new_contract_fields={"budget_limit_usd": 200000.0}
        )

        self.assertEqual(v2.contract_version, 2)
        self.assertEqual(v2.parent_contract_version, 1)
        self.assertEqual(v2.parent_version_id, "contract-amend-test")
        self.assertEqual(v2.budget_limit_usd, 200000.0)

        # Confirm original v1 contract remains unchanged (immutability)
        fetched_v1 = self.repo.get_contract_version("contract-amend-test", 1)
        self.assertEqual(fetched_v1.budget_limit_usd, 100000.0)

        # Confirm latest version is v2
        latest = self.repo.get_latest_contract("contract-amend-test")
        self.assertEqual(latest.contract_version, 2)

    def test_version_history_returns_in_order(self):
        """Verify list_version_history returns all versions sequentially sorted."""
        contract_id = "contract-history-test"
        v1 = self.repo.create_baseline_contract(self._create_sample_baseline(contract_id))

        amendment_1 = ContractAmendmentMetadata(
            amendment_id="amend-1",
            actor_id="cto",
            reason="Reason 1",
            source_request_id="req-1",
            previous_version=1,
            new_version=2
        )
        self.repo.create_amendment_version(contract_id, amendment_1, {"target_timeline_months": 4})

        amendment_2 = ContractAmendmentMetadata(
            amendment_id="amend-2",
            actor_id="cto",
            reason="Reason 2",
            source_request_id="req-2",
            previous_version=2,
            new_version=3
        )
        self.repo.create_amendment_version(contract_id, amendment_2, {"target_timeline_months": 5})

        history = self.repo.list_version_history(contract_id)
        self.assertEqual(len(history), 3)
        self.assertEqual([c.contract_version for c in history], [1, 2, 3])
        self.assertEqual(history[0].target_timeline_months, 3)
        self.assertEqual(history[1].target_timeline_months, 4)
        self.assertEqual(history[2].target_timeline_months, 5)

    def test_stale_expected_parent_version_rejected(self):
        """Verify amendment against a stale expected parent version raises StaleVersionError."""
        contract_id = "contract-stale-test"
        self.repo.create_baseline_contract(self._create_sample_baseline(contract_id))

        # Advance to v2
        self.repo.create_amendment_version(
            contract_id,
            ContractAmendmentMetadata(
                amendment_id="a1", actor_id="cto", reason="r1", source_request_id="q1",
                previous_version=1, new_version=2
            ),
            {"budget_limit_usd": 150000.0}
        )

        # Attempt amendment targeting stale v1 when latest is v2
        stale_amendment = ContractAmendmentMetadata(
            amendment_id="a2-stale", actor_id="cto", reason="r2", source_request_id="q2",
            previous_version=1,  # STALE (current is 2)
            new_version=2
        )
        with self.assertRaises(StaleVersionError) as cm:
            self.repo.create_amendment_version(contract_id, stale_amendment, {"budget_limit_usd": 180000.0})

        self.assertEqual(cm.exception.current_version, 2)
        self.assertEqual(cm.exception.expected_version, 1)

    def test_non_sequential_new_version_rejected(self):
        """Verify creating a version with gap (e.g. 1 -> 3) raises VersionConflictError."""
        contract_id = "contract-gap-test"
        self.repo.create_baseline_contract(self._create_sample_baseline(contract_id))

        gap_amendment = ContractAmendmentMetadata(
            amendment_id="a1", actor_id="cto", reason="r1", source_request_id="q1",
            previous_version=1,
            new_version=3  # GAP (expected 2)
        )
        with self.assertRaises(VersionConflictError):
            self.repo.create_amendment_version(contract_id, gap_amendment, {})

    def test_missing_contract_or_version_raises_not_found(self):
        """Verify structured errors when querying non-existent contracts or versions."""
        with self.assertRaises(ContractNotFoundError):
            self.repo.get_latest_contract("non-existent-contract")

        with self.assertRaises(ContractNotFoundError):
            self.repo.get_contract_version("non-existent-contract", 1)

        self.repo.create_baseline_contract(self._create_sample_baseline("exists-contract"))
        with self.assertRaises(ContractVersionNotFoundError):
            self.repo.get_contract_version("exists-contract", 99)


if __name__ == "__main__":
    unittest.main()
