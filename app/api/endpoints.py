import uuid
import threading
from enum import Enum
from typing import Dict, Any, List, Tuple, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.core.simulation import execute_turn, Vector2D, EnvironmentStorm, PRESET_STORMS, Iceberg

router = APIRouter()

# 1. Enums and Pydantic Schemas for Registration
class RiskTolerance(str, Enum):
    CONSERVATIVE = "Conservative"
    BALANCED = "Balanced"
    AGGRESSIVE = "Aggressive"

class AnchorGoal(BaseModel):
    title: str = Field(..., description="The title of the strategic goal")
    target_timeline_months: int = Field(..., description="Target timeline in months", gt=0)
    budget_limit_usd: float = Field(..., description="Strategic budget limit in USD", gt=0)
    reliability_target_sla: float = Field(..., description="Target reliability SLA", ge=0.0, le=100.0)

class CTOProfile(BaseModel):
    user_id: str = Field(..., description="The unique ID of the user")
    role: str = Field(..., description="The role of the user")
    company_scale: str = Field(..., description="The scale of the company")
    industry: str = Field(..., description="The industry of the company")
    anchor_goal: AnchorGoal = Field(..., description="The registered anchor goal")
    risk_tolerance: RiskTolerance = Field(..., description="Risk tolerance setting")


# 2. Schemas for Decision Evaluation
class Vector2DModel(BaseModel):
    magnitude: float
    heading_degrees: float

class IcebergModel(BaseModel):
    name: str
    x: float
    y: float
    radius: float = 100.0

class EvaluateDecisionRequest(BaseModel):
    simulation_id: str = Field(..., description="The unique simulation session ID")
    intent_vector: Vector2DModel = Field(..., description="The CTO's intentional velocity and direction")
    declared_constraints: List[str] = Field(default_factory=list, description="Active constraints declared by CTO")
    active_storms: List[str] = Field(default_factory=list, description="Names of active environmental storms")
    custom_icebergs: Optional[List[IcebergModel]] = Field(None, description="Optional custom icebergs")
    custom_opposing_pairs: Optional[List[Tuple[str, str]]] = Field(None, description="Optional custom opposing constraint pairs")

class TelemetryModel(BaseModel):
    current_position: Dict[str, float] = Field(..., description="New position coordinates (x, y)")
    intent_vector: Vector2DModel = Field(..., description=" CTO intentional vector")
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


# 3. In-Memory Session Store
sessions: Dict[str, Dict[str, Any]] = {}
sessions_lock = threading.Lock()


@router.get("/status")
def get_status():
    return {"status": "ready"}


@router.post("/simulation/register")
def register_simulation(profile: CTOProfile):
    sim_id = str(uuid.uuid4())
    
    with sessions_lock:
        sessions[sim_id] = {
            "profile": profile.model_dump(),
            "destination": {"x": 0.0, "y": 1000.0},
            "current_position": {"x": 0.0, "y": 0.0},
            "accumulated_burn": 0.0,
            "history": []
        }
        
    return {
        "simulation_id": sim_id,
        "quantum_mountain_coordinates": {"x": 0.0, "y": 1000.0},
        "cto_profile": profile
    }


@router.post("/simulation/evaluate-decision", response_model=EvaluateDecisionResponse)
def evaluate_decision(payload: EvaluateDecisionRequest):
    sim_id = payload.simulation_id
    
    with sessions_lock:
        if sim_id not in sessions:
            raise HTTPException(status_code=404, detail="Simulation session not found.")
        session = sessions[sim_id]
        
    # Retrieve current state from session
    curr_pos = session.get("current_position", {"x": 0.0, "y": 0.0})
    current_x = curr_pos.get("x", 0.0)
    current_y = curr_pos.get("y", 0.0)
    
    # Map active storm names to PRESET_STORMS objects
    storms_list = []
    for storm_name in payload.active_storms:
        if storm_name in PRESET_STORMS:
            storms_list.append(PRESET_STORMS[storm_name])
            
    # Convert payload structures to core simulation formats
    core_intent = Vector2D(
        magnitude=payload.intent_vector.magnitude,
        heading_degrees=payload.intent_vector.heading_degrees
    )
    
    core_custom_icebergs = []
    if payload.custom_icebergs:
        for ib in payload.custom_icebergs:
            core_custom_icebergs.append(Iceberg(name=ib.name, x=ib.x, y=ib.y, radius=ib.radius))
            
    # Execute step simulation via modular function
    result = execute_turn(
        current_x=current_x,
        current_y=current_y,
        intent_v=core_intent,
        active_storms=storms_list,
        base_burn_rate=100.0,
        declared_constraints=payload.declared_constraints,
        custom_icebergs=core_custom_icebergs,
        custom_opposing_pairs=payload.custom_opposing_pairs
    )
    
    threat_names = [ib.name for ib in result["collision_threats"]]
    deadlocks = result["deadlocks"]
    
    # ponytail: simplified HITL check and reasoning construction
    hitl_data = None
    if deadlocks or threat_names:
        reasons = []
        if deadlocks:
            reasons.append(f"Active logical deadlocks: {', '.join(f'{p[0]} & {p[1]}' for p in deadlocks)}.")
        if threat_names:
            reasons.append(f"Imminent collision threat with: {', '.join(threat_names)}.")
        
        hitl_data = HITLInterceptionData(
            requires_intervention=True,
            reason=" ".join(reasons),
            telemetry_snapshot={
                "current_position": {"x": current_x, "y": current_y},
                "resultant_vector": {
                    "magnitude": result["resultant_vector"].magnitude,
                    "heading_degrees": result["resultant_vector"].heading_degrees
                },
                "angular_drift_delta": result["angular_drift_delta"],
                "deadlocks": deadlocks,
                "threats": threat_names
            }
        )
        
    # Save the updated step results to the session store
    new_pos = result["new_position"]
    with sessions_lock:
        sessions[sim_id]["current_position"] = new_pos
        sessions[sim_id]["accumulated_burn"] = sessions[sim_id].get("accumulated_burn", 0.0) + result["actual_burn_rate"]
        sessions[sim_id].setdefault("history", []).append({
            "position": new_pos,
            "resultant_vector": {
                "magnitude": result["resultant_vector"].magnitude,
                "heading_degrees": result["resultant_vector"].heading_degrees
            },
            "actual_burn_rate": result["actual_burn_rate"],
            "angular_drift_delta": result["angular_drift_delta"],
            "deadlocks": deadlocks,
            "threats": threat_names
        })
        
    drift_warning = result["angular_drift_delta"] > 15.0
    
    return EvaluateDecisionResponse(
        simulation_id=sim_id,
        telemetry=TelemetryModel(
            current_position=new_pos,
            intent_vector=payload.intent_vector,
            resultant_vector=Vector2DModel(
                magnitude=result["resultant_vector"].magnitude,
                heading_degrees=result["resultant_vector"].heading_degrees
            ),
            actual_burn_rate=result["actual_burn_rate"],
            angular_drift_delta=result["angular_drift_delta"]
        ),
        drift_warning=drift_warning,
        deadlocks=deadlocks,
        collision_threats=threat_names,
        hitl_interception_data=hitl_data
    )
