from typing import List, Optional
from pydantic import BaseModel, Field
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from app.core.config import GEMINI_MODEL
from app.core.tools import logical_deadlocks_tool
from app.core.state import Vector2D as StateVector2D

class ConflictDetail(BaseModel):
    constraint_a: str = Field(description="First constraint in conflict")
    constraint_b: str = Field(description="Second constraint in conflict")
    conflict_type: str = Field(description="Type: static (from tool) or semantic/novel")
    evidence: str = Field(description="Detailed reason or evidence for why these two constraints conflict under current conditions")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")

class ConstraintConflictAssessment(BaseModel):
    has_deadlock: bool = Field(description="True if any active deadlock/conflict is detected (either deterministic static pair or high-confidence novel semantic conflict)")
    conflicts: List[ConflictDetail] = Field(default_factory=list, description="List of detected conflicting constraint pairs with evidence and confidence")

async def after_predictor_callback(callback_context: CallbackContext) -> None:
    assessment = callback_context.output
    if isinstance(assessment, dict):
        assessment = ConstraintConflictAssessment.model_validate(assessment)
    elif not isinstance(assessment, ConstraintConflictAssessment):
        return
    
    deadlocks_list = []
    for c in assessment.conflicts:
        # High confidence novel conflicts (>= 0.7) or static deadlocks count as active deadlocks
        if c.conflict_type == "static" or c.confidence >= 0.7:
            deadlocks_list.append([c.constraint_a, c.constraint_b])
    
    # Persist detected deadlocks to session state
    callback_context.state["active_deadlocks"] = deadlocks_list
    
    if assessment.has_deadlock or deadlocks_list:
        callback_context.route = "deadlock"
        # Drop intentional velocity magnitude to 0 on deadlock
        intent = callback_context.state.get("intent_vector")
        if intent:
            heading = intent.heading_degrees if hasattr(intent, "heading_degrees") else intent.get("heading_degrees", 0.0)
            callback_context.state["intent_vector"] = StateVector2D(
                magnitude=0.0,
                heading_degrees=heading
            )
    else:
        callback_context.route = "no_deadlock"

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
    after_agent_callback=after_predictor_callback
)
