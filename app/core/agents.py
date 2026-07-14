import json
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types as genai_types
from app.core.config import GEMINI_MODEL
from app.core.tools import logical_deadlocks_tool
from app.core.simulation import check_logical_deadlocks
from app.core.state import Vector2D as StateVector2D, get_typed_state, update_typed_state

class ConflictDetail(BaseModel):
    constraint_a: str = Field(description="First constraint in conflict")
    constraint_b: str = Field(description="Second constraint in conflict")
    conflict_type: str = Field(default="semantic", description="Type: 'static' or 'semantic'")
    evidence: str = Field(description="Detailed reason or evidence for why these two constraints conflict under current conditions")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")

    @model_validator(mode="after")
    def validate_conflict_fields(self) -> 'ConflictDetail':
        if self.conflict_type not in ("static", "semantic"):
            self.conflict_type = "semantic"
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        return self

class ConstraintConflictAssessment(BaseModel):
    has_deadlock: bool = Field(description="True if any active deadlock/conflict is detected (either deterministic static pair or high-confidence novel semantic conflict)")
    conflicts: List[ConflictDetail] = Field(default_factory=list, description="List of detected conflicting constraint pairs with evidence and confidence")

async def before_predictor_callback(callback_context: CallbackContext) -> Optional[genai_types.Content]:
    """
    Deterministic SMT pre-execution check for static opposing constraint pairs.
    If static deadlocks exist among declared_constraints, short-circuits the LLM call immediately
    by returning a synthetic Content object and setting active_deadlocks, route, and intent vector stall.
    """
    current_state = get_typed_state(callback_context.state)
    declared = current_state.declared_constraints
    
    deadlocks = check_logical_deadlocks(declared)
    if not deadlocks:
        return None  # Allow LLM to evaluate semantic conflicts
        
    deadlocks_list = [[a, b] for a, b in deadlocks]
    
    # Update state via typed boundary
    intent = current_state.intent_vector
    stalled_intent = StateVector2D(
        magnitude=0.0,
        heading_degrees=intent.heading_degrees
    )
    
    update_typed_state(
        callback_context.state,
        {
            "active_deadlocks": deadlocks_list,
            "intent_vector": stalled_intent.model_dump(),
        },
        validate_transition=False
    )
    
    # Set route
    callback_context.route = "deadlock"
    if hasattr(callback_context, "_event_actions") and callback_context._event_actions:
        callback_context._event_actions.route = "deadlock"
        
    # Build schema-valid synthetic response Content
    assessment = ConstraintConflictAssessment(
        has_deadlock=True,
        conflicts=[
            ConflictDetail(
                constraint_a=a,
                constraint_b=b,
                conflict_type="static",
                evidence=f"Static deterministic conflict between opposing constraints: '{a}' and '{b}'.",
                confidence=1.0
            )
            for a, b in deadlocks
        ]
    )
    
    return genai_types.Content(
        role="model",
        parts=[genai_types.Part(text=assessment.model_dump_json())]
    )

async def after_predictor_callback(callback_context: CallbackContext) -> None:
    # 1. Retrieve the last model response from this agent
    model_text = None
    for event in reversed(callback_context.session.events):
        if event.author == "ConstraintPredictor" and event.content:
            parts = event.content.parts
            if parts:
                model_text = "".join(p.text for p in parts if p.text and not p.thought)
                break
                
    # 2. If no text or parsing fails, fallback to checking static tool output in session events
    if not model_text:
        await _fallback_static_check(callback_context)
        return
        
    try:
        cleaned_text = model_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()
        
        assessment = ConstraintConflictAssessment.model_validate_json(cleaned_text)
    except Exception:
        await _fallback_static_check(callback_context)
        return

    # 3. Process the parsed assessment: only static or high-confidence (>= 0.7) semantic conflicts block
    deadlocks_list = []
    has_blocking_conflict = False
    for c in assessment.conflicts:
        if c.conflict_type == "static" or c.confidence >= 0.7:
            deadlocks_list.append([c.constraint_a, c.constraint_b])
            has_blocking_conflict = True
            
    # Persist detected deadlocks to session state via typed update
    delta: dict = {"active_deadlocks": deadlocks_list}
    
    if assessment.has_deadlock and has_blocking_conflict:
        callback_context.route = "deadlock"
        if hasattr(callback_context, "_event_actions") and callback_context._event_actions:
            callback_context._event_actions.route = "deadlock"
        current_state = get_typed_state(callback_context.state)
        intent = current_state.intent_vector
        delta["intent_vector"] = StateVector2D(
            magnitude=0.0,
            heading_degrees=intent.heading_degrees
        ).model_dump()
    else:
        callback_context.route = "no_deadlock"
        if hasattr(callback_context, "_event_actions") and callback_context._event_actions:
            callback_context._event_actions.route = "no_deadlock"

    update_typed_state(callback_context.state, delta, validate_transition=False)

async def _fallback_static_check(callback_context: CallbackContext) -> None:
    """Fallback SMT check that scans tool responses in session events for static deadlocks."""
    deadlocks_list = []
    for event in callback_context.session.events:
        for fr in event.get_function_responses():
            if fr.name == "check_logical_deadlocks_tool" and fr.response:
                for p1, p2 in fr.response:
                    deadlocks_list.append([p1, p2])
                    
    delta: dict = {}
    if deadlocks_list:
        delta["active_deadlocks"] = deadlocks_list
        callback_context.route = "deadlock"
        callback_context._event_actions.route = "deadlock"
        current_state = get_typed_state(callback_context.state)
        intent = current_state.intent_vector
        delta["intent_vector"] = StateVector2D(
            magnitude=0.0,
            heading_degrees=intent.heading_degrees
        ).model_dump()
    else:
        callback_context.route = "no_deadlock"
        callback_context._event_actions.route = "no_deadlock"

    if delta:
        update_typed_state(callback_context.state, delta, validate_transition=False)

CONSTRAINT_PREDICTOR_INSTRUCTION = """
You are the Constraint Conflict Predictor Agent for the Polaris Neuro Guard simulation.
Your responsibility is to analyze the declared_constraints and active_storms to identify any conflicting constraint configurations that represent a system deadlock.

Guidelines:
1. ALWAYS call the `check_logical_deadlocks_tool` first to deterministically identify any static opposing constraint pairs among the `declared_constraints`.
2. If the tool detects any deadlocks, you must include them in the `conflicts` list with `conflict_type`='static' and `confidence`=1.0.
3. Perform semantic reasoning over the `declared_constraints` to detect any novel or paraphrased constraint conflicts that the static tool might have missed (e.g. semantically equivalent constraints like 'FREEZE_HEADCOUNT' and 'INCREASE_STAFFING_LEVELS', or 'RIGID_TIMELINE' and 'EXTEND_SCHEDULE').
4. For novel or paraphrased conflicts, set `conflict_type`='semantic' and provide a clear `evidence` description and a `confidence` score (0.0 to 1.0).
5. Set `has_deadlock` to True only if a deterministic static deadlock was found or a novel semantic deadlock is detected with high confidence (confidence >= 0.7).
6. If a semantic conflict is detected with low confidence (< 0.7), include it in the `conflicts` list to document it, but do NOT set `has_deadlock` to True. This ensures uncertain conflicts do not silently block the system.
"""

constraint_predictor = LlmAgent(
    name="ConstraintPredictor",
    model=GEMINI_MODEL,
    instruction=CONSTRAINT_PREDICTOR_INSTRUCTION,
    tools=[logical_deadlocks_tool],
    output_schema=ConstraintConflictAssessment,
    before_agent_callback=before_predictor_callback,
    after_agent_callback=after_predictor_callback
)

class GoalAnalysisResult(BaseModel):
    is_consistent: bool = Field(description="True if the user request is strategically consistent with the anchor goal and risk tolerance, False otherwise")
    evidence: str = Field(description="Detailed reason or evidence for why the request is consistent or inconsistent")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")

async def after_analyzer_callback(callback_context: CallbackContext) -> None:
    # 1. Retrieve the last model response from this agent
    model_text = None
    for event in reversed(callback_context.session.events):
        if event.author == "GoalAnalyzer" and event.content:
            parts = event.content.parts
            if parts:
                model_text = "".join(p.text for p in parts if p.text and not p.thought)
                break
                
    if not model_text:
        callback_context.route = "inconsistent"
        callback_context._event_actions.route = "inconsistent"
        return
        
    try:
        cleaned_text = model_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()
        
        result = GoalAnalysisResult.model_validate_json(cleaned_text)
    except Exception:
        callback_context.route = "inconsistent"
        callback_context._event_actions.route = "inconsistent"
        return

    if result.is_consistent:
        callback_context.route = "consistent"
        callback_context._event_actions.route = "consistent"
    else:
        callback_context.route = "inconsistent"
        callback_context._event_actions.route = "inconsistent"

    # Trigger a dummy state delta via typed helper so route event is preserved
    current_state = get_typed_state(callback_context.state)
    update_typed_state(
        callback_context.state,
        {"risk_tolerance": current_state.risk_tolerance},
        validate_transition=False
    )

GOAL_ANALYZER_INSTRUCTION = """
You are the Goal Analyzer agent for the Polaris Neuro Guard simulation.
Your responsibility is to analyze the user's current request (including steering intent and declared constraints) against their strategic `anchor_goal` (timeline, budget, reliability SLA) and `risk_tolerance` level.

Guidelines:
1. Compare the requested intent vector and constraints to the anchor goal's parameters:
   - Check if the budget or timeline targets are likely to be violated by the current request or declared constraints.
   - For example, if a user requests high-burn steering or constraints that directly increase costs, evaluate if this is consistent with the remaining budget.
2. Assess the risk level of the request in the context of the user's `risk_tolerance` (Conservative, Balanced, Aggressive).
   - Conservative: High speed or risky constraint combinations under severe weather/storms are inconsistent.
   - Balanced: Moderate risks are acceptable.
   - Aggressive: High risk maneuvers are consistent.
3. Return `is_consistent` = True if the request is strategically consistent with the anchor goal and risk tolerance. Otherwise, set `is_consistent` = False.
4. Provide a detailed `evidence` string explaining your analysis, and a `confidence` score (0.0 to 1.0) indicating how certain you are of the assessment.
"""

goal_analyzer = LlmAgent(
    name="GoalAnalyzer",
    model=GEMINI_MODEL,
    instruction=GOAL_ANALYZER_INSTRUCTION,
    output_schema=GoalAnalysisResult,
    after_agent_callback=after_analyzer_callback
)
