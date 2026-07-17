import time
from typing import List, Dict, Any
from google.adk.workflow import node, Workflow, Edge, START, RetryConfig
from google.adk.agents.context import Context
from google.adk.workflow._errors import NodeInterruptedError
from app.core.state import StormModel, Vector2D, IcebergModel, get_typed_state, update_typed_state
from app.core.hitl.interruption import InterruptionReason, InterruptionPayload, ADKInterruptionError
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

from app.core.config import BASE_BURN_RATE, WORKFLOW_RETRY_CONFIG
from app.core.observability import metrics

class UnknownStormError(ValueError):
    """Deterministic validation error raised when an unrecognized storm name is passed to weather_station."""
    pass

WORKFLOW_NODE_RETRY_CONFIG = RetryConfig(
    max_attempts=WORKFLOW_RETRY_CONFIG.max_attempts,
    initial_delay=WORKFLOW_RETRY_CONFIG.initial_delay,
    max_delay=WORKFLOW_RETRY_CONFIG.max_delay,
    backoff_factor=WORKFLOW_RETRY_CONFIG.backoff_factor,
    exceptions_to_skip=(UnknownStormError,)
)

@node(retry_config=WORKFLOW_NODE_RETRY_CONFIG)
def weather_station(ctx: Context, active_storms: list[str], custom_storms: dict[str, StormModel]) -> list[StormModel]:
    node_started = time.monotonic()
    metrics.increment("node_executions_total", {"node": "weather_station"})
    # Enforce typed state contract at node entry
    typed_state = get_typed_state(ctx.state)
    
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
            raise UnknownStormError(f"Unknown storm: {storm_name}")
            
    update_typed_state(
        ctx.state,
        {"resolved_storms": [s.model_dump() for s in resolved]},
        validate_transition=False
    )
    metrics.observe("node_execution", time.monotonic() - node_started,
                    {"node": "weather_station", "status": "success"})
    return resolved

@node(retry_config=WORKFLOW_NODE_RETRY_CONFIG)
def path_simulator(ctx: Context) -> dict:
    node_started = time.monotonic()
    metrics.increment("node_executions_total", {"node": "path_simulator"})
    # 1. Enforce typed state contract at boundary entry
    state = get_typed_state(ctx.state)
    
    # 2. Resolve intent velocity
    intent_v = state.intent_vector
    # If active deadlocks are present, intent magnitude drops to 0.0 (stall)
    if state.active_deadlocks:
        intent_v = Vector2D(magnitude=0.0, heading_degrees=intent_v.heading_degrees)
        
    sim_intent = SimVector2D(magnitude=intent_v.magnitude, heading_degrees=intent_v.heading_degrees)
    
    # 3. Resolve active storms to EnvironmentStorm objects
    storms_list = []
    for storm in state.resolved_storms:
        storms_list.append(EnvironmentStorm(
            storm_type=storm.storm_type,
            name=storm.name,
            force_vector=SimVector2D(
                magnitude=storm.force_vector.magnitude,
                heading_degrees=storm.force_vector.heading_degrees
            ),
            cost_friction_multiplier=storm.cost_friction_multiplier
        ))
        
    # 4. Calculate resultant vector
    sim_resultant = calculate_resultant_vector(sim_intent, storms_list)
    resultant_v = Vector2D(magnitude=sim_resultant.magnitude, heading_degrees=sim_resultant.heading_degrees)
    
    # 5. Advance position
    curr_pos = state.current_position
    new_x, new_y = advance_position(curr_pos.get("x", 0.0), curr_pos.get("y", 0.0), sim_resultant)
    new_pos = {"x": new_x, "y": new_y}
    
    # 6. Check for trajectory collision threats (3 turns look-ahead)
    custom_ib_list = [
        Iceberg(name=ib.name, x=ib.x, y=ib.y, radius=ib.radius)
        for ib in state.custom_icebergs
    ]
        
    all_icebergs = DEFAULT_ICEBERGS + custom_ib_list
    collisions = check_trajectory_collision(
        curr_pos.get("x", 0.0), curr_pos.get("y", 0.0), sim_resultant, all_icebergs
    )
    collision_names = [ib.name for ib in collisions]
    
    # 7. Calculate actual burn rate and accumulated burn
    actual_burn = calculate_actual_burn_rate(BASE_BURN_RATE, storms_list)
    new_accumulated = state.accumulated_burn + actual_burn
    
    # 8. Quantify strategic drift delta
    theta_a = intent_v.heading_degrees
    theta_g = resultant_v.heading_degrees
    angle_diff = abs(theta_g - theta_a) % 360.0
    angular_drift_delta = min(angle_diff, 360.0 - angle_diff)
    drift_warning = angular_drift_delta > 15.0
    
    # 9. Check for HITL interception if deadlocks or collisions exist
    deadlocks = state.active_deadlocks

    delta_update: Dict[str, Any] = {
        "current_position": new_pos,
        "accumulated_burn": new_accumulated,
        "resultant_vector": resultant_v.model_dump(),
        "actual_burn_rate": actual_burn,
        "angular_drift_delta": angular_drift_delta,
        "drift_warning": drift_warning,
        "collision_threats": collision_names,
    }

    if deadlocks or collision_names:
        reasons = []
        if deadlocks:
            reasons.append(f"Active logical deadlocks: {', '.join(f'{p[0]} & {p[1]}' for p in deadlocks)}.")
            interruption_reason = InterruptionReason.STATIC_CONSTRAINT_DEADLOCK
        if collision_names:
            reasons.append(f"Imminent collision threat with: {', '.join(collision_names)}.")
            if not deadlocks:
                interruption_reason = InterruptionReason.COLLISION_THREAT

        hitl_reason = " ".join(reasons)
        hitl_snapshot = {
            "current_position": new_pos,
            "resultant_vector": {
                "magnitude": resultant_v.magnitude,
                "heading_degrees": resultant_v.heading_degrees,
            },
            "angular_drift_delta": angular_drift_delta,
            "deadlocks": deadlocks,
            "threats": collision_names,
        }

        invocation_id = getattr(ctx, "invocation_id", "") or "inv-unknown"
        simulation_id = state.simulation_id or "sim-unknown"
        contract_id = state.active_contract_id or f"contract-{simulation_id}"
        contract_version = state.active_contract_version or 1

        payload = InterruptionPayload(
            simulation_id=simulation_id,
            invocation_id=invocation_id,
            workflow_node="path_simulator",
            reason=interruption_reason,
            severity="CRITICAL" if deadlocks else "HIGH",
            explanation=hitl_reason,
            safe_telemetry_snapshot=hitl_snapshot,
            goal_contract_id=contract_id,
            active_contract_version=contract_version,
            required_resolution_action="Resolve deadlock or trajectory collision threat to resume simulation."
        )

        delta_update.update({
            "hitl_interrupted": True,
            "hitl_reason": hitl_reason,
            "hitl_telemetry_snapshot": hitl_snapshot,
            "interruption_payload": payload.model_dump(),
        })
        
        # Enforce validation and state transition rules on node exit
        update_typed_state(ctx.state, delta_update, validate_transition=True)
        
        # Register interruption ID on context for ADK tracking
        ctx._interrupt_ids.add(payload.interruption_id)

        raise ADKInterruptionError(payload)

    delta_update.update({
        "hitl_interrupted": False,
        "hitl_reason": "",
        "hitl_telemetry_snapshot": None,
    })
    
    # Enforce validation and state transition rules on node exit
    update_typed_state(ctx.state, delta_update, validate_transition=True)
    
    metrics.observe("node_execution", time.monotonic() - node_started,
                    {"node": "path_simulator", "status": "success"})
    return {
        "current_position": new_pos,
        "resultant_vector": resultant_v,
        "actual_burn_rate": actual_burn,
        "angular_drift_delta": angular_drift_delta,
        "drift_warning": drift_warning,
        "deadlocks": deadlocks,
        "collision_threats": collision_names,
        "status": "RUNNING",
    }

from app.core.agents import goal_analyzer, constraint_predictor

goal_analyzer.retry_config = WORKFLOW_NODE_RETRY_CONFIG
constraint_predictor.retry_config = WORKFLOW_NODE_RETRY_CONFIG

simulation_workflow = Workflow(
    name="SimulationWorkflow",
    edges=[
        Edge(from_node=START, to_node=goal_analyzer),
        Edge(from_node=goal_analyzer, to_node=constraint_predictor, route="consistent"),
        Edge(from_node=constraint_predictor, to_node=weather_station),
        Edge(from_node=weather_station, to_node=path_simulator),
    ]
)

# FR-3.5 / NFR-1.2: all four nodes must be to_a2a-exposable so they can be
# swapped for remote agents without changing the workflow graph.
# get_a2a_nodes() is a lazy factory: calling it requires the google-adk[a2a]
# extra (and its a2a dependency). The function is importable regardless.
def get_a2a_nodes() -> dict:
    """Return A2A Starlette apps for all four simulation nodes.

    Requires google-adk[a2a] to be installed. Raises ImportError if the
    'a2a' package is missing from the environment.
    """
    from google.adk.a2a.utils.agent_to_a2a import to_a2a as _to_a2a
    from app.core.security import A2AAuthMiddleware
    nodes = {
        "goal_analyzer": _to_a2a(goal_analyzer),
        "constraint_predictor": _to_a2a(constraint_predictor),
        "weather_station": _to_a2a(weather_station),
        "path_simulator": _to_a2a(path_simulator),
    }
    for app in nodes.values():
        app.add_middleware(A2AAuthMiddleware)
    return nodes
