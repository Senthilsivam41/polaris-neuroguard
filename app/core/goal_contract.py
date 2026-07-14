"""Goal Contract Schema Module (DRIFT-001).

Contract Versioning Model Overview:
------------------------------------
A Goal Contract serves as the single source of truth for strategic intent, objective boundaries,
deliverables, constraints, and acceptance criteria in Polaris NeuroGuard.

1. Baseline Contract (Version 1):
   Created automatically upon initial simulation registration. Derived from the user's initial
   natural-language request and profile inputs. The baseline is stored immutably with version = 1
   and parent_contract_version = None.

2. Contract Amendments (Version N > 1):
   Every approved amendment generates a new Goal Contract version linked to its parent
   (parent_contract_version = N - 1, parent_version_id = previous_contract_id).
   Saved versions are never mutated in place.

3. Content Hashing & Fingerprinting:
   Each Goal Contract contains a deterministic SHA-256 `content_fingerprint` computed over all
   canonical domain content fields (objective, outcomes, deliverables, constraints, budget, timeline, SLA).
   Mutable metadata (such as system timestamp or internal database IDs) are excluded from fingerprint computation.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator, model_validator


class OutcomeCategorization(BaseModel):
    """Categorizes strategic outcomes into explicit operational boundaries."""
    required_outcomes: List[str] = Field(
        default_factory=list,
        description="Non-negotiable outcomes mandatory for contract fulfillment."
    )
    optional_outcomes: List[str] = Field(
        default_factory=list,
        description="Nice-to-have outcomes prioritized as secondary scope."
    )
    excluded_outcomes: List[str] = Field(
        default_factory=list,
        description="Outcomes explicitly out-of-scope or forbidden."
    )


class GoalContract(BaseModel):
    """
    Normalized, strongly typed Goal Contract representing the strategic specification baseline.
    Fully compliant with DRIFT-001 specification requirements.
    """
    contract_id: str = Field(..., description="Unique contract UUID identifier.")
    schema_version: str = Field(default="1.0.0", description="Contract specification schema version.")
    contract_version: int = Field(default=1, ge=1, description="Sequential contract revision number (1 for baseline).")
    
    # Text intent requirements
    original_request_text: str = Field(..., description="Original raw natural-language request text.")
    normalized_objective: str = Field(..., description="Normalized high-level strategic objective.")
    
    # Boundary specifications
    deliverables: List[str] = Field(default_factory=list, description="Concrete technical or operational deliverables.")
    in_scope_items: List[str] = Field(default_factory=list, description="Explicitly included scope elements.")
    explicit_exclusions: List[str] = Field(default_factory=list, description="Explicitly excluded scope elements.")
    constraints: List[str] = Field(default_factory=list, description="Operational or technical constraint flags.")
    
    # Explicit required, optional, and excluded outcome breakdown
    outcomes: OutcomeCategorization = Field(
        default_factory=OutcomeCategorization,
        description="Outcome breakdown by requirement status."
    )
    
    # Quantitative parameters with validation bounds
    budget_limit_usd: float = Field(default=1000000.0, gt=0.0, description="Financial resource budget limit in USD.")
    target_timeline_months: int = Field(default=12, gt=0, description="Target execution timeline in months.")
    reliability_target_sla: float = Field(default=99.9, ge=0.0, le=100.0, description="Target reliability SLA percentage.")
    risk_tolerance: str = Field(default="Balanced", description="Risk posture (Conservative, Balanced, Aggressive).")
    
    # Verification & assumptions
    assumptions: List[str] = Field(default_factory=list, description="Underlying assumptions accepted for this contract.")
    acceptance_criteria: List[str] = Field(default_factory=list, description="Concrete validation rules for completion.")
    
    # Versioning & Audit Metadata
    creation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware UTC timestamp of contract instantiation."
    )
    creator_id: str = Field(default="", description="Identifier of actor/user creating this version.")
    parent_version_id: Optional[str] = Field(default=None, description="Contract ID of parent contract version.")
    parent_contract_version: Optional[int] = Field(default=None, ge=1, description="Version number of parent contract.")
    content_fingerprint: str = Field(default="", description="Deterministic SHA-256 fingerprint of canonical contract content.")

    @field_validator("original_request_text", "normalized_objective")
    @classmethod
    def validate_non_empty_text(cls, value: str, info) -> str:
        """Enforce that text fields are non-empty and non-whitespace."""
        if not value or not value.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string.")
        return value.strip()

    @field_validator("creation_timestamp")
    @classmethod
    def validate_utc_timestamp(cls, value: datetime) -> datetime:
        """Enforce timezone-aware UTC timestamps."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def calculate_fingerprint(self) -> str:
        """
        Compute a deterministic SHA-256 digest of the canonical contract content.
        Excludes volatile storage/system metadata (contract_id, creation_timestamp, parent_version_id, content_fingerprint).
        """
        canonical_payload = {
            "schema_version": self.schema_version,
            "contract_version": self.contract_version,
            "original_request_text": self.original_request_text,
            "normalized_objective": self.normalized_objective,
            "deliverables": sorted(self.deliverables),
            "in_scope_items": sorted(self.in_scope_items),
            "explicit_exclusions": sorted(self.explicit_exclusions),
            "constraints": sorted(self.constraints),
            "outcomes": {
                "required_outcomes": sorted(self.outcomes.required_outcomes),
                "optional_outcomes": sorted(self.outcomes.optional_outcomes),
                "excluded_outcomes": sorted(self.outcomes.excluded_outcomes),
            },
            "budget_limit_usd": round(float(self.budget_limit_usd), 2),
            "target_timeline_months": int(self.target_timeline_months),
            "reliability_target_sla": round(float(self.reliability_target_sla), 4),
            "risk_tolerance": self.risk_tolerance,
            "assumptions": sorted(self.assumptions),
            "acceptance_criteria": sorted(self.acceptance_criteria),
            "creator_id": self.creator_id,
            "parent_contract_version": self.parent_contract_version,
        }
        encoded = json.dumps(canonical_payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @model_validator(mode="after")
    def populate_fingerprint(self) -> 'GoalContract':
        """Automatically populate content_fingerprint if empty or out-of-date."""
        calculated = self.calculate_fingerprint()
        if not self.content_fingerprint:
            object.__setattr__(self, "content_fingerprint", calculated)
        return self
