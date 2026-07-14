"""Drift Classification and Decision Engine (DRIFT-007).

Combines structured extraction (DRIFT-004), deterministic rule findings (DRIFT-005), semantic drift scores (DRIFT-006),
and risk policy thresholds (DRIFT-008) to produce evidence-based classification, severity rating, and recommended action.
"""

from typing import List, Optional, Tuple
from app.core.goal_contract import GoalContract
from app.core.drift_models import (
    ExtractedChangeRequest,
    RuleFinding,
    SemanticScorerResult,
    DriftClassification,
    DriftSeverity,
    DriftDecisionAction
)
from app.core.drift_rules import evaluate_deterministic_rules
from app.core.semantic_drift import default_semantic_scorer, SemanticScorerInterface
from app.core.drift_policy import get_drift_policy, DriftPolicyProfile


SEVERITY_ORDER = {
    DriftSeverity.NONE: 0,
    DriftSeverity.LOW: 1,
    DriftSeverity.MEDIUM: 2,
    DriftSeverity.HIGH: 3,
    DriftSeverity.CRITICAL: 4,
}


def evaluate_request_drift(
    contract: GoalContract,
    extracted: ExtractedChangeRequest,
    risk_profile: str = "Balanced",
    semantic_scorer: Optional[SemanticScorerInterface] = None
) -> Tuple[DriftClassification, DriftSeverity, DriftDecisionAction, List[RuleFinding], SemanticScorerResult, DriftPolicyProfile, str]:
    """
    Evaluates complete drift pipeline for an extracted change request against an active Goal Contract.
    
    Returns:
        Tuple of (classification, severity, recommended_action, rule_findings, semantic_result, policy_used, explanation)
    """
    policy = get_drift_policy(risk_profile)
    scorer = semantic_scorer or default_semantic_scorer
    
    # 1. Deterministic Rule Findings
    rule_findings = evaluate_deterministic_rules(contract, extracted)
    
    # 2. Semantic Drift Scoring
    semantic_result = scorer.compute_semantic_drift(contract, extracted)
    
    # 3. Deterministic Precedence Logic
    
    # Priority A: Security / Prompt Injection
    if extracted.prompt_injection_flag:
        return (
            DriftClassification.POLICY_OR_SECURITY_RISK,
            DriftSeverity.CRITICAL,
            DriftDecisionAction.REJECT,
            rule_findings,
            semantic_result,
            policy,
            "Adversarial prompt injection / override attempt detected. Request rejected immediately."
        )

    # Priority B: Direct Constraint Contradictions & Excluded Outcome Violations
    has_constraint_conflict = any(r.category in ["DIRECT_CONSTRAINT_CONTRADICTION", "EXCLUDED_OUTCOME_CONFLICT"] for r in rule_findings)
    if has_constraint_conflict:
        sev = DriftSeverity.CRITICAL if any(r.severity_contribution == DriftSeverity.CRITICAL for r in rule_findings) else DriftSeverity.HIGH
        action = DriftDecisionAction.REJECT if policy.profile_name == "Conservative" else DriftDecisionAction.REQUIRE_HITL_REVIEW
        return (
            DriftClassification.CONSTRAINT_CONFLICT,
            sev,
            action,
            rule_findings,
            semantic_result,
            policy,
            "Direct SMT constraint contradiction or excluded outcome violation detected."
        )

    # Priority C: Objective Replacement
    has_obj_replacement = any(r.category == "OBJECTIVE_REPLACEMENT" for r in rule_findings) or semantic_result.drift_score >= 0.8
    if has_obj_replacement:
        return (
            DriftClassification.GOAL_REPLACEMENT,
            DriftSeverity.HIGH,
            DriftDecisionAction.REQUIRE_CONFIRMATION,
            rule_findings,
            semantic_result,
            policy,
            "Request proposes fundamental replacement or major transformation of baseline objective."
        )

    # Priority D: Ambiguity
    if extracted.ambiguity_flags or any(r.category == "AMBIGUOUS_REQUEST" for r in rule_findings):
        if policy.ambiguity_behavior == "NEEDS_CLARIFICATION":
            return (
                DriftClassification.AMBIGUOUS,
                DriftSeverity.LOW,
                DriftDecisionAction.NEEDS_CLARIFICATION,
                rule_findings,
                semantic_result,
                policy,
                "Request phrasing is vague or ambiguous. Clarification required before evaluation can proceed."
            )

    # Priority E: Scope Expansion / Budget / Timeline / Reliability Deviations
    has_scope_expansion = any(r.category in ["SCOPE_EXPANSION", "BUDGET_CHANGE", "TIMELINE_CHANGE", "RELIABILITY_CHANGE"] for r in rule_findings) or semantic_result.drift_score >= policy.semantic_drift_material_threshold
    if has_scope_expansion:
        # Determine max severity contribution from triggered rules
        max_sev_val = max([SEVERITY_ORDER[r.severity_contribution] for r in rule_findings], default=1)
        sev_keys = list(SEVERITY_ORDER.keys())
        severity = sev_keys[max_sev_val]
        
        # Decide Action based on Policy Thresholds
        if SEVERITY_ORDER[severity] >= SEVERITY_ORDER[policy.severity_hitl_threshold]:
            action = DriftDecisionAction.REQUIRE_HITL_REVIEW
        elif SEVERITY_ORDER[severity] >= SEVERITY_ORDER[policy.severity_confirmation_threshold] or len(extracted.scope_additions) >= policy.scope_expansion_threshold:
            action = DriftDecisionAction.REQUIRE_CONFIRMATION
        else:
            action = DriftDecisionAction.ALLOW_WITH_AUDIT

        classification = DriftClassification.SCOPE_EXPANSION if extracted.scope_additions else DriftClassification.COMPATIBLE_EXTENSION
        return (
            classification,
            severity,
            action,
            rule_findings,
            semantic_result,
            policy,
            f"Material scope/budget/timeline deviation detected. Recommended action: {action.value}."
        )

    # Priority F: Scope Reduction
    if any(r.category == "SCOPE_REDUCTION" for r in rule_findings):
        return (
            DriftClassification.SCOPE_REDUCTION,
            DriftSeverity.LOW,
            DriftDecisionAction.REQUIRE_CONFIRMATION,
            rule_findings,
            semantic_result,
            policy,
            "Scope reduction requested. User confirmation required before contract versioning."
        )

    # Priority G: Compatible Extension / Clarification
    if any(r.category == "COMPATIBLE_CLARIFICATION" for r in rule_findings) or extracted.is_no_change_detected:
        return (
            DriftClassification.NO_DRIFT,
            DriftSeverity.NONE,
            DriftDecisionAction.ALLOW,
            rule_findings,
            semantic_result,
            policy,
            "No material request drift detected. Request is fully aligned with baseline contract parameters."
        )

    # Priority H: Minor Compatible Extension Fallback
    return (
        DriftClassification.COMPATIBLE_EXTENSION,
        DriftSeverity.LOW,
        DriftDecisionAction.ALLOW_WITH_AUDIT,
        rule_findings,
        semantic_result,
        policy,
        "Minor compatible request extension detected."
    )
