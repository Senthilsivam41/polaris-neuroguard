"""HITL Interruption Module (HITL-001).

Defines the typed InterruptionReason enum, InterruptionPayload schema,
and ADKInterruptionError exception for real ADK workflow interruptions.
"""

import uuid
from enum import Enum
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from google.adk.workflow._errors import NodeInterruptedError


class InterruptionReason(str, Enum):
    STATIC_CONSTRAINT_DEADLOCK = "STATIC_CONSTRAINT_DEADLOCK"
    SEMANTIC_CONSTRAINT_DEADLOCK = "SEMANTIC_CONSTRAINT_DEADLOCK"
    COLLISION_THREAT = "COLLISION_THREAT"
    DRIFT_REQUIRES_CONFIRMATION = "DRIFT_REQUIRES_CONFIRMATION"
    DRIFT_REQUIRES_HITL_REVIEW = "DRIFT_REQUIRES_HITL_REVIEW"
    AMENDMENT_REJECTED = "AMENDMENT_REJECTED"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    UNKNOWN = "UNKNOWN"


class InterruptionPayload(BaseModel):
    interruption_id: str = Field(default_factory=lambda: f"int-{uuid.uuid4()}")
    simulation_id: str
    invocation_id: str
    workflow_node: str
    reason: InterruptionReason
    severity: str = Field(default="HIGH", description="Severity level: CRITICAL, HIGH, MEDIUM, LOW")
    explanation: str
    safe_telemetry_snapshot: Dict[str, Any] = Field(default_factory=dict)
    goal_contract_id: Optional[str] = None
    active_contract_version: Optional[int] = None
    change_request_id: Optional[str] = None
    amendment_id: Optional[str] = None
    required_resolution_action: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = Field(default="ACTIVE", description="State of interruption: ACTIVE, RESOLVED, EXPIRED, CANCELLED")


class ADKInterruptionError(NodeInterruptedError):
    """Exception raised by ADK workflow nodes to trigger a real ADK interruption."""

    def __init__(self, payload: InterruptionPayload):
        super().__init__(f"Workflow interrupted: [{payload.reason.value}] {payload.explanation}")
        self.payload = payload
