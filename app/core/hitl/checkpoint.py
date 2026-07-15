"""HITL Checkpoint Data Model & Redaction Module (HITL-002).

Defines WorkflowCheckpoint model, sensitive data redaction, state schema validation,
and SHA-256 state fingerprinting.
"""

import uuid
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from app.core.hitl.interruption import InterruptionPayload
from app.core.state import SimulationStateSchema


PROHIBITED_SECRET_KEYS = {
    "api_key", "secret", "password", "token", "raw_prompt",
    "prompt", "chain_of_thought", "thought", "reasoning_steps",
    "hidden_reasoning", "auth_token"
}


def sanitize_and_fingerprint_state(state_dict: Dict[str, Any]) -> tuple[Dict[str, Any], str]:
    """Sanitize state dictionary, validate with SimulationStateSchema, and generate SHA-256 fingerprint.

    Removes secrets, raw prompts, and model internal chain-of-thought fields.
    """
    # 1. Strip sensitive key-values recursively
    def _sanitize(item: Any) -> Any:
        if isinstance(item, dict):
            clean_dict = {}
            for k, v in item.items():
                if k.lower() in PROHIBITED_SECRET_KEYS:
                    continue
                clean_dict[k] = _sanitize(v)
            return clean_dict
        elif isinstance(item, list):
            return [_sanitize(x) for x in item]
        return item

    sanitized = _sanitize(state_dict)

    # 2. Validate with SimulationStateSchema
    validated_schema = SimulationStateSchema.model_validate(sanitized)
    clean_state = validated_schema.model_dump()

    # 3. Compute deterministic canonical JSON fingerprint
    canonical_json = json.dumps(clean_state, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    return clean_state, fingerprint


class WorkflowCheckpoint(BaseModel):
    checkpoint_id: str = Field(default_factory=lambda: f"chk-{uuid.uuid4()}")
    simulation_id: str
    invocation_id: str
    node_position: str
    validated_state: Dict[str, Any]
    state_fingerprint: str
    interruption_payload: InterruptionPayload
    active_contract_id: Optional[str] = None
    active_contract_version: Optional[int] = None
    change_request_id: Optional[str] = None
    amendment_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    checkpoint_status: str = Field(
        default="ACTIVE",
        description="Status: ACTIVE, RESOLVED, EXPIRED, CANCELLED, SUPERSEDED"
    )
    resume_attempt_count: int = Field(default=0, ge=0)
    idempotency_key: Optional[str] = None
    checkpoint_version: int = Field(default=1, ge=1, description="Optimistic locking version number")
    completed_nodes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Cached output events of earlier completed nodes to avoid duplicate side effects"
    )
