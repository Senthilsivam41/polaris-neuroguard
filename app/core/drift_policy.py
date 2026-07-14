"""Configurable Drift Policy Module (DRIFT-008).

Defines typed, validated threshold configuration profiles (Conservative, Balanced, Aggressive)
governing drift material thresholds, scope expansion limits, confirmation & HITL triggers, and budget/timeline tolerances.
"""

from typing import Dict
from pydantic import BaseModel, Field, field_validator
from app.core.drift_models import DriftSeverity


class DriftPolicyProfile(BaseModel):
    """Configuration schema controlling drift evaluation decisions by user risk posture."""
    profile_name: str = Field(..., description="Name of the risk tolerance profile.")
    semantic_drift_material_threshold: float = Field(
        default=0.4, ge=0.0, le=1.0,
        description="Semantic drift score above which drift is considered material."
    )
    scope_expansion_threshold: int = Field(
        default=2, ge=0,
        description="Maximum unconfirmed scope items permitted before requiring confirmation."
    )
    severity_confirmation_threshold: DriftSeverity = Field(
        default=DriftSeverity.MEDIUM,
        description="Minimum severity rating triggering requirement for user confirmation."
    )
    severity_hitl_threshold: DriftSeverity = Field(
        default=DriftSeverity.HIGH,
        description="Minimum severity rating triggering mandatory human-in-the-loop (HITL) review."
    )
    ambiguity_behavior: str = Field(
        default="NEEDS_CLARIFICATION",
        description="Default action on ambiguous requests ('NEEDS_CLARIFICATION' or 'ALLOW_IF_LOW_RISK')."
    )
    max_budget_deviation_percent: float = Field(
        default=15.0, ge=0.0,
        description="Maximum percent budget increase permitted before escalation."
    )
    max_timeline_deviation_months: int = Field(
        default=3, ge=0,
        description="Maximum timeline extension in months permitted before escalation."
    )
    max_sla_reduction_percent: float = Field(
        default=0.1, ge=0.0,
        description="Maximum SLA reduction percentage allowed before escalation."
    )

    @field_validator("ambiguity_behavior")
    @classmethod
    def validate_ambiguity_behavior(cls, v: str) -> str:
        if v not in ["NEEDS_CLARIFICATION", "ALLOW_IF_LOW_RISK"]:
            raise ValueError("ambiguity_behavior must be 'NEEDS_CLARIFICATION' or 'ALLOW_IF_LOW_RISK'.")
        return v


POLICY_PROFILES: Dict[str, DriftPolicyProfile] = {
    "Conservative": DriftPolicyProfile(
        profile_name="Conservative",
        semantic_drift_material_threshold=0.2,
        scope_expansion_threshold=1,
        severity_confirmation_threshold=DriftSeverity.LOW,
        severity_hitl_threshold=DriftSeverity.MEDIUM,
        ambiguity_behavior="NEEDS_CLARIFICATION",
        max_budget_deviation_percent=5.0,
        max_timeline_deviation_months=1,
        max_sla_reduction_percent=0.0
    ),
    "Balanced": DriftPolicyProfile(
        profile_name="Balanced",
        semantic_drift_material_threshold=0.4,
        scope_expansion_threshold=2,
        severity_confirmation_threshold=DriftSeverity.MEDIUM,
        severity_hitl_threshold=DriftSeverity.HIGH,
        ambiguity_behavior="NEEDS_CLARIFICATION",
        max_budget_deviation_percent=15.0,
        max_timeline_deviation_months=3,
        max_sla_reduction_percent=0.1
    ),
    "Aggressive": DriftPolicyProfile(
        profile_name="Aggressive",
        semantic_drift_material_threshold=0.7,
        scope_expansion_threshold=5,
        severity_confirmation_threshold=DriftSeverity.HIGH,
        severity_hitl_threshold=DriftSeverity.CRITICAL,
        ambiguity_behavior="ALLOW_IF_LOW_RISK",
        max_budget_deviation_percent=50.0,
        max_timeline_deviation_months=6,
        max_sla_reduction_percent=0.5
    ),
}


def get_drift_policy(risk_profile: str) -> DriftPolicyProfile:
    """
    Retrieves effective policy configuration for a given risk tolerance profile.
    Defaults to Balanced profile if unspecified or unknown.
    """
    normalized = risk_profile.capitalize() if risk_profile else "Balanced"
    return POLICY_PROFILES.get(normalized, POLICY_PROFILES["Balanced"])
