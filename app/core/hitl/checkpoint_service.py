"""HITL Checkpoint Service & Persistence Module (HITL-002).

Provides thread-safe atomic checkpoint repository and service, ensuring
single active checkpoint per simulation, optimistic concurrency control,
and auditable checkpoint history.
"""

import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from app.core.hitl.checkpoint import (
    WorkflowCheckpoint,
    sanitize_and_fingerprint_state,
)
from app.core.hitl.interruption import InterruptionPayload


class CheckpointServiceError(ValueError):
    """Base exception for Checkpoint Service operations."""
    pass


class CheckpointNotFoundError(CheckpointServiceError):
    """Raised when requested checkpoint ID is missing."""
    pass


class CheckpointVersionConflictError(CheckpointServiceError):
    """Raised when expected checkpoint version does not match active version (optimistic locking error)."""
    pass


class CheckpointCorruptError(CheckpointServiceError):
    """Raised when checkpoint state serialization or schema validation fails."""
    pass


class CheckpointExpiredError(CheckpointServiceError):
    """Raised when attempting an operation on an expired, cancelled, or superseded checkpoint."""
    pass


class CheckpointService:
    """Thread-safe in-memory repository for storing and managing workflow interruption checkpoints."""

    def __init__(self):
        self._checkpoints: Dict[str, WorkflowCheckpoint] = {}  # checkpoint_id -> WorkflowCheckpoint
        self._sim_active_map: Dict[str, str] = {}  # simulation_id -> active_checkpoint_id
        self._sim_history: Dict[str, List[str]] = {}  # simulation_id -> list of checkpoint_ids
        self._lock = threading.Lock()

    def clear(self) -> None:
        """Clear all stored checkpoints (used for test isolation)."""
        with self._lock:
            self._checkpoints.clear()
            self._sim_active_map.clear()
            self._sim_history.clear()

    def create_checkpoint(
        self,
        simulation_id: str,
        invocation_id: str,
        node_position: str,
        state_dict: Dict[str, Any],
        interruption_payload: InterruptionPayload,
        active_contract_id: Optional[str] = None,
        active_contract_version: Optional[int] = None,
        change_request_id: Optional[str] = None,
        amendment_id: Optional[str] = None,
        completed_nodes: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> WorkflowCheckpoint:
        """Atomically create a new active checkpoint, invalidating any prior active checkpoint for the simulation."""
        try:
            clean_state, fingerprint = sanitize_and_fingerprint_state(state_dict)
        except Exception as e:
            raise CheckpointCorruptError(f"Checkpoint state validation failed: {str(e)}") from e

        now_str = datetime.now(timezone.utc).isoformat()

        checkpoint = WorkflowCheckpoint(
            simulation_id=simulation_id,
            invocation_id=invocation_id,
            node_position=node_position,
            validated_state=clean_state,
            state_fingerprint=fingerprint,
            interruption_payload=interruption_payload,
            active_contract_id=active_contract_id,
            active_contract_version=active_contract_version,
            change_request_id=change_request_id,
            amendment_id=amendment_id,
            created_at=now_str,
            updated_at=now_str,
            checkpoint_status="ACTIVE",
            resume_attempt_count=0,
            idempotency_key=idempotency_key,
            checkpoint_version=1,
            completed_nodes=completed_nodes or {}
        )

        with self._lock:
            # Enforce single active checkpoint rule per simulation
            if simulation_id in self._sim_active_map:
                prior_active_id = self._sim_active_map[simulation_id]
                if prior_active_id in self._checkpoints:
                    prior_chk = self._checkpoints[prior_active_id]
                    if prior_chk.checkpoint_status == "ACTIVE":
                        prior_chk.checkpoint_status = "SUPERSEDED"
                        prior_chk.updated_at = now_str

            self._checkpoints[checkpoint.checkpoint_id] = checkpoint
            self._sim_active_map[simulation_id] = checkpoint.checkpoint_id
            self._sim_history.setdefault(simulation_id, []).append(checkpoint.checkpoint_id)

        return checkpoint

    def get_active_checkpoint(self, simulation_id: str) -> Optional[WorkflowCheckpoint]:
        """Retrieve the currently active checkpoint for a simulation, if any."""
        with self._lock:
            active_id = self._sim_active_map.get(simulation_id)
            if not active_id or active_id not in self._checkpoints:
                return None
            chk = self._checkpoints[active_id]
            if chk.checkpoint_status != "ACTIVE":
                return None
            return chk.model_copy()

    def get_by_id(self, checkpoint_id: str) -> WorkflowCheckpoint:
        """Retrieve a checkpoint by its unique ID."""
        with self._lock:
            if checkpoint_id not in self._checkpoints:
                raise CheckpointNotFoundError(f"Checkpoint '{checkpoint_id}' not found.")
            return self._checkpoints[checkpoint_id].model_copy()

    def mark_resolved(
        self,
        checkpoint_id: str,
        expected_version: int,
        resolution_details: str = ""
    ) -> WorkflowCheckpoint:
        """Atomically mark a checkpoint as RESOLVED using optimistic concurrency check."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if checkpoint_id not in self._checkpoints:
                raise CheckpointNotFoundError(f"Checkpoint '{checkpoint_id}' not found.")
            chk = self._checkpoints[checkpoint_id]

            if chk.checkpoint_version != expected_version:
                raise CheckpointVersionConflictError(
                    f"Optimistic lock conflict: Expected version {expected_version}, but current version is {chk.checkpoint_version}."
                )

            if chk.checkpoint_status in ["EXPIRED", "CANCELLED", "SUPERSEDED"]:
                raise CheckpointExpiredError(f"Cannot resolve checkpoint '{checkpoint_id}' with status {chk.checkpoint_status}.")

            chk.checkpoint_status = "RESOLVED"
            chk.checkpoint_version += 1
            chk.updated_at = now_str

            # Clear active mapping if this was active
            sim_id = chk.simulation_id
            if self._sim_active_map.get(sim_id) == checkpoint_id:
                del self._sim_active_map[sim_id]

            return chk.model_copy()

    def mark_expired_or_cancelled(
        self,
        checkpoint_id: str,
        status: str = "CANCELLED"
    ) -> WorkflowCheckpoint:
        """Mark a checkpoint as EXPIRED or CANCELLED."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if checkpoint_id not in self._checkpoints:
                raise CheckpointNotFoundError(f"Checkpoint '{checkpoint_id}' not found.")
            chk = self._checkpoints[checkpoint_id]

            chk.checkpoint_status = status
            chk.checkpoint_version += 1
            chk.updated_at = now_str

            sim_id = chk.simulation_id
            if self._sim_active_map.get(sim_id) == checkpoint_id:
                del self._sim_active_map[sim_id]

            return chk.model_copy()

    def get_checkpoint_history(self, simulation_id: str) -> List[WorkflowCheckpoint]:
        """Retrieve full auditable checkpoint history for a simulation session."""
        with self._lock:
            chk_ids = self._sim_history.get(simulation_id, [])
            return [self._checkpoints[cid].model_copy() for cid in chk_ids if cid in self._checkpoints]


# Global singleton instance
checkpoint_service = CheckpointService()
