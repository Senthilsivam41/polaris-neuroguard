"""Goal-Amendment Confirmation Workflow Module (DRIFT-010).

Manages the explicit state machine lifecycle for goal amendments (evaluating, confirming, rejecting).
Guarantees that an active Goal Contract is never silently mutated: version N+1 is created ONLY upon explicit approval of a valid, non-stale change request.
"""

import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.core.goal_contract_service import (
    goal_contract_repo,
    ContractAmendmentMetadata,
    ContractNotFoundError,
    StaleVersionError,
)
from app.core.drift_models import (
    ExtractedChangeRequest,
    RuleFinding,
    SemanticScorerResult,
    DriftClassification,
    DriftSeverity,
    DriftDecisionAction,
    AmendmentStatus,
)
from app.core.drift_extraction import extract_structured_changes
from app.core.drift_engine import evaluate_request_drift
from app.core.semantic_drift import SemanticScorerInterface


class AmendmentWorkflowError(ValueError):
    """Base exception for Goal Amendment Workflow operations."""
    pass


class AmendmentNotFoundError(AmendmentWorkflowError):
    """Raised when evaluation history for a request ID is missing."""
    pass


class UnauthorizedActorError(AmendmentWorkflowError):
    """Raised when actor ID does not match simulation ownership."""
    pass


class InvalidWorkflowStateError(AmendmentWorkflowError):
    """Raised when attempting an operation invalid for the current status."""
    pass


class GoalAmendmentWorkflowService:
    """
    Service managing evaluation, lifecycle status tracking, confirmation, and rejection of goal change requests.
    """
    def __init__(self):
        # Evaluation records: request_id -> dict
        self._evaluations: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def clear(self) -> None:
        """Clear all in-memory evaluation records (for test isolation)."""
        with self._lock:
            self._evaluations.clear()

    def evaluate_change_request(
        self,
        sim_session: Dict[str, Any],
        request_record: Dict[str, Any],
        semantic_scorer: Optional[SemanticScorerInterface] = None
    ) -> Dict[str, Any]:
        """
        Executes drift evaluation for a change request against the current active contract.
        Saves evaluation evidence and initial amendment status without mutating the goal contract.
        """
        request_id = request_record["request_id"]
        raw_text = request_record["raw_text"]
        expected_version = request_record["expected_version"]
        contract_id = sim_session.get("active_contract_id")
        risk_profile = sim_session.get("profile", {}).get("risk_tolerance", "Balanced")

        active_contract = goal_contract_repo.get_latest_contract(contract_id)

        # Stale expected version check
        if expected_version != active_contract.contract_version:
            raise StaleVersionError(
                f"Expected contract version {expected_version} is stale. Active version is {active_contract.contract_version}.",
                current_version=active_contract.contract_version,
                expected_version=expected_version,
                contract_id=contract_id
            )

        # Extract structured deltas
        extracted = extract_structured_changes(request_id, raw_text, active_contract)
        
        # Evaluate drift engine
        classification, severity, action, rules, semantic_res, policy, explanation = evaluate_request_drift(
            contract=active_contract,
            extracted=extracted,
            risk_profile=risk_profile,
            semantic_scorer=semantic_scorer
        )

        # Initial status determination
        if action == DriftDecisionAction.ALLOW:
            status = AmendmentStatus.NO_AMENDMENT_NEEDED
        elif action == DriftDecisionAction.NEEDS_CLARIFICATION:
            status = AmendmentStatus.NEEDS_CLARIFICATION
        elif action == DriftDecisionAction.REJECT:
            status = AmendmentStatus.REJECTED
        elif action == DriftDecisionAction.REQUIRE_HITL_REVIEW:
            status = AmendmentStatus.PENDING_HITL_REVIEW
        else:
            status = AmendmentStatus.PENDING_CONFIRMATION

        evaluation_data = {
            "request_id": request_id,
            "contract_id": contract_id,
            "active_contract_version": active_contract.contract_version,
            "baseline_contract_version": 1,
            "extracted_changes": extracted.model_dump(),
            "classification": classification.value,
            "severity": severity.value,
            "recommended_action": action.value,
            "amendment_status": status.value,
            "deterministic_rule_findings": [r.model_dump() for r in rules],
            "semantic_score_result": semantic_res.model_dump(),
            "policy_profile_used": policy.profile_name,
            "human_explanation": explanation,
            "trace_id": request_record["response"].get("trace_id", ""),
            "contract_unchanged": True,
            "evaluated_at": datetime.now(timezone.utc).isoformat()
        }

        with self._lock:
            self._evaluations[request_id] = evaluation_data

        return evaluation_data.copy()

    def get_evaluation(self, request_id: str) -> Dict[str, Any]:
        """Retrieves prior drift evaluation record for a request ID."""
        with self._lock:
            if request_id not in self._evaluations:
                raise AmendmentNotFoundError(f"Evaluation for request ID '{request_id}' not found.")
            return self._evaluations[request_id].copy()

    def confirm_change_request(
        self,
        sim_session: Dict[str, Any],
        request_id: str,
        actor_id: str,
        decision: str = "APPROVE",
        rationale: str = ""
    ) -> Dict[str, Any]:
        """
        Processes explicit user or reviewer confirmation/rejection of a change request amendment.
        On APPROVE: calls goal_contract_repo.create_amendment_version() to instantiate GoalContract v(N+1).
        On REJECT: marks amendment status REJECTED without mutating contract.
        Handles idempotent repeat executions safely.
        """
        with self._lock:
            if request_id not in self._evaluations:
                raise AmendmentNotFoundError(f"Evaluation for request ID '{request_id}' not found.")
            eval_record = self._evaluations[request_id]

        current_status = eval_record["amendment_status"]
        
        # Idempotency check: repeat calls return cached result
        if current_status in [AmendmentStatus.APPROVED.value, AmendmentStatus.REJECTED.value]:
            return {
                "request_id": request_id,
                "contract_id": eval_record["contract_id"],
                "active_contract_version": eval_record["active_contract_version"],
                "amendment_status": current_status,
                "idempotent_replay": True,
                "message": f"Amendment request '{request_id}' was already processed with status {current_status}."
            }

        # Ownership check
        owner_id = sim_session.get("profile", {}).get("user_id", "")
        if actor_id and owner_id and actor_id != owner_id:
            raise UnauthorizedActorError(f"Actor '{actor_id}' is unauthorized to confirm simulation belonging to '{owner_id}'.")

        # Status check
        if current_status == AmendmentStatus.NEEDS_CLARIFICATION.value:
            raise InvalidWorkflowStateError("Cannot confirm request needing clarification. Please submit clarified request.")

        contract_id = eval_record["contract_id"]
        eval_version = eval_record["active_contract_version"]

        # Verify active contract version hasn't changed since evaluation
        latest_contract = goal_contract_repo.get_latest_contract(contract_id)
        if latest_contract.contract_version != eval_version:
            raise StaleVersionError(
                f"Contract version has progressed to {latest_contract.contract_version} since evaluation at version {eval_version}.",
                current_version=latest_contract.contract_version,
                expected_version=eval_version,
                contract_id=contract_id
            )

        if decision.upper() == "REJECT":
            with self._lock:
                eval_record["amendment_status"] = AmendmentStatus.REJECTED.value
                eval_record["decision_actor"] = actor_id
                eval_record["decision_rationale"] = rationale
                eval_record["processed_at"] = datetime.now(timezone.utc).isoformat()
            
            return {
                "request_id": request_id,
                "contract_id": contract_id,
                "active_contract_version": latest_contract.contract_version,
                "amendment_status": AmendmentStatus.REJECTED.value,
                "idempotent_replay": False,
                "message": "Amendment request rejected by user/reviewer. Active contract remains unchanged."
            }

        # APPROVE branch -> Instantiate new contract version N+1
        extracted_dict = eval_record["extracted_changes"]
        new_version_num = latest_contract.contract_version + 1

        # Build fields to update for version N+1
        new_fields: Dict[str, Any] = {}
        if extracted_dict.get("budget_limit_usd") is not None:
            new_fields["budget_limit_usd"] = extracted_dict["budget_limit_usd"]
        if extracted_dict.get("target_timeline_months") is not None:
            new_fields["target_timeline_months"] = extracted_dict["target_timeline_months"]
        if extracted_dict.get("reliability_target_sla") is not None:
            new_fields["reliability_target_sla"] = extracted_dict["reliability_target_sla"]
        if extracted_dict.get("scope_additions"):
            new_fields["in_scope_items"] = list(set(latest_contract.in_scope_items + extracted_dict["scope_additions"]))
            new_fields["deliverables"] = list(set(latest_contract.deliverables + extracted_dict["scope_additions"]))
        if extracted_dict.get("constraint_additions"):
            new_fields["constraints"] = list(set(latest_contract.constraints + extracted_dict["constraint_additions"]))

        amendment_metadata = ContractAmendmentMetadata(
            amendment_id=f"amendment-{request_id}",
            actor_id=actor_id,
            reason=rationale or extracted_dict.get("raw_request_text", "Approved user change request"),
            source_request_id=request_id,
            previous_version=latest_contract.contract_version,
            new_version=new_version_num
        )

        new_contract = goal_contract_repo.create_amendment_version(
            contract_id=contract_id,
            amendment_metadata=amendment_metadata,
            new_contract_fields=new_fields
        )

        # Update simulation session active contract details
        sim_session["active_contract_version"] = new_contract.contract_version
        sim_session["active_contract_fingerprint"] = new_contract.content_fingerprint

        with self._lock:
            eval_record["amendment_status"] = AmendmentStatus.APPROVED.value
            eval_record["active_contract_version"] = new_contract.contract_version
            eval_record["decision_actor"] = actor_id
            eval_record["decision_rationale"] = rationale
            eval_record["processed_at"] = datetime.now(timezone.utc).isoformat()
            eval_record["contract_unchanged"] = False

        return {
            "request_id": request_id,
            "contract_id": contract_id,
            "active_contract_version": new_contract.contract_version,
            "amendment_status": AmendmentStatus.APPROVED.value,
            "idempotent_replay": False,
            "new_contract_fingerprint": new_contract.content_fingerprint,
            "message": f"Amendment approved. Instantiated Goal Contract version {new_contract.contract_version}."
        }


# Global singleton instance
amendment_workflow_service = GoalAmendmentWorkflowService()
