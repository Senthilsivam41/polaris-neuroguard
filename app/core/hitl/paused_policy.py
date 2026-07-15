"""HITL Paused-Session Policy Module (HITL-004).

Enforces authoritative paused-session state guardrails. Blocks normal decision
evaluation requests when an active interruption or checkpoint exists, returning
HTTP 409 SIMULATION_PAUSED without state mutation.
"""

from typing import Dict, Any
from fastapi import HTTPException
from app.core.hitl.checkpoint_service import checkpoint_service


class SimulationPausedError(HTTPException):
    """Structured HTTP 409 exception raised when attempting to evaluate decisions on a paused session."""

    def __init__(self, simulation_id: str, checkpoint_id: str, interruption_payload: Any, checkpoint_version: int):
        payload_dict = (
            interruption_payload.model_dump()
            if hasattr(interruption_payload, "model_dump")
            else dict(interruption_payload)
        )
        reason_val = (
            payload_dict["reason"].value
            if hasattr(payload_dict["reason"], "value")
            else str(payload_dict["reason"])
        )

        detail = {
            "error_code": "SIMULATION_PAUSED",
            "message": f"Simulation session '{simulation_id}' is currently paused. Resolve the blocking condition and call the resume endpoint.",
            "simulation_id": simulation_id,
            "interruption_id": payload_dict.get("interruption_id", ""),
            "active_checkpoint_id": checkpoint_id,
            "checkpoint_version": checkpoint_version,
            "reason": reason_val,
            "explanation": payload_dict.get("explanation", ""),
            "required_resolution_action": payload_dict.get("required_resolution_action", ""),
            "resume_endpoint": f"/api/v1/simulation/{simulation_id}/resume"
        }
        super().__init__(status_code=409, detail=detail)


def enforce_paused_session_policy(simulation_id: str, session: Dict[str, Any]) -> None:
    """Check if simulation is paused. If so, raise SimulationPausedError (HTTP 409)."""
    active_chk = checkpoint_service.get_active_checkpoint(simulation_id)
    if active_chk:
        raise SimulationPausedError(
            simulation_id=simulation_id,
            checkpoint_id=active_chk.checkpoint_id,
            interruption_payload=active_chk.interruption_payload,
            checkpoint_version=active_chk.checkpoint_version
        )

    if session.get("hitl_interrupted"):
        # Fallback if session has hitl_interrupted flag set directly
        active_chk_id = session.get("active_checkpoint_id", "")
        chk_version = session.get("active_checkpoint_version", 1)
        hitl_reason = session.get("hitl_reason", "Workflow paused by guardrail.")
        fallback_payload = {
            "interruption_id": session.get("paused_interruption_id", "int-unknown"),
            "reason": "STATIC_CONSTRAINT_DEADLOCK",
            "explanation": hitl_reason,
            "required_resolution_action": "Resolve blocking condition before resuming."
        }
        raise SimulationPausedError(
            simulation_id=simulation_id,
            checkpoint_id=active_chk_id,
            interruption_payload=fallback_payload,
            checkpoint_version=chk_version
        )
