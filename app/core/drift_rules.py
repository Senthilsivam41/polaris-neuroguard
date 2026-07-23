"""Deterministic Goal and Constraint Drift Rules Engine (DRIFT-005).

Evaluates pure, independently testable rules comparing an ExtractedChangeRequest against the active GoalContract.
Identifies contradictions, scope changes, budget/timeline deviations, and excluded-outcome violations without LLM dependencies.
"""

from typing import List
from app.core.goal_contract import GoalContract
from app.core.drift_models import ExtractedChangeRequest, RuleFinding, DriftSeverity


OPPOSING_CONSTRAINT_PAIRS = [
    ("RIGID_TIMELINE", "FREEZE_HEADCOUNT"),
    ("RIGID_TIMELINE", "EXTEND_SCHEDULE"),
    ("FREEZE_HEADCOUNT", "EXPAND_SCOPE"),
    ("REDUCE_COST", "EXPAND_SCOPE"),
    ("STRICT_COMPLIANCE", "BYPASS_AUDIT"),
]


def evaluate_deterministic_rules(
    contract: GoalContract,
    extracted: ExtractedChangeRequest
) -> List[RuleFinding]:
    """
    Evaluates pure, deterministic rules comparing extracted change requests against active contract parameters.
    """
    findings: List[RuleFinding] = []

    # 1. Prompt Injection / Security Violation Check
    if extracted.prompt_injection_flag:
        findings.append(RuleFinding(
            rule_id="RULE-SEC-001",
            category="SECURITY_VIOLATION",
            triggered_fields=["raw_request_text"],
            evidence="Prompt injection / adversarial override phrasing detected in input text.",
            severity_contribution=DriftSeverity.CRITICAL,
            confidence=1.0
        ))

    # 2. Objective Replacement Check
    if extracted.objective_changes and extracted.objective_changes.lower() != contract.normalized_objective.lower():
        findings.append(RuleFinding(
            rule_id="RULE-OBJ-001",
            category="OBJECTIVE_REPLACEMENT",
            triggered_fields=["normalized_objective"],
            evidence=f"Request proposes replacing active baseline objective '{contract.normalized_objective}' with '{extracted.objective_changes}'.",
            severity_contribution=DriftSeverity.HIGH,
            confidence=1.0
        ))

    # 3. Direct Constraint Contradictions (Opposing constraint pairs)
    active_constraints = set(contract.constraints + extracted.constraint_additions)
    for c_a, c_b in OPPOSING_CONSTRAINT_PAIRS:
        if c_a in active_constraints and c_b in active_constraints:
            findings.append(RuleFinding(
                rule_id=f"RULE-CONSTR-PAIR-{c_a}-{c_b}",
                category="DIRECT_CONSTRAINT_CONTRADICTION",
                triggered_fields=["constraints"],
                evidence=f"Direct opposing-pair contradiction between active constraints '{c_a}' and '{c_b}'.",
                severity_contribution=DriftSeverity.HIGH,
                confidence=1.0
            ))

    # 4. Excluded Outcome / Scope Conflicts
    all_exclusions = set(contract.explicit_exclusions + contract.outcomes.excluded_outcomes)
    for scope_item in (extracted.scope_additions + extracted.deliverable_additions):
        for excl in all_exclusions:
            if excl.lower() in scope_item.lower() or scope_item.lower() in excl.lower():
                findings.append(RuleFinding(
                    rule_id="RULE-EXCL-001",
                    category="EXCLUDED_OUTCOME_CONFLICT",
                    triggered_fields=["outcomes.excluded_outcomes", "scope_additions"],
                    evidence=f"Requested scope addition '{scope_item}' violates explicit contract exclusion '{excl}'.",
                    severity_contribution=DriftSeverity.HIGH,
                    confidence=1.0
                ))

    # 5. Budget Modifications
    if extracted.budget_limit_usd is not None and round(extracted.budget_limit_usd, 2) != round(contract.budget_limit_usd, 2):
        diff = extracted.budget_limit_usd - contract.budget_limit_usd
        direction = "increase" if diff > 0 else "reduction"
        sev = DriftSeverity.MEDIUM if abs(diff) > 100000.0 else DriftSeverity.LOW
        findings.append(RuleFinding(
            rule_id="RULE-FIN-001",
            category="BUDGET_CHANGE",
            triggered_fields=["budget_limit_usd"],
            evidence=f"Requested budget {direction} from USD {contract.budget_limit_usd:,.2f} to USD {extracted.budget_limit_usd:,.2f} (delta: {diff:+,.2f}).",
            severity_contribution=sev,
            confidence=1.0
        ))

    # 6. Timeline Modifications
    if extracted.target_timeline_months is not None and extracted.target_timeline_months != contract.target_timeline_months:
        diff = extracted.target_timeline_months - contract.target_timeline_months
        direction = "extension" if diff > 0 else "compression"
        
        # Conflict check if timeline compressed while RIGID_TIMELINE constraint is active
        if direction == "extension" and "RIGID_TIMELINE" in contract.constraints:
            sev = DriftSeverity.HIGH
            cat = "DIRECT_CONSTRAINT_CONTRADICTION"
            ev = f"Requested timeline extension to {extracted.target_timeline_months} months violates RIGID_TIMELINE constraint."
        else:
            sev = DriftSeverity.MEDIUM if abs(diff) >= 3 else DriftSeverity.LOW
            cat = "TIMELINE_CHANGE"
            ev = f"Requested timeline {direction} from {contract.target_timeline_months} to {extracted.target_timeline_months} months."

        findings.append(RuleFinding(
            rule_id="RULE-TIME-001",
            category=cat,
            triggered_fields=["target_timeline_months"],
            evidence=ev,
            severity_contribution=sev,
            confidence=1.0
        ))

    # 7. Reliability SLA Modifications
    if extracted.reliability_target_sla is not None and round(extracted.reliability_target_sla, 4) != round(contract.reliability_target_sla, 4):
        diff = extracted.reliability_target_sla - contract.reliability_target_sla
        sev = DriftSeverity.HIGH if diff < -0.1 else DriftSeverity.LOW
        findings.append(RuleFinding(
            rule_id="RULE-SLA-001",
            category="RELIABILITY_CHANGE",
            triggered_fields=["reliability_target_sla"],
            evidence=f"Requested SLA change from {contract.reliability_target_sla}% to {extracted.reliability_target_sla}% (delta: {diff:+.2f}%).",
            severity_contribution=sev,
            confidence=1.0
        ))

    # 8. Scope Expansion / Reduction
    if extracted.scope_additions or extracted.deliverable_additions:
        items = list(set(extracted.scope_additions + extracted.deliverable_additions))
        findings.append(RuleFinding(
            rule_id="RULE-SCOPE-EXP-001",
            category="SCOPE_EXPANSION",
            triggered_fields=["scope_additions", "deliverables"],
            evidence=f"Scope expansion proposed: {', '.join(items)}.",
            severity_contribution=DriftSeverity.MEDIUM,
            confidence=1.0
        ))

    if extracted.scope_removals or extracted.deliverable_removals:
        items = list(set(extracted.scope_removals + extracted.deliverable_removals))
        findings.append(RuleFinding(
            rule_id="RULE-SCOPE-RED-001",
            category="SCOPE_REDUCTION",
            triggered_fields=["scope_removals", "deliverables"],
            evidence=f"Scope reduction proposed: {', '.join(items)}.",
            severity_contribution=DriftSeverity.LOW,
            confidence=1.0
        ))

    # 9. Ambiguity Check
    if extracted.ambiguity_flags:
        findings.append(RuleFinding(
            rule_id="RULE-AMBIGUOUS-001",
            category="AMBIGUOUS_REQUEST",
            triggered_fields=["raw_request_text"],
            evidence=f"Vague or ambiguous phrasing requires explicit clarification: {'; '.join(extracted.ambiguity_flags)}.",
            severity_contribution=DriftSeverity.LOW,
            confidence=1.0
        ))

    # 10. Compatible Clarification (when no changes or minor compatible wording)
    if extracted.is_no_change_detected or (not findings and not extracted.prompt_injection_flag):
        findings.append(RuleFinding(
            rule_id="RULE-CLARIFY-001",
            category="COMPATIBLE_CLARIFICATION",
            triggered_fields=["raw_request_text"],
            evidence="Request is fully consistent with active contract baseline parameters.",
            severity_contribution=DriftSeverity.NONE,
            confidence=1.0
        ))

    return findings
