import math
from typing import List, Tuple, Dict, Any, Optional
from pydantic import BaseModel, Field
from google.adk.tools import FunctionTool
from app.core.simulation import (
    Vector2D as Vector2D_core,
    EnvironmentStorm,
    Iceberg,
    DEFAULT_ICEBERGS,
    calculate_resultant_vector,
    check_logical_deadlocks,
    check_trajectory_collision
)

# 1. Pydantic Schemas for ADK FunctionTool inputs/outputs

class Vector2D(BaseModel):
    magnitude: float = Field(..., description="Magnitude of the vector force or speed")
    heading_degrees: float = Field(..., description="Direction in degrees from positive Y-axis (0-360°)")

class StormModel(BaseModel):
    storm_type: str = Field(..., description="Classification: Geopolitical, Meteorological, or Economic")
    name: str = Field(..., description="Name identifier of the storm")
    magnitude: float = Field(..., description="Speed magnitude of the storm force vector")
    heading_degrees: float = Field(..., description="Heading direction of the storm vector in degrees (0-360°)")
    cost_friction_multiplier: float = Field(default=1.0, description="Financial operational cost multiplier")

class IcebergModel(BaseModel):
    name: str = Field(..., description="Name identifier of the iceberg constraint")
    x: float = Field(..., description="X coordinate center")
    y: float = Field(..., description="Y coordinate center")
    radius: float = Field(default=100.0, description="Safety radius boundary")

class PositionModel(BaseModel):
    x: float = Field(..., description="X coordinate")
    y: float = Field(..., description="Y coordinate")


# 2. Tool function implementations

def calculate_resultant_vector_tool(
    intent_vector: Vector2D,
    active_storms: List[StormModel]
) -> Vector2D:
    """Sum all vectors (intent + storms) to find the resultant vector."""
    core_intent = Vector2D_core(magnitude=intent_vector.magnitude, heading_degrees=intent_vector.heading_degrees)
    core_storms = [
        EnvironmentStorm(
            storm_type=s.storm_type,
            name=s.name,
            force_vector=Vector2D_core(magnitude=s.magnitude, heading_degrees=s.heading_degrees),
            cost_friction_multiplier=s.cost_friction_multiplier
        )
        for s in active_storms
    ]
    core_res = calculate_resultant_vector(core_intent, core_storms)
    return Vector2D(magnitude=core_res.magnitude, heading_degrees=core_res.heading_degrees)


def check_logical_deadlocks_tool(
    declared_constraints: List[str],
    custom_opposing_pairs: Optional[List[Tuple[str, str]]] = None
) -> List[Tuple[str, str]]:
    """Check for active SMT logical deadlocks when opposing constraints are simultaneously declared."""
    return check_logical_deadlocks(declared_constraints, custom_opposing_pairs)


def check_trajectory_collision_tool(
    start_x: float,
    start_y: float,
    resultant_vector: Vector2D,
    custom_icebergs: Optional[List[IcebergModel]] = None
) -> List[str]:
    """Project trajectory 3 turns in the future and check for capsule intersections with icebergs."""
    core_res = Vector2D_core(magnitude=resultant_vector.magnitude, heading_degrees=resultant_vector.heading_degrees)
    icebergs = DEFAULT_ICEBERGS + [
        Iceberg(name=ib.name, x=ib.x, y=ib.y, radius=ib.radius)
        for ib in (custom_icebergs or [])
    ]
    collisions = check_trajectory_collision(start_x, start_y, core_res, icebergs)
    return [ib.name for ib in collisions]


def calculate_burn_rate_tool(
    base_burn_rate: float,
    active_storms: List[StormModel]
) -> float:
    """Calculate final operational burn-rate per turn applying macroeconomic surcharges."""
    friction_mult = 1.0
    for storm in active_storms:
        friction_mult *= storm.cost_friction_multiplier
    return base_burn_rate * friction_mult


def advance_position_tool(
    current_x: float,
    current_y: float,
    resultant_vector: Vector2D
) -> PositionModel:
    """Advance coordinates based on the resultant vector components."""
    # Convert heading (degrees from positive Y-axis) to radians
    rad = math.radians(resultant_vector.heading_degrees)
    dx = resultant_vector.magnitude * math.sin(rad)
    dy = resultant_vector.magnitude * math.cos(rad)
    return PositionModel(x=current_x + dx, y=current_y + dy)


# 3. Instantiate ADK FunctionTool components

resultant_vector_tool = FunctionTool(calculate_resultant_vector_tool)
logical_deadlocks_tool = FunctionTool(check_logical_deadlocks_tool)
trajectory_collision_tool = FunctionTool(check_trajectory_collision_tool)
burn_rate_tool = FunctionTool(calculate_burn_rate_tool)
position_advancer_tool = FunctionTool(advance_position_tool)
