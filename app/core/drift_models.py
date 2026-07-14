"""Drift Detection Models and Enums (DRIFT-004 to DRIFT-010).

Defines strongly typed Pydantic models and controlled enums for structured change extraction,
rule findings, semantic scoring results, drift classification, risk policy thresholds, and amendment status lifecycle.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class DriftClassification(str, Enum):
    """Controlled classifications for request-intent drift."""
    NO_DRIFT = "NO_DRIFT"
    CLARIFICATION = "CLARIFICATION"
    COMPATIBLE_EXTENSION = "COMPATIBLE_EXTENSION"
    SCOPE_EXPANSION = "SCOPE_EXPANSION"
    SCOPE_REDUCTION = "SCOPE_REDUCTION"
    CONSTRAINT_CONFLICT = "CONSTRAINT_CONFLICT"
    OBJECTIVE_CONFLICT = "OBJECTIVE_CONFLICT"
    GOAL_REPLACEMENT = "GOAL_REPLACEMENT"
    AMBIGUOUS = "AMBIGUOUS"
    POLICY_OR_SECURITY_RISK = "POLICY_OR_SECURITY_RISK"


class DriftSeverity(str, Enum):
    """Categorical severity rating for detected drift."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DriftDecisionAction(str, Enum):
    """Recommended action resulting from drift evaluation."""
    ALLOW = "ALLOW"
    ALLOW_WITH_AUDIT = "ALLOW_WITH_AUDIT"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    REQUIRE_HITL_REVIEW = "REQUIRE_HITL_REVIEW"
    REJECT = "REJECT"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class AmendmentStatus(str, Enum):
    """Lifecycle states for a goal amendment request."""
    PENDING_EVALUATION = "PENDING_EVALUATION"
    NO_AMENDMENT_NEEDED = "NO_AMENDMENT_NEEDED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    PENDING_HITL_REVIEW = "PENDING_HITL_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class ExtractedChangeRequest(BaseModel):
    """Structured extraction output detailing changes requested relative to an active Goal Contract (DRIFT-004)."""
    request_id: str = Field(..., description="Target request ID.")
    contract_id: str = Field(..., description="Active Goal Contract ID.")
    contract_version: int = Field(..., description="Active Goal Contract version number.")
    raw_request_text: str = Field(..., description="Raw text of natural language change request.")
    
    # Delta fields
    objective_changes: Optional[str] = Field(default=None, description="Extracted changes to objective.")
    deliverable_additions: List[str] = Field(default_factory=list, description="Deliverables added.")
    deliverable_removals: List[str] = Field(default_factory=list, description="Deliverables removed.")
    scope_additions: List[str] = Field(default_factory=list, description="In-scope items added.")
    scope_removals: List[str] = Field(default_factory=list, description="In-scope items removed.")
    new_exclusions: List[str] = Field(default_factory=list, description="Exclusions added.")
    constraint_additions: List[str] = Field(default_factory=list, description="Constraints added.")
    constraint_removals: List[str] = Field(default_factory=list, description="Constraints removed.")
    
    budget_limit_usd: Optional[float] = Field(default=None, description="Requested budget limit USD.")
    target_timeline_months: Optional[int] = Field(default=None, description="Requested target timeline in months.")
    reliability_target_sla: Optional[float] = Field(default=None, description="Requested reliability SLA %.")
    risk_tolerance: Optional[str] = Field(default=None, description="Requested risk tolerance profile.")
    
    assumption_changes: List[str] = Field(default_factory=list, description="Assumption additions/removals.")
    acceptance_criteria_changes: List[str] = Field(default_factory=list, description="Acceptance criteria changes.")
    
    is_no_change_detected: bool = Field(default=False, description="True if input request contains no functional changes.")
    ambiguity_flags: List[str] = Field(default_factory=list, description="List of detected ambiguous phrasing flags.")
    prompt_injection_flag: bool = Field(default=False, description="True if prompt injection / adversarial manipulation detected.")
    
    extraction_evidence: str = Field(default="", description="Field-level extraction evidence summary.")
    extraction_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score.")


class RuleFinding(BaseModel):
    """Finding produced by a deterministic goal or constraint drift rule (DRIFT-005)."""
    rule_id: str = Field(..., description="Unique rule identifier (e.g. RULE-CONSTRAINTS-001).")
    category: str = Field(..., description="Rule evaluation category.")
    triggered_fields: List[str] = Field(..., description="Contract/request fields that triggered this rule.")
    evidence: str = Field(..., description="Deterministic evidence string explaining rule trigger.")
    severity_contribution: DriftSeverity = Field(..., description="Severity contribution of this rule.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Deterministic rule confidence.")


class SemanticScorerResult(BaseModel):
    """Result of semantic score calculation (DRIFT-006)."""
    drift_score: float = Field(..., ge=0.0, le=1.0, description="Normalized semantic drift score [0.0 - 1.0].")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Semantic model confidence.")
    semantic_evidence: str = Field(..., description="Explanation of semantic alignment or deviation.")
    matched_concepts: List[str] = Field(default_factory=list, description="Matched domain concepts.")
    contradicted_concepts: List[str] = Field(default_factory=list, description="Contradicted domain concepts.")
    is_fallback: bool = Field(default=False, description="True if fallback scorer was used.")
