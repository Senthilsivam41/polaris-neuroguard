from pydantic import BaseModel, Field, model_validator
from typing import Dict, List, Any, Optional

# 1. Nested typed models to enforce strict contracts

class Vector2D(BaseModel):
    magnitude: float = Field(default=0.0, ge=0.0, description="Magnitude of the vector force or speed")
    heading_degrees: float = Field(default=0.0, ge=0.0, le=360.0, description="Direction in degrees (0-360°)")

class GoalModel(BaseModel):
    title: str = Field(default="", description="Goal title")
    target_timeline_months: int = Field(default=12, gt=0, description="Target timeline in months")
    budget_limit_usd: float = Field(default=1000000.0, gt=0.0, description="Budget limit in USD")
    reliability_target_sla: float = Field(default=99.9, ge=0.0, le=100.0, description="Reliability target SLA percentage")

class UserRequestModel(BaseModel):
    intent_vector: Optional[Vector2D] = None
    declared_constraints: Optional[List[str]] = None

class NodeMetadataModel(BaseModel):
    current_node: str = Field(default="", description="Current executing node name")
    execution_timestamp: float = Field(default=0.0, ge=0.0, description="Timestamp of execution")
    attempts: int = Field(default=1, ge=0, description="Number of execution attempts")

class StormModel(BaseModel):
    storm_type: str = Field(description="Type of storm")
    name: str = Field(description="Name of storm")
    force_vector: Vector2D = Field(description="Force vector of the storm")
    cost_friction_multiplier: float = Field(default=1.0, description="Cost multiplier")

class IcebergModel(BaseModel):
    name: str = Field(description="The name of the iceberg constraint")
    x: float = Field(description="X coordinate of the iceberg center")
    y: float = Field(description="Y coordinate of the iceberg center")
    radius: float = Field(default=100.0, description="The safety boundary radius around the iceberg")


# 2. Main workflow state schema with validation checks

class SimulationStateSchema(BaseModel):
    """
    Unified simulation state schema for ADK 2.0 multi-agent workflow.
    Guarantees that every workflow node reads and writes to the same validated state contract.
    """
    # Simulation ID and user ID
    simulation_id: str = Field(default="", description="Unique session ID")
    user_id: str = Field(default="", description="User identifier")
    risk_tolerance: str = Field(default="Balanced", description="User risk tolerance setting")
    
    # Initial anchor goal
    anchor_goal: GoalModel = Field(default_factory=GoalModel, description="Initial anchor goal config")
    
    # Current goal-contract version & references (DRIFT-001)
    goal_contract_version: str = Field(default="1.0.0", description="Strategic contract version label")
    active_contract_id: Optional[str] = Field(default=None, description="Active Goal Contract unique ID")
    active_contract_version: Optional[int] = Field(default=None, description="Active Goal Contract version number")
    active_contract_fingerprint: Optional[str] = Field(default=None, description="Active Goal Contract SHA-256 fingerprint")
    
    # Current user request
    current_user_request: UserRequestModel = Field(default_factory=UserRequestModel, description="Input request payload for the current turn")
    
    # Intent vector
    intent_vector: Vector2D = Field(
        default_factory=Vector2D,
        description="Strategic intent velocity and direction"
    )
    
    # Declared constraints
    declared_constraints: List[str] = Field(default_factory=list, description="List of declared SMT constraint flags")
    
    # Active storms
    active_storms: List[str] = Field(default_factory=list, description="Active environment modifier names")
    
    # Custom storms injected in the session
    custom_storms: Dict[str, StormModel] = Field(default_factory=dict, description="Custom storms details")
    
    # Resolved storm objects active in this turn
    resolved_storms: List[StormModel] = Field(default_factory=list, description="Resolved active storms")
    
    # Custom icebergs injected in the session
    custom_icebergs: List[IcebergModel] = Field(default_factory=list, description="Custom icebergs list")
    
    # Simulation vector outputs
    resultant_vector: Vector2D = Field(default_factory=Vector2D, description="Resultant velocity vector")
    actual_burn_rate: float = Field(default=0.0, ge=0.0, description="Burn rate for the current turn")
    
    # Position and accumulated burn (with validation bounds)
    current_position: Dict[str, float] = Field(
        default_factory=lambda: {"x": 0.0, "y": 0.0},
        description="Ship Cartesian position coordinate"
    )
    accumulated_burn: float = Field(default=0.0, ge=0.0, description="Total financial resource consumption")
    
    # Drift assessment (with validation bounds)
    angular_drift_delta: float = Field(default=0.0, ge=0.0, description="Difference between actual and intent heading")
    drift_warning: bool = Field(default=False, description="True if drift > 15 degrees")
    
    # Deadlocks and collision threats
    active_deadlocks: List[List[str]] = Field(default_factory=list, description="Systemic deadlocks detected")
    collision_threats: List[str] = Field(default_factory=list, description="Icebergs in path projection")
    
    # HITL interruption state
    hitl_interrupted: bool = Field(default=False, description="True if simulator loop is paused")
    hitl_reason: str = Field(default="", description="Human-in-the-loop pause reason")
    hitl_telemetry_snapshot: Optional[Dict[str, Any]] = Field(default=None, description="Diagnostic snapshot of state at interruption")
    interruption_payload: Optional[Dict[str, Any]] = Field(default=None, description="Typed interruption payload dictionary")
    
    # Workflow node and execution metadata
    node_metadata: NodeMetadataModel = Field(
        default_factory=NodeMetadataModel,
        description="ADK node execution statistics and timestamps"
    )

    @model_validator(mode="after")
    def validate_hitl_state(self) -> 'SimulationStateSchema':
        """Ensure consistency of HITL interruption state variables."""
        if self.hitl_interrupted:
            if not self.hitl_reason:
                raise ValueError("hitl_reason cannot be empty when hitl_interrupted is True")
            if self.hitl_telemetry_snapshot is None:
                raise ValueError("hitl_telemetry_snapshot cannot be None when hitl_interrupted is True")
        else:
            if self.hitl_reason:
                raise ValueError("hitl_reason must be empty when hitl_interrupted is False")
        return self


# 3. Transition validation check

def validate_state_transition(old_state: SimulationStateSchema, new_state: SimulationStateSchema) -> None:
    """Enforce that state transitions obey rules (e.g. burn rate cannot decrease)."""
    if new_state.accumulated_burn < old_state.accumulated_burn:
        raise ValueError("accumulated_burn cannot decrease.")
    if old_state.hitl_interrupted and not new_state.hitl_interrupted:
        if new_state.hitl_reason:
            raise ValueError("hitl_reason must be cleared when exiting interruption.")


# 4. Typed boundary helper functions

def get_typed_state(raw_state: Any) -> SimulationStateSchema:
    """
    Validate and return a SimulationStateSchema from a raw dict, Context.state, or ADK State object.
    Enforces the full schema contract at boundary entry.
    """
    if hasattr(raw_state, "to_dict"):
        state_dict = raw_state.to_dict()
    elif hasattr(raw_state, "items"):
        state_dict = dict(raw_state)
    else:
        state_dict = raw_state
    return SimulationStateSchema.model_validate(state_dict)


def update_typed_state(
    state_target: Any,
    delta: Dict[str, Any],
    validate_transition: bool = True
) -> SimulationStateSchema:
    """
    Apply a delta update to state_target (a Context.state dict-like object or python dict),
    validate the resulting object against SimulationStateSchema and transition constraints,
    and persist the validated fields back to state_target.
    """
    current_schema = get_typed_state(state_target)
    merged = current_schema.model_dump()
    merged.update(delta)
    
    new_schema = SimulationStateSchema.model_validate(merged)
    
    if validate_transition:
        validate_state_transition(current_schema, new_schema)
        
    updated_dict = new_schema.model_dump()
    if hasattr(state_target, "update"):
        state_target.update(updated_dict)
    elif isinstance(state_target, dict):
        state_target.update(updated_dict)
        
    return new_schema

