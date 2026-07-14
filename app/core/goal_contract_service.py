"""Goal Contract Versioning Service Module (DRIFT-002).

Provides an immutable, thread-safe GoalContractRepository that maintains the lifecycle of baseline contracts
and sequential, append-only contract amendments.
"""

import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from app.core.goal_contract import GoalContract


# Structured Exception Hierarchy
class GoalContractError(ValueError):
    """Base exception for Goal Contract operations."""
    pass


class ContractNotFoundError(GoalContractError):
    """Raised when a specified contract ID does not exist."""
    pass


class ContractVersionNotFoundError(GoalContractError):
    """Raised when a specific contract version number does not exist."""
    pass


class StaleVersionError(GoalContractError):
    """Raised when attempting an amendment against a stale contract version."""
    def __init__(self, message: str, current_version: int, expected_version: int, contract_id: str):
        super().__init__(message)
        self.current_version = current_version
        self.expected_version = expected_version
        self.contract_id = contract_id


class VersionConflictError(GoalContractError):
    """Raised when version sequencing is non-sequential or duplicate."""
    pass


class ImmutableContractError(GoalContractError):
    """Raised when an attempt is made to overwrite or modify a persisted contract in place."""
    pass


class ContractAmendmentMetadata(BaseModel):
    """Metadata model capturing approval details and audit lineage for a contract amendment."""
    amendment_id: str = Field(..., description="Unique amendment audit identifier.")
    actor_id: str = Field(..., description="User/Actor identifier performing or authorizing the amendment.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timezone-aware UTC timestamp of amendment approval."
    )
    reason: str = Field(..., description="Justification or change intent description.")
    source_request_id: str = Field(..., description="Natural-language change request ID triggering this amendment.")
    previous_version: int = Field(..., ge=1, description="Expected parent version being amended.")
    new_version: int = Field(..., ge=2, description="Target version created by this amendment.")
    content_fingerprint: str = Field(default="", description="Content fingerprint of the resulting contract version.")


class GoalContractRepository:
    """
    In-memory thread-safe repository for immutable Goal Contract baseline creation and amendment versioning.
    Guarantees baseline immutability, sequential version progression, and version conflict detection.
    """
    def __init__(self):
        # Storage layout: contract_id -> { version_number -> GoalContract }
        self._contracts: Dict[str, Dict[int, GoalContract]] = {}
        # Amendment audit log layout: contract_id -> List[ContractAmendmentMetadata]
        self._amendments: Dict[str, List[ContractAmendmentMetadata]] = {}
        self._lock = threading.Lock()

    def clear(self) -> None:
        """Clear all in-memory contracts and amendment logs (for test isolation)."""
        with self._lock:
            self._contracts.clear()
            self._amendments.clear()

    def create_baseline_contract(self, contract: GoalContract) -> GoalContract:
        """
        Persists an initial immutable Goal Contract (version 1).
        
        Raises:
            VersionConflictError: If version is not 1 or if contract_id already exists.
        """
        with self._lock:
            if contract.contract_version != 1:
                raise VersionConflictError(
                    f"Baseline contract must have contract_version = 1, got {contract.contract_version}."
                )
            if contract.contract_id in self._contracts:
                raise VersionConflictError(
                    f"Contract baseline already exists for contract_id: {contract.contract_id}."
                )
            
            # Enforce calculations and create frozen representation
            contract_dict = contract.model_dump()
            stored_contract = GoalContract.model_validate(contract_dict)
            
            self._contracts[contract.contract_id] = {1: stored_contract}
            self._amendments[contract.contract_id] = []
            return stored_contract.model_copy(deep=True)

    def get_contract_version(self, contract_id: str, version: int) -> GoalContract:
        """
        Retrieves a specific version of a Goal Contract.
        
        Raises:
            ContractNotFoundError: If contract_id is missing.
            ContractVersionNotFoundError: If specified version number is missing.
        """
        with self._lock:
            if contract_id not in self._contracts:
                raise ContractNotFoundError(f"Contract {contract_id} not found.")
            
            versions = self._contracts[contract_id]
            if version not in versions:
                raise ContractVersionNotFoundError(
                    f"Version {version} not found for contract {contract_id}."
                )
            return versions[version].model_copy(deep=True)

    def get_latest_contract(self, contract_id: str) -> GoalContract:
        """
        Retrieves the current active (highest version number) Goal Contract.
        
        Raises:
            ContractNotFoundError: If contract_id is missing.
        """
        with self._lock:
            if contract_id not in self._contracts:
                raise ContractNotFoundError(f"Contract {contract_id} not found.")
            
            versions = self._contracts[contract_id]
            latest_version = max(versions.keys())
            return versions[latest_version].model_copy(deep=True)

    def list_version_history(self, contract_id: str) -> List[GoalContract]:
        """
        Retrieves complete chronological version history for a contract sorted by version ascending.
        
        Raises:
            ContractNotFoundError: If contract_id is missing.
        """
        with self._lock:
            if contract_id not in self._contracts:
                raise ContractNotFoundError(f"Contract {contract_id} not found.")
            
            versions = self._contracts[contract_id]
            sorted_keys = sorted(versions.keys())
            return [versions[v].model_copy(deep=True) for v in sorted_keys]

    def create_amendment_version(
        self,
        contract_id: str,
        amendment_metadata: ContractAmendmentMetadata,
        new_contract_fields: Dict[str, Any]
    ) -> GoalContract:
        """
        Creates and stores a new version of an existing contract derived from an approved amendment.
        
        Guarantees:
        - Prevents in-place mutation of existing saved versions.
        - Requires previous_version to match current active latest version.
        - Requires new_version to equal previous_version + 1.
        
        Raises:
            ContractNotFoundError: If contract_id does not exist.
            StaleVersionError: If previous_version is not the current active version.
            VersionConflictError: If version progression is non-sequential.
        """
        with self._lock:
            if contract_id not in self._contracts:
                raise ContractNotFoundError(f"Contract {contract_id} not found.")
            
            versions = self._contracts[contract_id]
            latest_version_num = max(versions.keys())
            current_active = versions[latest_version_num]

            # Stale / version alignment checks
            if amendment_metadata.previous_version != latest_version_num:
                raise StaleVersionError(
                    f"Expected version {amendment_metadata.previous_version} is stale. Current active version is {latest_version_num}.",
                    current_version=latest_version_num,
                    expected_version=amendment_metadata.previous_version,
                    contract_id=contract_id
                )

            expected_new = latest_version_num + 1
            if amendment_metadata.new_version != expected_new:
                raise VersionConflictError(
                    f"New version {amendment_metadata.new_version} must equal next sequential version {expected_new}."
                )

            if expected_new in versions:
                raise VersionConflictError(
                    f"Version {expected_new} already exists for contract {contract_id}."
                )

            # Build base from current active version dict
            base_data = current_active.model_dump()
            
            # Apply new fields over base_data
            base_data.update(new_contract_fields)
            
            # Enforce versioning lineage metadata
            base_data["contract_id"] = contract_id
            base_data["contract_version"] = expected_new
            base_data["parent_version_id"] = contract_id
            base_data["parent_contract_version"] = latest_version_num
            base_data["creation_timestamp"] = amendment_metadata.timestamp
            base_data["creator_id"] = amendment_metadata.actor_id
            # Reset fingerprint so it re-computes for new content
            base_data["content_fingerprint"] = ""

            new_contract = GoalContract.model_validate(base_data)
            
            # Update amendment metadata fingerprint
            amendment_copy = amendment_metadata.model_copy()
            amendment_copy.content_fingerprint = new_contract.content_fingerprint

            # Persist immutably
            self._contracts[contract_id][expected_new] = new_contract
            self._amendments[contract_id].append(amendment_copy)

            return new_contract.model_copy(deep=True)


# Global singleton instance for app repository persistence
goal_contract_repo = GoalContractRepository()
