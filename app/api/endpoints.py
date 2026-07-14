import uuid
import threading
import asyncio
from enum import Enum
from typing import Dict, Any, List, Tuple, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.core.simulation import execute_turn, Vector2D, EnvironmentStorm, PRESET_STORMS, Iceberg
from app.core.config import BASE_BURN_RATE
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
    VersionConflictError,
)

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
    magnitude: float = Field(..., description="Speed or magnitude of the vector", examples=[10.0])
    heading_degrees: float = Field(..., description="Direction in degrees from positive Y-axis (0-360°)", examples=[0.0])

class IcebergModel(BaseModel):
    name: str = Field(..., description="The name of the iceberg constraint", examples=["Custom Budget Freeze"])
    x: float = Field(..., description="X coordinate of the iceberg center", examples=[-100.0])
    y: float = Field(..., description="Y coordinate of the iceberg center", examples=[400.0])
    radius: float = Field(100.0, description="The safety boundary radius around the iceberg", examples=[100.0])

class EvaluateDecisionRequest(BaseModel):
    simulation_id: str = Field(
        ..., 
        description="The unique simulation session ID returned on registration",
        examples=["64afce2a-7f67-4307-9b63-4a5491966940"]
    )
    intent_vector: Vector2DModel = Field(..., description="The User's intentional velocity and direction")
    declared_constraints: List[str] = Field(
        default_factory=list, 
        description="Active constraints declared by the user",
        examples=[["RIGID_TIMELINE", "FREEZE_HEADCOUNT"]]
    )
    active_storms: List[str] = Field(
        default_factory=list, 
        description="Names of active environmental storms (e.g. 'Category 4 Cyclone')",
        examples=[["Category 4 Cyclone"]]
    )
    custom_icebergs: Optional[List[IcebergModel]] = Field(None, description="Optional custom icebergs to inject")
    custom_opposing_pairs: Optional[List[Tuple[str, str]]] = Field(None, description="Optional custom opposing constraint pairs to evaluate")

class ResumeSimulationRequest(BaseModel):
    intent_vector: Vector2DModel = Field(..., description="The new intent vector to override the paused state")
    declared_constraints: List[str] = Field(default_factory=list, description="New list of declared constraints")

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


# 3. In-Memory Session Store
sessions: Dict[str, Dict[str, Any]] = {}
sessions_lock = threading.Lock()


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
def register_simulation(profile: UserProfile):
    """Registers a user profile containing role, scale, industry, anchor goals, and risk tolerance.
    Initializes simulation coordinates at (0,0) with destination targets set and baseline GoalContract (v1).
    """
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

    with sessions_lock:
        sessions[sim_id] = {
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
def submit_change_request(payload: ChangeRequestPayload):
    """Submits a natural-language change request referencing the expected active goal-contract version.
    Verifies actor ownership and contract version alignment. Stores the request without mutating the active Goal Contract.
    """
    sim_id = payload.simulation_id
    
    with sessions_lock:
        if sim_id not in sessions:
            raise HTTPException(status_code=404, detail="Simulation session not found.")
        session = sessions[sim_id]
        
    profile = session.get("profile", {})
    owner_id = profile.get("user_id", "")
    
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
    with sessions_lock:
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

    return response_data


@router.post(
    "/simulation/evaluate-decision", 
    response_model=EvaluateDecisionResponse,
    summary="Evaluate decision step telemetry, deadlocks, and path collisions"
)
async def evaluate_decision(payload: EvaluateDecisionRequest):
    """Executes a single simulation step based on the user's steering intent, active constraints, and storms.
    
    Runs real-time logical deadlock checking and capsule path collision projection. Returns full telemetry
    and registers human-in-the-loop (HITL) alerts if failure thresholds are violated.
    """
    sim_id = payload.simulation_id
    
    with sessions_lock:
        if sim_id not in sessions:
            raise HTTPException(status_code=404, detail="Simulation session not found.")
        session = sessions[sim_id]
        
    profile = session["profile"]
    budget_limit = profile.get("anchor_goal", {}).get("budget_limit_usd", float("inf"))
    
    # Block and return paused state if currently interrupted
    if session.get("hitl_interrupted"):
        history = session.get("history", [])
        last_snap = history[-1]["telemetry_snapshot"] if history else {
            "current_position": session.get("current_position", {"x": 0.0, "y": 0.0}),
            "intent_vector": payload.intent_vector.model_dump(),
            "resultant_vector": {"magnitude": 0.0, "heading_degrees": 0.0},
            "actual_burn_rate": 0.0,
            "angular_drift_delta": 0.0
        }
        
        hitl_data = HITLInterceptionData(
            requires_intervention=True,
            reason=session.get("hitl_reason", ""),
            telemetry_snapshot=session.get("hitl_telemetry_snapshot")
        )
        
        active_constraints = []
        deadlocks = history[-1]["fracture_events"]["deadlocks"] if history else []
        threats = history[-1]["fracture_events"]["collision_threats"] if history else []
        if deadlocks:
            active_constraints.append("ENGINE_STALL")
        if session.get("accumulated_burn", 0.0) > budget_limit:
            active_constraints.append("BUDGET_OVERRUN")
            
        return EvaluateDecisionResponse(
            simulation_id=sim_id,
            telemetry=TelemetryModel(
                current_position=session.get("current_position", {"x": 0.0, "y": 0.0}),
                intent_vector=payload.intent_vector,
                resultant_vector=Vector2DModel(
                    magnitude=last_snap["resultant_vector"]["magnitude"],
                    heading_degrees=last_snap["resultant_vector"]["heading_degrees"]
                ),
                actual_burn_rate=last_snap["actual_burn_rate"],
                angular_drift_delta=last_snap["angular_drift_delta"]
            ),
            drift_warning=last_snap["angular_drift_delta"] > 15.0,
            deadlocks=deadlocks,
            collision_threats=threats,
            hitl_interception_data=hitl_data,
            status="PAUSED_BY_GUARDRAIL",
            active_constraints=active_constraints
        )

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
    events = []
    async for event in runner.run_async(
        user_id=profile["user_id"],
        session_id=sim_id,
        invocation_id=invocation_id,
        new_message=types.Content(role="user", parts=[types.Part(text="{}")]),
        state_delta=init_state
    ):
        events.append(event)
        
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
        
    # 6. Update local session store and history
    with sessions_lock:
        session["current_position"] = state.current_position
        session["accumulated_burn"] = state.accumulated_burn
        session["hitl_interrupted"] = state.hitl_interrupted
        session["hitl_reason"] = state.hitl_reason
        session["hitl_telemetry_snapshot"] = state.hitl_telemetry_snapshot
        if state.hitl_interrupted:
            session["paused_invocation_id"] = invocation_id
            
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
        
    return EvaluateDecisionResponse(
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

@router.post(
    "/simulation/{simulation_id}/resume",
    response_model=EvaluateDecisionResponse,
    summary="Resume simulation from a paused state"
)
async def resume_simulation(simulation_id: str, payload: ResumeSimulationRequest):
    with sessions_lock:
        if simulation_id not in sessions:
            raise HTTPException(status_code=404, detail="Simulation session not found.")
        session = sessions[simulation_id]
        
    if not session.get("hitl_interrupted"):
        raise HTTPException(status_code=400, detail="Simulation is not currently paused.")
        
    invocation_id = session.get("paused_invocation_id")
    if not invocation_id:
        raise HTTPException(status_code=500, detail="No active invocation ID found for resume.")
        
    # Fetch existing ADK session
    adk_session = runner.session_service.get_session_sync(
        app_name="polaris-neuroguard",
        user_id=session["profile"]["user_id"],
        session_id=simulation_id
    )
    if adk_session is None:
        raise HTTPException(status_code=404, detail="ADK session not found.")

    # Build and validate state delta to clear HITL flag and update decision
    raw_delta = {
        "intent_vector": payload.intent_vector.model_dump(),
        "declared_constraints": payload.declared_constraints,
        "hitl_interrupted": False,
        "hitl_reason": "",
        "hitl_telemetry_snapshot": None
    }
    validated_state = update_typed_state(adk_session.state, raw_delta, validate_transition=True)
    state_delta = raw_delta
    
    # Run the workflow resuming from the invocation_id
    events = []
    async for event in runner.run_async(
        user_id=session["profile"]["user_id"],
        session_id=simulation_id,
        invocation_id=invocation_id,
        state_delta=state_delta
    ):
        events.append(event)
        
    # Fetch updated state
    adk_session = runner.session_service.get_session_sync(
        app_name="polaris-neuroguard",
        user_id=session["profile"]["user_id"],
        session_id=simulation_id
    )
    state = get_typed_state(adk_session.state)
    
    # Update local session
    profile = session["profile"]
    budget_limit = profile.get("anchor_goal", {}).get("budget_limit_usd", float("inf"))
    projected_burn = state.accumulated_burn
    
    active_constraints = []
    if state.active_deadlocks:
        active_constraints.append("ENGINE_STALL")
    if projected_burn > budget_limit:
        active_constraints.append("BUDGET_OVERRUN")
        
    status = "PAUSED_BY_GUARDRAIL" if state.hitl_interrupted else "RUNNING"
    
    hitl_data = None
    if state.hitl_interrupted:
        hitl_data = HITLInterceptionData(
            requires_intervention=True,
            reason=state.hitl_reason,
            telemetry_snapshot=state.hitl_telemetry_snapshot
        )
        
    with sessions_lock:
        session["current_position"] = state.current_position
        session["accumulated_burn"] = projected_burn
        session["hitl_interrupted"] = state.hitl_interrupted
        session["hitl_reason"] = state.hitl_reason
        session["hitl_telemetry_snapshot"] = state.hitl_telemetry_snapshot
        if state.hitl_interrupted:
            session["paused_invocation_id"] = invocation_id
        else:
            session.pop("paused_invocation_id", None)
            
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
            "active_storms": state.active_storms,
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
        
    return EvaluateDecisionResponse(
        simulation_id=simulation_id,
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


@router.get(
    "/simulation/{simulation_id}/history",
    response_model=SimulationHistoryResponse,
    summary="Fetch chronological history of a simulation session"
)
def get_simulation_history(simulation_id: str):
    """Fetches the complete historical array of telemetry, drift, constraints, and events for a simulation session."""
    with sessions_lock:
        if simulation_id not in sessions:
            raise HTTPException(status_code=404, detail="Simulation session not found.")
        session = sessions[simulation_id]
        
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
def inject_storm(simulation_id: str, payload: InjectStormRequest):
    """Injects a new custom environmental storm or updates an existing one for the session.
    Subsequent evaluation turns will process this storm vector if included in active_storms.
    """
    with sessions_lock:
        if simulation_id not in sessions:
            raise HTTPException(status_code=404, detail="Simulation session not found.")
        session = sessions[simulation_id]
        
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
        
    return {
        "status": "success",
        "injected_storm": payload,
        "active_custom_storms": list(session["custom_storms"].keys())
    }
