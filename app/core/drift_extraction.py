"""Structured Change Extraction Module (DRIFT-004).

Extracts structured parameter deltas, ambiguity flags, prompt injection risks, and domain intent
from raw natural-language change requests relative to an active Goal Contract.
"""

import re
from typing import Optional, List, Tuple
from app.core.goal_contract import GoalContract
from app.core.drift_models import ExtractedChangeRequest


PROMPT_INJECTION_PATTERNS = [
    r"ignore (all )?(previous|above|prior) (instructions|directions|rules)",
    r"bypass (all )?(security|guardrails|filters|rules)",
    r"forget (all )?(previous|prior) (rules|instructions)",
    r"system prompt:",
    r"override security",
    r"you are now in god mode",
    r"sudo ",
]

AMBIGUOUS_KEYWORDS = [
    "faster", "better", "cheaper", "soon", "asap", "more", "less", "upgrade",
    "optimize", "improve", "make it good", "whatever", "maybe", "kind of"
]

NO_CHANGE_PHRASES = [
    "everything looks good", "no changes", "no change", "looks good",
    "proceed as planned", "no update needed", "confirming baseline",
    "continue", "keep as is", "status quo"
]


def extract_structured_changes(
    request_id: str,
    raw_request_text: str,
    contract: GoalContract
) -> ExtractedChangeRequest:
    """
    Extracts structured changes from natural-language request text against an active GoalContract.
    Does not mutate the active contract.
    """
    text_lower = raw_request_text.lower().strip()
    evidence_parts: List[str] = []
    
    # 1. Prompt Injection / Security Check
    injection_flag = False
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text_lower):
            injection_flag = True
            evidence_parts.append(f"Prompt injection pattern detected: '{pattern}'")
            break

    # 2. No-change check
    is_no_change = False
    if any(phrase in text_lower for phrase in NO_CHANGE_PHRASES) or text_lower in ["none", "n/a", "no"]:
        is_no_change = True
        evidence_parts.append("Request indicates no structural change to goal contract.")

    # 3. Ambiguity check
    ambiguity_flags: List[str] = []
    for kw in AMBIGUOUS_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
            # If vague without quantitative specification, flag ambiguity
            if not re.search(r"\d+", text_lower):
                ambiguity_flags.append(f"Vague modifier '{kw}' without explicit numeric threshold.")

    if ambiguity_flags:
        evidence_parts.append(f"Ambiguity detected: {'; '.join(ambiguity_flags)}")

    # 4. Budget Extraction
    budget_limit_usd: Optional[float] = None
    # H1: explicit currency/number "budget to $500k", "budget 500000", "budget to 500,000 usd"
    budget_match = re.search(r"budget\s*(?:to|of|is|=|:)?\s*\$?([0-9,]+(?:\.[0-9]+)?)\s*(?:k|m|usd)?", text_lower)
    if budget_match:
        val_str = budget_match.group(1).replace(",", "")
        try:
            val = float(val_str)
            if "k" in budget_match.group(0):
                val *= 1000
            elif "m" in budget_match.group(0):
                val *= 1000000
            budget_limit_usd = val
            evidence_parts.append(f"Extracted budget limit: USD {val:,.2f}")
        except ValueError:
            pass

    # 5. Timeline Extraction
    target_timeline_months: Optional[int] = None
    timeline_match = re.search(r"(?:timeline|schedule|duration|deadline)\s*(?:to|of|is|=|:)?\s*([0-9]+)\s*months?", text_lower)
    if timeline_match:
        try:
            target_timeline_months = int(timeline_match.group(1))
            evidence_parts.append(f"Extracted timeline: {target_timeline_months} months")
        except ValueError:
            pass

    # 6. SLA Extraction
    reliability_target_sla: Optional[float] = None
    sla_match = re.search(r"(?:sla|reliability)\s*(?:to|of|is|=|:)?\s*([0-9]+(?:\.[0-9]+)?)\s*%", text_lower)
    if sla_match:
        try:
            reliability_target_sla = float(sla_match.group(1))
            evidence_parts.append(f"Extracted SLA: {reliability_target_sla}%")
        except ValueError:
            pass

    # 7. Constraint Additions & Removals
    constraint_additions: List[str] = []
    constraint_removals: List[str] = []
    
    known_constraints = [
        "RIGID_TIMELINE", "FREEZE_HEADCOUNT", "REDUCE_COST",
        "EXPAND_SCOPE", "EXTEND_SCHEDULE", "ZERO_DOWNTIME_DEPLOYMENT",
        "STRICT_COMPLIANCE"
    ]
    for c in known_constraints:
        c_clean = c.lower().replace("_", " ")
        if f"add constraint {c_clean}" in text_lower or f"require {c_clean}" in text_lower or c in raw_request_text:
            constraint_additions.append(c)
        elif f"remove constraint {c_clean}" in text_lower or f"drop {c_clean}" in text_lower or f"cancel {c_clean}" in text_lower:
            constraint_removals.append(c)

    if constraint_additions:
        evidence_parts.append(f"Constraint additions: {', '.join(constraint_additions)}")
    if constraint_removals:
        evidence_parts.append(f"Constraint removals: {', '.join(constraint_removals)}")

    # 8. Scope / Deliverable Additions
    scope_additions: List[str] = []
    if any(k in text_lower for k in ["add scope", "include", "expand scope", "add deliverable", "add "]):
        match = re.search(r"(?:include|add scope|add deliverable|add)\s*[:\-]?\s*([^\.\n,]+?)(?:\s+deliverable|\s+scope|\.|\n|$)", raw_request_text, re.IGNORECASE)
        if match:
            item = match.group(1).strip()
            # Exclude budget numbers, numeric values, or constraints
            if item and not re.match(r"^[\$\d\.,\s]+$", item) and item.lower() not in ["constraint", "rigid timeline", "extend schedule"]:
                scope_additions.append(item)
                evidence_parts.append(f"Extracted scope addition: {item}")

    # 9. Objective replacement check
    objective_changes: Optional[str] = None
    if "replace objective" in text_lower or "pivot goal" in text_lower or "new objective" in text_lower:
        match = re.search(r"(?:replace objective|new objective|pivot goal)\s*(?:with|to|:)?\s*([^\.\n]+)", raw_request_text, re.IGNORECASE)
        if match:
            objective_changes = match.group(1).strip()
            evidence_parts.append(f"Extracted objective replacement: '{objective_changes}'")

    if not evidence_parts:
        evidence_parts.append("Natural-language request text processed for domain intent.")

    return ExtractedChangeRequest(
        request_id=request_id,
        contract_id=contract.contract_id,
        contract_version=contract.contract_version,
        raw_request_text=raw_request_text,
        objective_changes=objective_changes,
        deliverable_additions=scope_additions,
        deliverable_removals=[],
        scope_additions=scope_additions,
        scope_removals=[],
        new_exclusions=[],
        constraint_additions=constraint_additions,
        constraint_removals=constraint_removals,
        budget_limit_usd=budget_limit_usd,
        target_timeline_months=target_timeline_months,
        reliability_target_sla=reliability_target_sla,
        risk_tolerance=None,
        assumption_changes=[],
        acceptance_criteria_changes=[],
        is_no_change_detected=is_no_change,
        ambiguity_flags=ambiguity_flags,
        prompt_injection_flag=injection_flag,
        extraction_evidence="; ".join(evidence_parts),
        extraction_confidence=1.0 if not ambiguity_flags else 0.7
    )
