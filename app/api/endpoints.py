import uuid
import threading
import asyncio
import time
from enum import Enum
from typing import Dict, Any, List, Tuple, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.core.simulation import execute_turn, Vector2D, EnvironmentStorm, PRESET_STORMS, Iceberg
from app.core.config import BASE_BURN_RATE, AUTH_REQUIRED
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.sessions.session import Session as AdkSession
from google.genai import types
from datetime import datetime, timezone
from pydantic import field_validator
from app.core.nodes import simulation_workflow
from app.core.state import SimulationStateSchema, get_typed_state, update_typed_state, validate_state_transition
from app.core.goal_contract import GoalContract, OutcomeCategorization
from app.core.goal_contract_service import (
    goal_contract_repo,
    ContractNotFoundError,
    StaleVersionError,
)
from app.core.hitl.paused_policy import enforce_paused_session_policy
from app.core.hitl.resume_service import resume_service, ResumeRequestPayload
from app.core.hitl.checkpoint_service import checkpoint_service
from app.core.hitl.interruption import InterruptionPayload, InterruptionReason
from app.core.persistence import (
    workflow_store,
    VersionConflictError,
    IdempotencyConflictError,
)
from app.core.security import Principal, audit_event, current_principal, enforce_owner
from app.core.observability import metrics

router = APIRouter()

session_service = InMemorySessionService()
runner = Runner(
    app_name="polaris-neuroguard",
    node=simulation_workflow,
    session_service=session_service
)

# 1. Enums and Pydantic Schemas for Registration
class RiskTolerance(str, Enum):
    CONSERVATIVE = "Conservative"
    BALANCED = "Balanced"
    AGGRESSIVE = "Aggressive"

class AnchorGoal(BaseModel):
    title: str = Field(
        ..., 
        description="The title of the strategic goal",
        examples=["Migrate Core Infrastructure"]
    )
    target_timeline_months: int = Field(
        ..., 
        description="Target timeline in months", 
        gt=0,
        examples=[18]
    )
    budget_limit_usd: float = Field(
        ..., 
        description="Strategic budget limit in USD", 
        gt=0.0,
        examples=[5000000.0]
    )
    reliability_target_sla: float = Field(
        ..., 
        description="Target reliability SLA (0.0 to 100.0)", 
        ge=0.0, 
        le=100.0,
        examples=[99.95]
    )

class UserProfile(BaseModel):
    user_id: str = Field(
        ..., 
        description="The unique ID of the user",
        examples=["user_123"]
    )
    role: str = Field(
        ..., 
        description="The role of the user",
        examples=["Chief Technology Officer"]
    )
    company_scale: str = Field(
        ..., 
        description="The scale of the company",
        examples=["Enterprise"]
    )
    industry: str = Field(
        ..., 
        description="The industry of the company",
        examples=["Maritime Logistics"]
    )
    anchor_goal: AnchorGoal = Field(..., description="The registered anchor goal")
    risk_tolerance: RiskTolerance = Field(
        ..., 
        description="Risk tolerance setting",
        examples=["Balanced"]
    )


# 2. Schemas for Decision Evaluation
class Vector2DModel(BaseModel):
    magnitude: float = Field(..., ge=0.0, le=100000.0, description="Speed or magnitude of the vector", examples=[10.0])
    heading_degrees: float = Field(..., ge=0.0, lt=360.0, description="Direction in degrees from positive Y-axis (0-360°)", examples=[0.0])

class IcebergModel(BaseModel):
    name: str = Field(..., description="The name of the iceberg constraint", examples=["Custom Budget Freeze"])
    x: float = Field(..., description="X coordinate of the iceberg center", examples=[-100.0])
    y: float = Field(..., description="Y coordinate of the iceberg center", examples=[400.0])
    radius: float = Field(100.0, gt=0.0, le=100000.0, description="The safety boundary radius around the iceberg", examples=[100.0])

class EvaluateDecisionRequest(BaseModel):
    simulation_id: str = Field(
        ..., 
        description="The unique simulation session ID returned on registration",
        examples=["64afce2a-7f67-4307-9b63-4a5491966940"]
    )
    intent_vector: Vector2DModel = Field(..., description="The User's intentional velocity and direction")
    declared_constraints: List[str] = Field(
        default_factory=list, 
        max_length=50,
        description="Active constraints declared by the user",
        examples=[["RIGID_TIMELINE", "FREEZE_HEADCOUNT"]]
    )
    active_storms: List[str] = Field(
        default_factory=list, 
        max_length=20,
        description="Names of active environmental storms (e.g. 'Category 4 Cyclone')",
        examples=[["Category 4 Cyclone"]]
    )
    custom_icebergs: Optional[List[IcebergModel]] = Field(None, max_length=20, description="Optional custom icebergs to inject")
    custom_opposing_pairs: Optional[List[Tuple[str, str]]] = Field(None, description="Optional custom opposing constraint pairs to evaluate")
    request_id: Optional[str] = Field(None, description="Optional idempotency key for this evaluation")

class ResumeSimulationRequest(BaseModel):
    checkpoint_id: str = Field(..., description="Target active checkpoint ID to resume from")
    resume_request_id: str = Field(..., description="Unique request ID / idempotency key")
    actor_id: str = Field(..., description="Actor/User ID attempting the resume")
    resolution_action: str = Field(..., description="Resolution action description")
    approval_decision_id: Optional[str] = Field(default=None, description="Optional approval or amendment decision ID")
    amendment_id: Optional[str] = Field(default=None, description="Optional amendment ID")
    expected_checkpoint_version: int = Field(..., ge=1, description="Expected checkpoint version number for optimistic locking")
    intent_vector: Optional[Vector2DModel] = Field(None, description="Optional intent vector override")
    declared_constraints: Optional[List[str]] = Field(None, description="Optional updated declared constraints")

class ResumeSimulationResponse(BaseModel):
    simulation_id: str = Field(..., description="The simulation session ID")
    checkpoint_id: str = Field(..., description="The checkpoint ID resolved/resumed")
    resumed_invocation_id: str = Field(..., description="The ADK workflow invocation ID resumed")
    resume_status: str = Field(..., description="Resume status (RUNNING, PAUSED_BY_GUARDRAIL)")
    current_workflow_state: Dict[str, Any] = Field(..., description="Full workflow state after resume execution")
    telemetry: TelemetryModel = Field(..., description="Updated telemetry details")
    active_contract_version: int = Field(..., description="Active Goal Contract version number")
    remaining_interruption_details: Optional[Dict[str, Any]] = Field(None, description="Details if workflow encountered another blocking condition")
    correlation_id: str = Field(..., description="Correlation / trace ID for tracking")

class TelemetryModel(BaseModel):
    current_position: Dict[str, float] = Field(..., description="New position coordinates (x, y)")
    intent_vector: Vector2DModel = Field(..., description="User intentional vector")
    resultant_vector: Vector2DModel = Field(..., description="Resultant velocity vector after storms and deadlocks")
    actual_burn_rate: float = Field(..., description="Burn-rate cost for this turn")
    angular_drift_delta: float = Field(..., description="Angular difference between intent and reality in degrees")

class HITLInterceptionData(BaseModel):
    requires_intervention: bool = Field(..., description="Flags if Human-in-the-Loop intervention is required")
    reason: str = Field(..., description="Reason detail for the required intervention")
    telemetry_snapshot: Dict[str, Any] = Field(..., description="Diagnostic snapshot of the failure state")

class EvaluateDecisionResponse(BaseModel):
    simulation_id: str = Field(..., description="The simulation session ID")
    telemetry: TelemetryModel = Field(..., description="Telemetry details of this step")
    drift_warning: bool = Field(..., description="Drift flag warning (True if angular drift > 15°)")
    deadlocks: List[Tuple[str, str]] = Field(..., description="List of active logical deadlock pairs")
    collision_threats: List[str] = Field(..., description="List of threatened iceberg names")
    hitl_interception_data: Optional[HITLInterceptionData] = Field(None, description="Interception block if threats or deadlocks are present")
    status: str = Field("RUNNING", description="Simulation run status (RUNNING, PAUSED_BY_GUARDRAIL)")
    active_constraints: List[str] = Field(default_factory=list, description="Active constraint flags (e.g. ENGINE_STALL, BUDGET_OVERRUN)")

class HistoryStepLog(BaseModel):
    turn_number: int = Field(..., description="1-indexed turn number", examples=[1])
    telemetry_snapshot: TelemetryModel = Field(..., description="Telemetry snapshot at the end of the turn")
    active_storms: List[str] = Field(..., description="List of active storms in this turn", examples=[["Category 4 Cyclone"]])
    applied_decision: Dict[str, Any] = Field(..., description="User decision applied in this turn")
    fracture_events: Dict[str, Any] = Field(..., description="Active constraints, deadlocks, and collisions")

class SimulationHistoryResponse(BaseModel):
    simulation_id: str = Field(..., description="The simulation session ID")
    total_turns_executed: int = Field(..., description="Total turns executed in this simulation")
    history: List[HistoryStepLog] = Field(..., description="List of step logs")

class StormType(str, Enum):
    GEOPOLITICAL = "Geopolitical"
    METEOROLOGICAL = "Meteorological"
    ECONOMIC = "Economic"

class InjectStormRequest(BaseModel):
    storm_type: StormType = Field(..., description="The type classification of the storm")
    name: str = Field(..., description="The unique identifier name of the storm", examples=["Custom Solar Flare"])
    magnitude: float = Field(..., description="The magnitude/force speed of the storm vector", ge=0.0, examples=[8.0])
    heading_degrees: float = Field(
        ..., 
        description="The heading direction of the storm vector in degrees (0 to 360)", 
        ge=0.0, 
        le=360.0,
        examples=[180.0]
    )

class StatusResponse(BaseModel):
    status: str = Field(..., description="API router status state", examples=["ready"])

class RegisterSimulationResponse(BaseModel):
    simulation_id: str = Field(..., description="The generated simulation session ID")
    quantum_mountain_coordinates: Dict[str, float] = Field(..., description="Locked-in Quantum Mountain coordinates")
    user_profile: UserProfile = Field(..., description="The registered user profile details")
    active_contract_id: Optional[str] = Field(default=None, description="Active Goal Contract unique ID")
    active_contract_version: Optional[int] = Field(default=None, description="Active Goal Contract version number")

class ChangeRequestPayload(BaseModel):
    simulation_id: str = Field(..., description="Target simulation session ID.")
    request_id: str = Field(..., description="Unique request ID / idempotency key.")
    natural_language_request: str = Field(..., description="Raw text of natural-language change request.")
    expected_goal_contract_version: int = Field(..., ge=1, description="Expected active contract version.")
    explicit_change_intent: Optional[str] = Field(default=None, description="Optional explicit change intent description.")
    actor_id: Optional[str] = Field(default=None, description="Actor/User ID submitting the change request.")

    @field_validator("natural_language_request")
    @classmethod
    def validate_request_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("natural_language_request must be non-empty.")
        return v.strip()

class ChangeRequestResponse(BaseModel):
    request_id: str = Field(..., description="Request ID / idempotency key.")
    contract_id: str = Field(..., description="Target Goal Contract ID.")
    active_contract_version: int = Field(..., description="Active contract version number.")
    idempotency_result: str = Field(..., description="'accepted' for initial submit, 'idempotent_replay' for duplicates.")
    request_acceptance_status: str = Field(default="RECEIVED", description="Processing status of the change request.")
    classification_status: str = Field(default="PENDING_DRIFT_ANALYSIS", description="Initial classification status.")
    trace_id: str = Field(..., description="Correlation / trace ID for downstream processing.")

class InjectStormResponse(BaseModel):
    status: str = Field(..., description="Status of the injection request", examples=["success"])
    injected_storm: InjectStormRequest = Field(..., description="The injected storm details")
    active_custom_storms: List[str] = Field(..., description="List of all currently registered custom storm names")


# 3. Durable Session Store (SQLite); cache is retained only for legacy callers/tests.
sessions: Dict[str, Dict[str, Any]] = {}
sessions_lock = threading.Lock()


def _load_session(simulation_id: str) -> Tuple[Dict[str, Any], int]:
    """Read the durable session; retain the legacy cache only for test compatibility."""
    stored = workflow_store.get_session(simulation_id)
    if stored is None:
        # Existing callers/tests may seed the legacy mapping directly.
        with sessions_lock:
            legacy = sessions.get(simulation_id)
        if legacy is None:
            raise HTTPException(status_code=404, detail="Simulation session not found.")
        try:
            version = workflow_store.create_session(simulation_id, legacy)
        except Exception:
            stored = workflow_store.get_session(simulation_id)
            if stored is None:
                raise
            return stored
        return legacy.copy(), version
    return stored


def _save_session(simulation_id: str, session: Dict[str, Any], version: int) -> int:
    try:
        next_version = workflow_store.save_session(simulation_id, session, version)
    except VersionConflictError as exc:
        raise HTTPException(status_code=409, detail={"error_code": "SESSION_VERSION_CONFLICT", "message": str(exc)}) from exc
    with sessions_lock:
        sessions[simulation_id] = session
    return next_version


@router.get(
    "/status", 
    response_model=StatusResponse, 
    summary="Get API router status"
)
def get_status():
    """Returns the initialization status of the simulation API router."""
    return {"status": "ready"}


@router.post(
    "/simulation/register", 
    response_model=RegisterSimulationResponse, 
    summary="Register new user profile and initialize simulation"
)
def register_simulation(profile: UserProfile, principal: Principal = Depends(current_principal)):
    """Registers a user profile containing role, scale, industry, anchor goals, and risk tolerance.
    Initializes simulation coordinates at (0,0) with destination targets set and baseline GoalContract (v1).
    """
    if AUTH_REQUIRED and principal.actor_id != profile.user_id and not principal.roles.intersection({"admin", "override"}):
        raise HTTPException(status_code=403, detail={"error_code": "PROFILE_OWNERSHIP_REQUIRED"})
    sim_id = str(uuid.uuid4())
    contract_id = f"contract-{sim_id}"
    
    anchor = profile.anchor_goal
    baseline_contract = GoalContract(
        contract_id=contract_id,
        contract_version=1,
        original_request_text=f"Initial registration for anchor goal: {anchor.title}",
        normalized_objective=anchor.title,
        deliverables=[anchor.title],
        in_scope_items=[anchor.title],
        outcomes=OutcomeCategorization(
            required_outcomes=[anchor.title],
            optional_outcomes=[],
            excluded_outcomes=[]
        ),
        budget_limit_usd=anchor.budget_limit_usd,
        target_timeline_months=anchor.target_timeline_months,
        reliability_target_sla=anchor.reliability_target_sla,
        risk_tolerance=profile.risk_tolerance,
        creator_id=profile.user_id,
        acceptance_criteria=[f"Achieve {anchor.title} within SLA {anchor.reliability_target_sla}%"]
    )
    saved_contract = goal_contract_repo.create_baseline_contract(baseline_contract)

    session_data = {
        "profile": profile.model_dump(),
        "destination": {"x": 0.0, "y": 1000.0},
        "current_position": {"x": 0.0, "y": 0.0},
        "accumulated_burn": 0.0,
        "active_storms": {},
        "custom_storms": {},
        "history": [],
        "active_contract_id": saved_contract.contract_id,
        "active_contract_version": saved_contract.contract_version,
        "active_contract_fingerprint": saved_contract.content_fingerprint,
        "change_requests": {}
    }
    workflow_store.create_session(sim_id, session_data)
    with sessions_lock:
        sessions[sim_id] = session_data
    audit_event("simulation_registered", actor_id=principal.actor_id, simulation_id=sim_id,
                details={"goal_hash": saved_contract.content_fingerprint, "contract_version": 1})
        
    return {
        "simulation_id": sim_id,
        "quantum_mountain_coordinates": {"x": 0.0, "y": 1000.0},
        "user_profile": profile,
        "active_contract_id": saved_contract.contract_id,
        "active_contract_version": saved_contract.contract_version
    }


@router.post(
    "/simulation/change-requests",
    response_model=ChangeRequestResponse,
    summary="Submit a natural-language change request for goal drift analysis (DRIFT-003)"
)
def submit_change_request(payload: ChangeRequestPayload, principal: Principal = Depends(current_principal)):
    """Submits a natural-language change request referencing the expected active goal-contract version.
    Verifies actor ownership and contract version alignment. Stores the request without mutating the active Goal Contract.
    """
    sim_id = payload.simulation_id
    
    session, session_version = _load_session(sim_id)
        
    profile = session.get("profile", {})
    owner_id = profile.get("user_id", "")
    enforce_owner(principal, owner_id)
    
    # Ownership authorization check
    if payload.actor_id and owner_id and payload.actor_id != owner_id:
        raise HTTPException(
            status_code=403,
            detail=f"Actor ID '{payload.actor_id}' does not match simulation owner '{owner_id}'."
        )

    # Idempotency check
    change_requests = session.setdefault("change_requests", {})
    if payload.request_id in change_requests:
        prior_record = change_requests[payload.request_id]
        replay_resp = prior_record["response"].copy()
        replay_resp["idempotency_result"] = "idempotent_replay"
        return replay_resp

    contract_id = session.get("active_contract_id", f"contract-{sim_id}")
    
    try:
        active_contract = goal_contract_repo.get_latest_contract(contract_id)
    except ContractNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Goal Contract '{contract_id}' not found for simulation '{sim_id}'."
        )

    # Version check (STALE Expected Version -> 409 Conflict)
    if payload.expected_goal_contract_version != active_contract.contract_version:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "STALE_GOAL_CONTRACT_VERSION",
                "message": f"Expected goal contract version {payload.expected_goal_contract_version} is stale. Current active version is {active_contract.contract_version}.",
                "contract_id": contract_id,
                "current_version": active_contract.contract_version,
                "expected_version": payload.expected_goal_contract_version,
            }
        )

    trace_id = str(uuid.uuid4())
    received_at = datetime.now(timezone.utc).isoformat()

    response_data = {
        "request_id": payload.request_id,
        "contract_id": contract_id,
        "active_contract_version": active_contract.contract_version,
        "idempotency_result": "accepted",
        "request_acceptance_status": "RECEIVED",
        "classification_status": "PENDING_DRIFT_ANALYSIS",
        "trace_id": trace_id,
    }

    # Store request record without mutating the goal contract
    change_requests[payload.request_id] = {
        "request_id": payload.request_id,
        "raw_text": payload.natural_language_request,
        "expected_version": payload.expected_goal_contract_version,
        "resolved_active_version": active_contract.contract_version,
        "explicit_change_intent": payload.explicit_change_intent,
        "actor": payload.actor_id or owner_id,
        "received_timestamp": received_at,
        "response": response_data
    }
    _save_session(sim_id, session, session_version)
    audit_event("change_request_submitted", actor_id=principal.actor_id, request_id=payload.request_id,
                simulation_id=sim_id, details={"contract_version": active_contract.contract_version})

    return response_data


@router.post(
    "/simulation/evaluate-decision", 
    response_model=EvaluateDecisionResponse,
    summary="Evaluate decision step telemetry, deadlocks, and path collisions"
)
async def evaluate_decision(payload: EvaluateDecisionRequest, principal: Principal = Depends(current_principal)):
    """Executes a single simulation step based on the user's steering intent, active constraints, and storms.
    
    Runs real-time logical deadlock checking and capsule path collision projection. Returns full telemetry
    and registers human-in-the-loop (HITL) alerts if failure thresholds are violated.
    """
    sim_id = payload.simulation_id
    request_id = payload.request_id or str(uuid.uuid4())
    idempotency_payload = payload.model_dump(exclude={"request_id"})
    try:
        replay = workflow_store.reserve_idempotency("evaluate", sim_id, request_id, idempotency_payload)
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail={"error_code": "IDEMPOTENCY_KEY_REUSED", "message": str(exc)}) from exc
    except VersionConflictError as exc:
        raise HTTPException(status_code=409, detail={"error_code": "REQUEST_IN_PROGRESS", "message": str(exc)}) from exc
    if replay is not None:
        return EvaluateDecisionResponse.model_validate(replay)

    session, session_version = _load_session(sim_id)
        
    profile = session["profile"]
    enforce_owner(principal, profile["user_id"])
    known_storms = set(PRESET_STORMS).union(session.get("custom_storms", {}))
    unknown_storms = sorted(set(payload.active_storms).difference(known_storms))
    if unknown_storms:
        raise HTTPException(status_code=422, detail={"error_code": "UNKNOWN_STORM", "storms": unknown_storms})
    budget_limit = profile.get("anchor_goal", {}).get("budget_limit_usd", float("inf"))
    
    # Enforce authoritative paused session policy (raises HTTP 409 SIMULATION_PAUSED)
    enforce_paused_session_policy(sim_id, session)


    # 1. Retrieve or create the ADK Session
    adk_session = runner.session_service.get_session_sync(
        app_name="polaris-neuroguard",
        user_id=profile["user_id"],
        session_id=sim_id
    )
    if adk_session is None:
        adk_session = runner.session_service.create_session_sync(
            app_name="polaris-neuroguard",
            user_id=profile["user_id"],
            session_id=sim_id
        )
        
    # 2. Populate/initialize state variables using typed schema validation
    init_delta = {
        "simulation_id": sim_id,
        "user_id": profile["user_id"],
        "risk_tolerance": profile["risk_tolerance"],
        "anchor_goal": profile["anchor_goal"],
        "intent_vector": payload.intent_vector.model_dump(),
        "declared_constraints": payload.declared_constraints,
        "active_storms": payload.active_storms,
        "custom_storms": session.get("custom_storms", {}),
        "custom_icebergs": [ib.model_dump() for ib in payload.custom_icebergs] if payload.custom_icebergs else [],
        "current_position": session.get("current_position", {"x": 0.0, "y": 0.0}),
        "accumulated_burn": session.get("accumulated_burn", 0.0),
        "active_deadlocks": [],
        "collision_threats": [],
        "hitl_interrupted": False,
        "hitl_reason": "",
        "hitl_telemetry_snapshot": None
    }
    validated_schema = update_typed_state(adk_session.state, init_delta, validate_transition=False)
    init_state = validated_schema.model_dump()
    
    # 3. Execute ADK workflow graph via the runner
    invocation_id = str(uuid.uuid4())
    workflow_started = time.monotonic()
    metrics.increment("workflow_executions_total")
    events = []
    try:
        async for event in runner.run_async(
            user_id=profile["user_id"],
            session_id=sim_id,
            invocation_id=invocation_id,
            new_message=types.Content(role="user", parts=[types.Part(text="{}")]),
            state_delta=init_state
        ):
            events.append(event)
    except Exception:
        metrics.increment("workflow_failures_total")
        raise
        
    # 4. Fetch the final updated state from the ADK Session
    adk_session = runner.session_service.get_session_sync(
        app_name="polaris-neuroguard",
        user_id=profile["user_id"],
        session_id=sim_id
    )
    state = get_typed_state(adk_session.state)
    
    # 5. Determine active constraints and status
    active_constraints = []
    if state.active_deadlocks:
        active_constraints.append("ENGINE_STALL")
    if state.accumulated_burn > budget_limit:
        active_constraints.append("BUDGET_OVERRUN")
        
    status = "PAUSED_BY_GUARDRAIL" if state.hitl_interrupted else "RUNNING"
    
    hitl_data = None
    if state.hitl_interrupted:
        hitl_data = HITLInterceptionData(
            requires_intervention=True,
            reason=state.hitl_reason,
            telemetry_snapshot=state.hitl_telemetry_snapshot
        )
        
    # 6. Update durable session and history using optimistic concurrency.
    if state.hitl_interrupted:
            # HITL-004: Do NOT mutate position/burn when paused. Preserve pre-interruption values.
            # Only update HITL tracking state in the session.
            session["hitl_interrupted"] = True
            session["hitl_reason"] = state.hitl_reason
            session["hitl_telemetry_snapshot"] = state.hitl_telemetry_snapshot
            session["paused_invocation_id"] = invocation_id

            # HITL-002: Atomically create durable checkpoint on interruption
            int_payload_dict = state.interruption_payload or {}
            int_reason_str = int_payload_dict.get("reason", InterruptionReason.UNKNOWN.value)
            try:
                int_reason = InterruptionReason(int_reason_str)
            except ValueError:
                int_reason = InterruptionReason.UNKNOWN

            interruption_payload = InterruptionPayload(
                interruption_id=int_payload_dict.get("interruption_id", f"int-{uuid.uuid4()}"),
                simulation_id=sim_id,
                invocation_id=invocation_id,
                workflow_node=int_payload_dict.get("workflow_node", "path_simulator"),
                reason=int_reason,
                severity=int_payload_dict.get("severity", "HIGH"),
                explanation=state.hitl_reason,
                safe_telemetry_snapshot=state.hitl_telemetry_snapshot or {},
                goal_contract_id=session.get("active_contract_id"),
                active_contract_version=session.get("active_contract_version"),
                required_resolution_action=int_payload_dict.get(
                    "required_resolution_action",
                    "Resolve blocking condition before resuming."
                ),
            )

            try:
                chk = checkpoint_service.create_checkpoint(
                    simulation_id=sim_id,
                    invocation_id=invocation_id,
                    node_position=int_payload_dict.get("workflow_node", "path_simulator"),
                    state_dict=dict(adk_session.state),
                    interruption_payload=interruption_payload,
                    active_contract_id=session.get("active_contract_id"),
                    active_contract_version=session.get("active_contract_version"),
                )
                session["active_checkpoint_id"] = chk.checkpoint_id
                session["active_checkpoint_version"] = chk.checkpoint_version
                session["paused_interruption_id"] = interruption_payload.interruption_id
            except Exception:
                # Checkpoint creation failure is non-fatal for the response
                pass
    else:
            # Only update position/burn when workflow completed without interruption
            session["current_position"] = state.current_position
            session["accumulated_burn"] = state.accumulated_burn
            session["hitl_interrupted"] = False
            session["hitl_reason"] = ""
            session["hitl_telemetry_snapshot"] = None

    history_list = session.setdefault("history", [])
    turn_number = len(history_list) + 1
    history_list.append({
            "turn_number": turn_number,
            "telemetry_snapshot": {
                "current_position": state.current_position,
                "intent_vector": payload.intent_vector.model_dump(),
                "resultant_vector": {
                    "magnitude": state.resultant_vector.magnitude,
                    "heading_degrees": state.resultant_vector.heading_degrees
                },
                "actual_burn_rate": state.actual_burn_rate,
                "angular_drift_delta": state.angular_drift_delta
            },
            "active_storms": payload.active_storms,
            "applied_decision": {
                "intent_vector": payload.intent_vector.model_dump(),
                "declared_constraints": payload.declared_constraints
            },
            "fracture_events": {
                "deadlocks": state.active_deadlocks,
                "collision_threats": state.collision_threats,
                "active_constraints": active_constraints
            }
    })
    _save_session(sim_id, session, session_version)
        
    response = EvaluateDecisionResponse(
        simulation_id=sim_id,
        telemetry=TelemetryModel(
            current_position=state.current_position,
            intent_vector=payload.intent_vector,
            resultant_vector=Vector2DModel(
                magnitude=state.resultant_vector.magnitude,
                heading_degrees=state.resultant_vector.heading_degrees
            ),
            actual_burn_rate=state.actual_burn_rate,
            angular_drift_delta=state.angular_drift_delta
        ),
        drift_warning=state.drift_warning,
        deadlocks=state.active_deadlocks,
        collision_threats=state.collision_threats,
        hitl_interception_data=hitl_data,
        status=status,
        active_constraints=active_constraints
    )
    workflow_store.complete_idempotency("evaluate", sim_id, request_id, response.model_dump())
    metrics.observe("workflow", time.monotonic() - workflow_started, {"status": status})
    if state.hitl_interrupted:
        metrics.increment("hitl_interruptions_total", {"reason": state.hitl_reason[:64]})
    if state.drift_warning:
        metrics.increment("drift_warnings_total", {"category": "angular"})
    audit_event("decision_evaluated", actor_id=principal.actor_id, request_id=request_id, simulation_id=sim_id,
                details={"status": status, "deadlocks": state.active_deadlocks, "model": "configured"})
    return response

@router.post(
    "/simulation/{simulation_id}/resume",
    response_model=ResumeSimulationResponse,
    summary="Resume simulation from a paused state"
)
async def resume_simulation(simulation_id: str, payload: ResumeSimulationRequest, principal: Principal = Depends(current_principal)):
    idempotency_payload = payload.model_dump(exclude={"resume_request_id"})
    try:
        replay = workflow_store.reserve_idempotency(
            "resume", simulation_id, payload.resume_request_id, idempotency_payload
        )
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail={"error_code": "IDEMPOTENCY_KEY_REUSED", "message": str(exc)}) from exc
    except VersionConflictError as exc:
        raise HTTPException(status_code=409, detail={"error_code": "REQUEST_IN_PROGRESS", "message": str(exc)}) from exc
    if replay is not None:
        return ResumeSimulationResponse.model_validate(replay)

    session, session_version = _load_session(simulation_id)
    enforce_owner(principal, session["profile"]["user_id"])

    domain_payload = ResumeRequestPayload(
        checkpoint_id=payload.checkpoint_id,
        resume_request_id=payload.resume_request_id,
        actor_id=payload.actor_id,
        resolution_action=payload.resolution_action,
        approval_decision_id=payload.approval_decision_id,
        amendment_id=payload.amendment_id,
        expected_checkpoint_version=payload.expected_checkpoint_version,
        intent_vector=payload.intent_vector.model_dump() if payload.intent_vector else None,
        declared_constraints=payload.declared_constraints,
    )

    response = await resume_service.execute_resume(
        simulation_id=simulation_id,
        payload=domain_payload,
        sim_session=session,
        runner=runner
    )
    _save_session(simulation_id, session, session_version)
    workflow_store.complete_idempotency("resume", simulation_id, payload.resume_request_id, response)
    metrics.increment("workflow_resumes_total", {"status": response["resume_status"]})
    audit_event("simulation_resumed", actor_id=principal.actor_id, request_id=payload.resume_request_id,
                simulation_id=simulation_id, details={"checkpoint_id": payload.checkpoint_id, "status": response["resume_status"]})
    return response



@router.get(
    "/simulation/{simulation_id}/history",
    response_model=SimulationHistoryResponse,
    summary="Fetch chronological history of a simulation session"
)
def get_simulation_history(simulation_id: str):
    """Fetches the complete historical array of telemetry, drift, constraints, and events for a simulation session."""
    session, _ = _load_session(simulation_id)
        
    history_list = session.get("history", [])
    return {
        "simulation_id": simulation_id,
        "total_turns_executed": len(history_list),
        "history": history_list
    }


@router.post(
    "/simulation/{simulation_id}/inject-storm",
    response_model=InjectStormResponse,
    summary="Dynamically inject or modify a custom environmental storm"
)
def inject_storm(simulation_id: str, payload: InjectStormRequest, principal: Principal = Depends(current_principal)):
    """Injects a new custom environmental storm or updates an existing one for the session.
    Subsequent evaluation turns will process this storm vector if included in active_storms.
    """
    session, session_version = _load_session(simulation_id)
    enforce_owner(principal, session["profile"]["user_id"])

    # Ensure custom_storms and active_storms dictionaries are initialized
    if "custom_storms" not in session:
        session["custom_storms"] = {}
    if "active_storms" not in session:
        session["active_storms"] = {}

    storm_dict = {
        "storm_type": payload.storm_type,
        "name": payload.name,
        "force_vector": {
            "magnitude": payload.magnitude,
            "heading_degrees": payload.heading_degrees
        },
        "cost_friction_multiplier": 1.0
    }
    session["custom_storms"][payload.name] = storm_dict
    session["active_storms"][payload.name] = storm_dict
    _save_session(simulation_id, session, session_version)
    audit_event("storm_injected", actor_id=principal.actor_id, simulation_id=simulation_id,
                details={"storm_name": payload.name, "storm_type": payload.storm_type})
        
    return {
        "status": "success",
        "injected_storm": payload,
        "active_custom_storms": list(session["custom_storms"].keys())
    }


# 4. DRIFT-009 & DRIFT-010 API Models & Endpoints

from app.core.amendment_workflow import (
    amendment_workflow_service,
    AmendmentNotFoundError,
    UnauthorizedActorError,
    InvalidWorkflowStateError,
)

class EvaluateDriftRequest(BaseModel):
    actor_id: Optional[str] = Field(default=None, description="Optional actor/user ID performing evaluation.")

class ConfirmAmendmentRequest(BaseModel):
    actor_id: str = Field(..., description="Actor/User ID approving or rejecting the amendment.")
    decision: str = Field(default="APPROVE", description="Decision action ('APPROVE' or 'REJECT').")
    rationale: Optional[str] = Field(default="", description="Human decision rationale.")

class ConfirmAmendmentResponse(BaseModel):
    request_id: str = Field(..., description="Target change request ID.")
    contract_id: str = Field(..., description="Target Goal Contract ID.")
    active_contract_version: int = Field(..., description="Active contract version after decision processing.")
    amendment_status: str = Field(..., description="Resulting amendment status (APPROVED or REJECTED).")
    idempotent_replay: bool = Field(default=False, description="True if decision was already processed.")
    new_contract_fingerprint: Optional[str] = Field(default=None, description="SHA-256 fingerprint if version updated.")
    message: str = Field(..., description="Summary explanation of confirmation outcome.")


@router.post(
    "/simulation/change-requests/{request_id}/evaluate",
    summary="Evaluate structured drift, rules, and semantic score for a submitted change request (DRIFT-009)"
)
def evaluate_change_request_drift(request_id: str, payload: Optional[EvaluateDriftRequest] = None,
                                  principal: Principal = Depends(current_principal)):
    """Evaluates request-intent drift for a previously submitted change request.
    Returns comprehensive deterministic rule findings, semantic score, risk policy profile, and recommended action.
    Does NOT mutate the active Goal Contract.
    """
    actor_id = payload.actor_id if payload else None
    
    # Locate simulation containing this request_id
    target_sim_id = None
    target_request_record = None
    
    for sim_id, session, _ in workflow_store.list_sessions():
        crs = session.get("change_requests", {})
        if request_id in crs:
            target_sim_id = sim_id
            target_request_record = crs[request_id]
            session_ref = session
            break
                
    if not target_sim_id or not target_request_record:
        raise HTTPException(
            status_code=404,
            detail=f"Change request ID '{request_id}' not found in any simulation session."
        )

    # Actor authorization check
    owner_id = session_ref.get("profile", {}).get("user_id", "")
    enforce_owner(principal, owner_id)
    if actor_id and owner_id and actor_id != owner_id:
        raise HTTPException(
            status_code=403,
            detail=f"Actor ID '{actor_id}' does not match simulation owner '{owner_id}'."
        )

    try:
        result = amendment_workflow_service.evaluate_change_request(session_ref, target_request_record)
        audit_event("drift_evaluated", actor_id=principal.actor_id, request_id=request_id,
                    simulation_id=target_sim_id, details={"drift_evidence": result})
        return result
    except StaleVersionError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "STALE_GOAL_CONTRACT_VERSION",
                "message": str(e),
                "contract_id": e.contract_id,
                "current_version": e.current_version,
                "expected_version": e.expected_version
            }
        )


@router.get(
    "/simulation/change-requests/{request_id}/evaluation",
    summary="Retrieve evaluation results for a change request"
)
def get_change_request_evaluation(request_id: str):
    """Fetches previously computed drift evaluation record for a change request."""
    try:
        return amendment_workflow_service.get_evaluation(request_id)
    except AmendmentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/simulation/change-requests/{request_id}/confirm",
    response_model=ConfirmAmendmentResponse,
    summary="Explicitly confirm or approve/reject a evaluated goal-amendment request (DRIFT-010)"
)
def confirm_change_request_amendment(request_id: str, payload: ConfirmAmendmentRequest,
                                    principal: Principal = Depends(current_principal)):
    """Processes explicit user or reviewer confirmation/rejection of a change request.
    If APPROVED: Instantiates new GoalContract version N+1.
    If REJECTED: Marks amendment status REJECTED without mutating the Goal Contract.
    Idempotent on repeat invocations.
    """
    target_session = None
    target_session_id = None
    target_session_version = None
    for sim_id, session, version in workflow_store.list_sessions():
        if request_id in session.get("change_requests", {}):
            target_session = session
            target_session_id = sim_id
            target_session_version = version
            break

    if not target_session:
        raise HTTPException(status_code=404, detail=f"Change request ID '{request_id}' not found.")
    enforce_owner(principal, target_session.get("profile", {}).get("user_id", ""))

    try:
        result = amendment_workflow_service.confirm_change_request(
            sim_session=target_session,
            request_id=request_id,
            actor_id=payload.actor_id,
            decision=payload.decision,
            rationale=payload.rationale or ""
        )
        _save_session(target_session_id, target_session, target_session_version)
        audit_event("amendment_decision", actor_id=principal.actor_id, request_id=request_id,
                    simulation_id=target_session_id, details={"decision": payload.decision, "result": result})
        return result
    except AmendmentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except UnauthorizedActorError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except StaleVersionError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "STALE_GOAL_CONTRACT_VERSION",
                "message": str(e),
                "contract_id": e.contract_id,
                "current_version": e.current_version,
                "expected_version": e.expected_version
            }
        )
    except InvalidWorkflowStateError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/simulation/change-requests/{request_id}/reject",
    response_model=ConfirmAmendmentResponse,
    summary="Convenience endpoint to explicitly reject a goal-amendment request (DRIFT-010)"
)
def reject_change_request_amendment(request_id: str, payload: ConfirmAmendmentRequest,
                                    principal: Principal = Depends(current_principal)):
    """Rejects a change request amendment without mutating active Goal Contract."""
    payload.decision = "REJECT"
    return confirm_change_request_amendment(request_id, payload, principal)


@router.get(
    "/simulation/{simulation_id}/change-requests/history",
    summary="Retrieve complete chronological change request and amendment history for a simulation"
)
def get_simulation_change_requests_history(simulation_id: str):
    """Fetches full chronological array of change requests, drift evaluations, and amendment states."""
    session, _ = _load_session(simulation_id)
        
    change_requests = session.get("change_requests", {})
    history = []
    for req_id, req_record in change_requests.items():
        eval_record = None
        try:
            eval_record = amendment_workflow_service.get_evaluation(req_id)
        except AmendmentNotFoundError:
            pass

        history.append({
            "request_record": req_record,
            "evaluation": eval_record
        })

    return {
        "simulation_id": simulation_id,
        "active_contract_id": session.get("active_contract_id"),
        "active_contract_version": session.get("active_contract_version"),
        "total_change_requests": len(history),
        "change_requests_history": history
    }
