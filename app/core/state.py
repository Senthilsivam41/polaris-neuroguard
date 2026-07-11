from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional

class SimulationStateSchema(BaseModel):
    """
    Unified simulation state schema for ADK 2.0 multi-agent workflow.
    Guarantees that every workflow node reads and writes to the same validated state contract.
    """
    # Simulation ID and user ID
    simulation_id: str = Field(default="", description="Unique session ID")
    user_id: str = Field(default="", description="User identifier")
    
    # Initial anchor goal
    anchor_goal: Dict[str, Any] = Field(default_factory=dict, description="Initial anchor goal config")
    
    # Current goal-contract version
    goal_contract_version: str = Field(default="1.0.0", description="Strategic contract version")
    
    # Current user request
    current_user_request: Dict[str, Any] = Field(default_factory=dict, description="Input request payload for the current turn")
    
    # Intent vector
    intent_vector: Dict[str, Any] = Field(
        default_factory=lambda: {"magnitude": 0.0, "heading_degrees": 0.0},
        description="Strategic intent velocity and direction"
    )
    
    # Declared constraints
    declared_constraints: List[str] = Field(default_factory=list, description="List of declared SMT constraint flags")
    
    # Active storms
    active_storms: List[str] = Field(default_factory=list, description="Active environment modifier names")
    
    # Position and accumulated burn
    current_position: Dict[str, float] = Field(
        default_factory=lambda: {"x": 0.0, "y": 0.0},
        description="Ship Cartesian position coordinate"
    )
    accumulated_burn: float = Field(default=0.0, description="Total financial resource consumption")
    
    # Drift assessment
    angular_drift_delta: float = Field(default=0.0, description="Difference between actual and intent heading")
    drift_warning: bool = Field(default=False, description="True if drift > 15 degrees")
    
    # Deadlocks and collision threats
    active_deadlocks: List[List[str]] = Field(default_factory=list, description="Systemic deadlocks detected")
    collision_threats: List[str] = Field(default_factory=list, description="Icebergs in path projection")
    
    # HITL interruption state
    hitl_interrupted: bool = Field(default=False, description="True if simulator loop is paused")
    hitl_reason: str = Field(default="", description="Human-in-the-loop pause reason")
    hitl_telemetry_snapshot: Optional[Dict[str, Any]] = Field(default=None, description="Diagnostic snapshot of state at interruption")
    
    # Workflow node and execution metadata
    node_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="ADK node execution statistics and timestamps"
    )
