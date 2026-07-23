import os
# Configure environment variables before importing app modules
os.environ["OFFLINE_MODE"] = "true"
os.environ["POLARIS_API_TOKENS"] = '{"token-owner":{"actor_id":"user-owner","roles":["operator"]}}'

import unittest
import json
import time
import sqlite3
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from app.core.drift_extraction import extract_structured_changes
from app.core.drift_rules import evaluate_deterministic_rules
from app.core.goal_contract import GoalContract, OutcomeCategorization
from app.core.persistence import workflow_store, SQLiteWorkflowStore
from app.core.security import audit_event, redact


class TestPhase8Validation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load benchmark cases
        cls.cases = json.loads((Path(__file__).parent / "fixtures" / "drift_benchmark.json").read_text())
        cls.contract = GoalContract(
            contract_id="benchmark",
            contract_version=1,
            original_request_text="Migrate core platform",
            normalized_objective="Migrate core platform",
            deliverables=["platform migration"],
            in_scope_items=["platform migration"],
            outcomes=OutcomeCategorization(required_outcomes=["migration"]),
            budget_limit_usd=100,
            target_timeline_months=12,
            reliability_target_sla=99,
            risk_tolerance="Balanced",
            creator_id="benchmark",
            acceptance_criteria=["complete migration"],
        )

    def test_calculate_benchmark_metrics_and_log_report(self):
        """Run Phase 8 drift benchmark, calculate precision/recall/error metrics, and output report."""
        passed = 0
        total = len(self.cases)
        results = []

        print("\n" + "="*80)
        print(" PHASE 8 DRIFT BENCHMARK REPORT")
        print("="*80)
        print(f"{'CASE ID':<15} | {'EXPECTED':<22} | {'PREDICTED':<22} | {'STATUS':<6}")
        print("-"*80)

        for case in self.cases:
            extraction = extract_structured_changes(case["id"], case["request"], self.contract)
            rules = evaluate_deterministic_rules(self.contract, extraction)
            labels = {finding.category for finding in rules}
            
            predicted = "PROMPT_INJECTION" if extraction.prompt_injection_flag else (
                "AMBIGUOUS" if extraction.ambiguity_flags else (
                    "OBJECTIVE_REPLACEMENT" if "OBJECTIVE_REPLACEMENT" in labels else
                    "CONSTRAINT_CONFLICT" if labels.intersection({"CONSTRAINT_CONFLICT", "DIRECT_CONSTRAINT_CONTRADICTION"}) else
                    "SCOPE_EXTENSION" if (extraction.scope_additions or extraction.deliverable_additions) else "NO_DRIFT"
                )
            )

            status = "PASS" if predicted == case["expected"] else "FAIL"
            if status == "PASS":
                passed += 1
            
            print(f"{case['id']:<15} | {case['expected']:<22} | {predicted:<22} | {status:<6}")
            results.append({
                "id": case["id"],
                "expected": case["expected"],
                "predicted": predicted,
                "status": status
            })

        accuracy = passed / total
        print("-"*80)
        print(f"Total Cases: {total} | Passed: {passed} | Accuracy: {accuracy:.2%}")
        print("="*80 + "\n")

        # Pass gate of 75% accuracy
        self.assertGreaterEqual(accuracy, 0.75, "Benchmark accuracy did not meet 75% release threshold.")

    def test_concurrent_slo_under_high_load(self):
        """Verify deterministic calculations remain under 200ms SLO under parallel load."""
        from app.core.simulation import Vector2D, calculate_resultant_vector
        
        intent = Vector2D(10, 45)
        
        # Measure latency under concurrent load of 10 workers running 100 total iterations
        start_time = time.perf_counter()
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(calculate_resultant_vector, intent, []) for _ in range(100)]
            results = [f.result() for f in futures]
        elapsed = time.perf_counter() - start_time
        
        avg_latency = elapsed / 100
        print(f"\n[SLO CHECK] Average latency per vector addition under load: {avg_latency*1000:.3f} ms")
        
        self.assertLess(avg_latency, 0.2, "Concurrent turn latency exceeds the 200ms SLO threshold.")

    def test_cryptographic_audit_ledger_integrity(self):
        """Verify that the hash chain in the SQLite audit log is cryptographically intact."""
        # Clean state, then write a few records
        db_path = os.path.join(os.path.dirname(workflow_store.path), "test_audit_integrity.sqlite")
        if os.path.exists(db_path):
            os.unlink(db_path)
            
        test_store = SQLiteWorkflowStore(db_path)
        
        # Append some records
        for i in range(5):
            test_store.append_audit_record(
                event_type=f"test_evt_{i}",
                actor_id="test_actor",
                request_id=f"req_{i}",
                simulation_id="sim_abc",
                details=redact({"step": i, "token": f"secret_{i}"})  # token key should be redacted!
            )
            
        # Verify hashes
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM audit_records ORDER BY sequence").fetchall()
            
        self.assertEqual(len(rows), 5)
        
        # Verify hash chaining and redactions
        for idx, row in enumerate(rows):
            details = json.loads(row["details_json"])
            # Redaction check
            self.assertEqual(details["token"], "[REDACTED]")
            
            # Hash chaining check
            if idx == 0:
                self.assertIsNone(row["previous_hash"])
            else:
                self.assertEqual(row["previous_hash"], rows[idx - 1]["record_hash"])
                
            # Verify record_hash calculation matches logic in code
            material = "|".join([
                row["recorded_at"],
                row["event_type"],
                row["actor_id"],
                row["request_id"] or "",
                row["simulation_id"] or "",
                row["details_json"],
                row["previous_hash"] or ""
            ])
            expected_hash = hashlib.sha256(material.encode()).hexdigest()
            self.assertEqual(row["record_hash"], expected_hash)
            
        # Clean up database file
        os.unlink(db_path)
