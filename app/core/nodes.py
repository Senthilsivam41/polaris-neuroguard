from typing import List, Dict, Any
from google.adk.workflow import node, Workflow, Edge, START, RetryConfig
from google.adk.agents.context import Context
from google.adk.workflow._errors import NodeInterruptedError
from app.core.state import StormModel, Vector2D, IcebergModel
from app.core.simulation import (
    PRESET_STORMS,
    DEFAULT_ICEBERGS,
    Iceberg,
    calculate_resultant_vector,
    advance_position,
    calculate_actual_burn_rate,
    check_trajectory_collision,
    EnvironmentStorm,
    Vector2D as SimVector2D
)

BASE_BURN_RATE = 100.0

@node(retry_config=RetryConfig(max_attempts=3))
def weather_station(ctx: Context, active_storms: list[str], custom_storms: dict[str, StormModel]) -> list[StormModel]:
    resolved = []
    for storm_name in active_storms:
        if storm_name in custom_storms:
            storm = custom_storms[storm_name]
            if isinstance(storm, dict):
                storm = StormModel(**storm)
            resolved.append(storm)
        elif storm_name in PRESET_STORMS:
            preset = PRESET_STORMS[storm_name]
            resolved.append(StormModel(
                storm_type=preset.storm_type,
                name=preset.name,
                force_vector=Vector2D(
                    magnitude=preset.force_vector.magnitude,
                    heading_degrees=preset.force_vector.heading_degrees
                ),
                cost_friction_multiplier=preset.cost_friction_multiplier
            ))
        else:
            raise ValueError(f"Unknown storm: {storm_name}")
            
    ctx.state["resolved_storms"] = resolved
    return resolved

@node(retry_config=RetryConfig(max_attempts=3))
def path_simulator(ctx: Context) -> dict:
    state = ctx.state
    
    # 1. Resolve intent velocity
    intent_v = state["intent_vector"]
    if isinstance(intent_v, dict):
        intent_v = Vector2D(**intent_v)
    # If active deadlocks are present, intent magnitude drops to 0.0 (stall)
    if state["active_deadlocks"]:
        intent_v = Vector2D(magnitude=0.0, heading_degrees=intent_v.heading_degrees)
        
    sim_intent = SimVector2D(magnitude=intent_v.magnitude, heading_degrees=intent_v.heading_degrees)
    
    # 2. Resolve active storms to EnvironmentStorm objects
    resolved_storms = state["resolved_storms"]
    storms_list = []
    for storm in resolved_storms:
        if isinstance(storm, dict):
            storm = StormModel(**storm)
        storms_list.append(EnvironmentStorm(
            storm_type=storm.storm_type,
            name=storm.name,
            force_vector=SimVector2D(
                magnitude=storm.force_vector.magnitude,
                heading_degrees=storm.force_vector.heading_degrees
            ),
            cost_friction_multiplier=storm.cost_friction_multiplier
        ))
        
    # 3. Calculate resultant vector
    sim_resultant = calculate_resultant_vector(sim_intent, storms_list)
    resultant_v = Vector2D(magnitude=sim_resultant.magnitude, heading_degrees=sim_resultant.heading_degrees)
    
    # 4. Advance position
    curr_pos = state["current_position"]
    new_x, new_y = advance_position(curr_pos.get("x", 0.0), curr_pos.get("y", 0.0), sim_resultant)
    new_pos = {"x": new_x, "y": new_y}
    
    # 5. Check for trajectory collision threats (3 turns look-ahead)
    custom_icebergs = state["custom_icebergs"]
    custom_ib_list = []
    for ib in custom_icebergs:
        if isinstance(ib, dict):
            ib = IcebergModel(**ib)
        custom_ib_list.append(Iceberg(name=ib.name, x=ib.x, y=ib.y, radius=ib.radius))
        
    all_icebergs = DEFAULT_ICEBERGS + custom_ib_list
    collisions = check_trajectory_collision(
        curr_pos.get("x", 0.0), curr_pos.get("y", 0.0), sim_resultant, all_icebergs
    )
    collision_names = [ib.name for ib in collisions]
    
    # 6. Calculate actual burn rate and accumulated burn
    actual_burn = calculate_actual_burn_rate(BASE_BURN_RATE, storms_list)
    new_accumulated = state["accumulated_burn"] + actual_burn
    
    # 7. Quantify strategic drift delta
    theta_a = intent_v.heading_degrees
    theta_g = resultant_v.heading_degrees
    angle_diff = abs(theta_g - theta_a) % 360.0
    angular_drift_delta = min(angle_diff, 360.0 - angle_diff)
    drift_warning = angular_drift_delta > 15.0
    
    # 8. Check for HITL interception if deadlocks or collisions exist
    deadlocks = state["active_deadlocks"]
    hitl_data = None
    if deadlocks or collision_names:
        reasons = []
        if deadlocks:
            reasons.append(f"Active logical deadlocks: {', '.join(f'{p[0]} & {p[1]}' for p in deadlocks)}.")
        if collision_names:
            reasons.append(f"Imminent collision threat with: {', '.join(collision_names)}.")
            
        hitl_data = {
            "requires_intervention": True,
            "reason": " ".join(reasons),
            "telemetry_snapshot": {
                "current_position": new_pos,
                "resultant_vector": {
                    "magnitude": resultant_v.magnitude,
                    "heading_degrees": resultant_v.heading_degrees
                },
                "angular_drift_delta": angular_drift_delta,
                "deadlocks": deadlocks,
                "threats": collision_names
            }
        }
        
    # Write all simulation outputs back to the state
    state["current_position"] = new_pos
    state["accumulated_burn"] = new_accumulated
    state["resultant_vector"] = resultant_v
    state["actual_burn_rate"] = actual_burn
    state["angular_drift_delta"] = angular_drift_delta
    state["drift_warning"] = drift_warning
    state["collision_threats"] = collision_names
    
    if hitl_data:
        state["hitl_interrupted"] = True
        state["hitl_reason"] = hitl_data["reason"]
        state["hitl_telemetry_snapshot"] = hitl_data["telemetry_snapshot"]
        raise NodeInterruptedError()
    else:
        state["hitl_interrupted"] = False
        state["hitl_reason"] = ""
        state["hitl_telemetry_snapshot"] = None
        
    return {
        "current_position": new_pos,
        "resultant_vector": resultant_v,
        "actual_burn_rate": actual_burn,
        "angular_drift_delta": angular_drift_delta,
        "drift_warning": drift_warning,
        "deadlocks": deadlocks,
        "collision_threats": collision_names,
        "status": "RUNNING"
    }

from app.core.agents import goal_analyzer, constraint_predictor

goal_analyzer.retry_config = RetryConfig(max_attempts=3)
constraint_predictor.retry_config = RetryConfig(max_attempts=3)

simulation_workflow = Workflow(
    name="SimulationWorkflow",
    edges=[
        Edge(from_node=START, to_node=goal_analyzer),
        Edge(from_node=goal_analyzer, to_node=constraint_predictor, route="consistent"),
        Edge(from_node=constraint_predictor, to_node=weather_station, route="no_deadlock"),
        Edge(from_node=constraint_predictor, to_node=path_simulator, route="deadlock"),
        Edge(from_node=weather_station, to_node=path_simulator),
    ]
)
