"""HITL Resume Service & Orchestration Module (HITL-003).

Orchestrates simulation workflow resume from durable checkpoints using ADK's real
resume mechanism. Enforces actor authorization, idempotency, version conflict detection,
and goal-contract version alignment outside FastAPI handlers.
"""

import logging
import uuid
import threading
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)
from pydantic import BaseModel, Field
from fastapi import HTTPException

from app.core.hitl.checkpoint_service import (
    checkpoint_service,
    CheckpointNotFoundError,
    CheckpointVersionConflictError,
    CheckpointExpiredError,
)
from app.core.state import update_typed_state, get_typed_state
from app.core.hitl.interruption import ADKInterruptionError


class ResumeRequestPayload(BaseModel):
    checkpoint_id: str = Field(..., description="Target checkpoint ID to resume from")
    resume_request_id: str = Field(..., description="Unique idempotency key for this resume request")
    actor_id: str = Field(..., description="Actor/User ID attempting the resume")
    resolution_action: str = Field(..., description="Description of resolution action taken")
    approval_decision_id: Optional[str] = Field(default=None, description="Optional approval or amendment ID")
    amendment_id: Optional[str] = Field(default=None, description="Optional amendment ID")
    expected_checkpoint_version: int = Field(..., ge=1, description="Expected checkpoint version number for optimistic locking")
    intent_vector: Optional[Dict[str, float]] = Field(default=None, description="Optional overridden intent vector")
    declared_constraints: Optional[List[str]] = Field(default=None, description="Optional updated declared constraints list")


class ResumeResponsePayload(BaseModel):
    simulation_id: str
    checkpoint_id: str
    resumed_invocation_id: str
    resume_status: str = Field(..., description="RUNNING or PAUSED_BY_GUARDRAIL")
    current_workflow_state: Dict[str, Any]
    telemetry: Dict[str, Any]
    active_contract_version: int
    remaining_interruption_details: Optional[Dict[str, Any]] = None
    correlation_id: str


class ResumeService:
    """Thread-safe orchestration service for executing simulation workflow resume operations."""

    def __init__(self):
        self._processed_resumes: Dict[str, Dict[str, Any]] = {}  # resume_request_id -> response_dict
        self._lock = threading.Lock()

    def clear(self) -> None:
        """Clear processing cache (used for test isolation)."""
        with self._lock:
            self._processed_resumes.clear()

    async def execute_resume(
        self,
        simulation_id: str,
        payload: ResumeRequestPayload,
        sim_session: Dict[str, Any],
        runner: Any
    ) -> Dict[str, Any]:
        """Validate ownership, checkpoint version, idempotency, and execute ADK resume."""
        request_id = payload.resume_request_id

        # 1. Idempotency check: return cached response if request_id already processed
        with self._lock:
            if request_id in self._processed_resumes:
                return self._processed_resumes[request_id].copy()

        # 2. Authorization check: actor_id must match simulation owner
        owner_id = sim_session.get("profile", {}).get("user_id", "")
        if payload.actor_id and owner_id and payload.actor_id != owner_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "UNAUTHORIZED_RESUME",
                    "message": f"Actor '{payload.actor_id}' is not authorized to resume simulation owned by '{owner_id}'.",
                    "simulation_id": simulation_id,
                    "actor_id": payload.actor_id,
                    "owner_id": owner_id,
                }
            )

        # 3. Retrieve target checkpoint
        try:
            chk = checkpoint_service.get_by_id(payload.checkpoint_id)
        except CheckpointNotFoundError as e:
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "CHECKPOINT_NOT_FOUND",
                    "message": str(e),
                    "simulation_id": simulation_id,
                    "checkpoint_id": payload.checkpoint_id,
                }
            ) from e

        # Check simulation mismatch
        if chk.simulation_id != simulation_id:
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "CHECKPOINT_NOT_FOUND",
                    "message": f"Checkpoint '{payload.checkpoint_id}' belongs to a different simulation.",
                    "simulation_id": simulation_id,
                    "checkpoint_id": payload.checkpoint_id,
                }
            )

        # 4. Check optimistic versioning conflict
        if chk.checkpoint_version != payload.expected_checkpoint_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "CHECKPOINT_VERSION_CONFLICT",
                    "message": f"Checkpoint version conflict: Expected version {payload.expected_checkpoint_version}, but active version is {chk.checkpoint_version}.",
                    "simulation_id": simulation_id,
                    "checkpoint_id": chk.checkpoint_id,
                    "expected_version": payload.expected_checkpoint_version,
                    "active_version": chk.checkpoint_version,
                }
            )

        # 5. Check resolution action validity
        if not payload.resolution_action or not payload.resolution_action.strip():
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "RESOLUTION_REQUIRED",
                    "message": "A non-empty resolution action or amendment confirmation is required to resume the simulation.",
                    "simulation_id": simulation_id,
                    "checkpoint_id": chk.checkpoint_id,
                }
            )

        # 6. Fetch existing ADK session
        adk_session = runner.session_service.get_session_sync(
            app_name="polaris-neuroguard",
            user_id=owner_id,
            session_id=simulation_id
        )
        if adk_session is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "ADK_SESSION_NOT_FOUND",
                    "message": f"ADK Session not found for simulation '{simulation_id}'.",
                    "simulation_id": simulation_id,
                }
            )

        # 7. Prepare state delta for ADK resume from stored context
        invocation_id = chk.invocation_id
        active_contract_version = sim_session.get("active_contract_version", 1)

        raw_delta: Dict[str, Any] = {
            "hitl_interrupted": False,
            "hitl_reason": "",
            "hitl_telemetry_snapshot": None,
            "interruption_payload": None,
            "active_contract_version": active_contract_version,
        }

        # Clear deadlocks if payload overrides declared_constraints
        if payload.declared_constraints is not None:
            raw_delta["declared_constraints"] = payload.declared_constraints
            raw_delta["active_deadlocks"] = []

        if payload.intent_vector is not None:
            raw_delta["intent_vector"] = payload.intent_vector

        # Validate the transition against the typed-state contract (raises on
        # invalid deltas) using the fetched session copy.
        update_typed_state(adk_session.state, raw_delta, validate_transition=True)

        # Persist the resolution delta as a session event. Runner.run_async only
        # persists state_delta when a new_message accompanies it; a resume call
        # has no new message, so without this event the cleared constraints /
        # intent override never reach the resumed invocation and the workflow
        # re-interrupts on the same deadlock.
        from google.adk.events import Event, EventActions
        resolution_event = Event(
            invocation_id=invocation_id,
            author="user",
            actions=EventActions(state_delta=raw_delta),
        )
        await runner.session_service.append_event(adk_session, resolution_event)

        trace_id = str(uuid.uuid4())
        second_interruption = None

        # 8. Resume workflow execution using ADK runner with stored invocation context
        try:
            events = []
            async for event in runner.run_async(
                user_id=owner_id,
                session_id=simulation_id,
                invocation_id=invocation_id,
                state_delta=raw_delta
            ):
                events.append(event)
        except ADKInterruptionError as exc:
            second_interruption = exc.payload
        except Exception as exc:
            # ADK runner may catch ADKInterruptionError inside node loop, read updated state
            logger.warning(
                "Resume run_async raised %s for simulation %s (invocation %s): %s",
                type(exc).__name__, simulation_id, invocation_id, exc,
            )

        # Fetch latest state after resume attempt
        updated_adk = runner.session_service.get_session_sync(
            app_name="polaris-neuroguard",
            user_id=owner_id,
            session_id=simulation_id
        )
        final_state = get_typed_state(updated_adk.state)

        # 9. Process resume results
        if final_state.hitl_interrupted or second_interruption:
            # Workflow encountered another blocking condition immediately
            status = "PAUSED_BY_GUARDRAIL"
            remaining_details = (
                second_interruption.model_dump()
                if second_interruption
                else final_state.interruption_payload
            ) or {}
            # The original checkpoint stays OPEN when the resume re-pauses, so
            # surface its id/version to let clients retry from the pause dialog.
            remaining_details.setdefault("checkpoint_id", chk.checkpoint_id)
            remaining_details.setdefault("checkpoint_version", chk.checkpoint_version)

            # Keep session paused
            sim_session["hitl_interrupted"] = True
            sim_session["hitl_reason"] = final_state.hitl_reason
            sim_session["hitl_telemetry_snapshot"] = final_state.hitl_telemetry_snapshot

            response = {
                "simulation_id": simulation_id,
                "checkpoint_id": chk.checkpoint_id,
                "resumed_invocation_id": invocation_id,
                "resume_status": status,
                "current_workflow_state": final_state.model_dump(),
                "telemetry": {
                    "current_position": final_state.current_position,
                    "intent_vector": final_state.intent_vector.model_dump(),
                    "resultant_vector": final_state.resultant_vector.model_dump(),
                    "actual_burn_rate": final_state.actual_burn_rate,
                    "angular_drift_delta": final_state.angular_drift_delta,
                },
                "active_contract_version": active_contract_version,
                "remaining_interruption_details": remaining_details,
                "correlation_id": trace_id,
            }
        else:
            # Resume succeeded! Mark checkpoint RESOLVED and clear session pause state
            status = "RUNNING"
            checkpoint_service.mark_resolved(
                checkpoint_id=chk.checkpoint_id,
                expected_version=chk.checkpoint_version,
                resolution_details=payload.resolution_action
            )

            sim_session["hitl_interrupted"] = False
            sim_session["hitl_reason"] = ""
            sim_session["hitl_telemetry_snapshot"] = None
            sim_session.pop("paused_invocation_id", None)
            sim_session["current_position"] = final_state.current_position
            sim_session["accumulated_burn"] = final_state.accumulated_burn

            response = {
                "simulation_id": simulation_id,
                "checkpoint_id": chk.checkpoint_id,
                "resumed_invocation_id": invocation_id,
                "resume_status": status,
                "current_workflow_state": final_state.model_dump(),
                "telemetry": {
                    "current_position": final_state.current_position,
                    "intent_vector": final_state.intent_vector.model_dump(),
                    "resultant_vector": final_state.resultant_vector.model_dump(),
                    "actual_burn_rate": final_state.actual_burn_rate,
                    "angular_drift_delta": final_state.angular_drift_delta,
                },
                "active_contract_version": active_contract_version,
                "remaining_interruption_details": None,
                "correlation_id": trace_id,
            }

        # Cache response for idempotency
        with self._lock:
            self._processed_resumes[request_id] = response.copy()

        return response


# Global singleton instance
resume_service = ResumeService()
