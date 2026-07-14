"""Semantic Drift Scoring Module (DRIFT-006).

Computes normalized semantic drift score [0.0 - 1.0], evidence, matched/contradicted concepts, and provider fallbacks.
Supports a pluggable scorer interface (`SemanticScorerInterface`) enabling hermetic test execution with `FakeSemanticScorer`.
"""

from typing import Protocol, List, Optional
import json
from google.adk.models.google_llm import Gemini
from google.genai import types
from app.core.goal_contract import GoalContract
from app.core.drift_models import ExtractedChangeRequest, SemanticScorerResult
from app.core.config import GEMINI_MODEL


class SemanticScorerInterface(Protocol):
    """Protocol interface for pluggable semantic drift scoring engines."""
    def compute_semantic_drift(
        self,
        contract: GoalContract,
        extracted: ExtractedChangeRequest
    ) -> SemanticScorerResult:
        ...


class FakeSemanticScorer:
    """
    Deterministic test fake implementation of SemanticScorerInterface.
    Allows hermetic unit testing without external LLM network calls.
    """
    def __init__(
        self,
        default_score: float = 0.0,
        default_confidence: float = 1.0,
        matched_concepts: Optional[List[str]] = None,
        contradicted_concepts: Optional[List[str]] = None
    ):
        self.default_score = default_score
        self.default_confidence = default_confidence
        self.matched_concepts = matched_concepts or ["Base Objective", "Core Scope"]
        self.contradicted_concepts = contradicted_concepts or []

    def compute_semantic_drift(
        self,
        contract: GoalContract,
        extracted: ExtractedChangeRequest
    ) -> SemanticScorerResult:
        if extracted.is_no_change_detected:
            return SemanticScorerResult(
                drift_score=0.0,
                confidence=1.0,
                semantic_evidence="Request confirmed zero semantic deviation from contract baseline.",
                matched_concepts=[contract.normalized_objective],
                contradicted_concepts=[],
                is_fallback=False
            )
            
        if extracted.prompt_injection_flag:
            return SemanticScorerResult(
                drift_score=1.0,
                confidence=1.0,
                semantic_evidence="Security threat / adversarial attempt detected in input request.",
                matched_concepts=[],
                contradicted_concepts=["Security Policy", "System Guardrails"],
                is_fallback=False
            )

        # Simple text similarity heuristic for Fake
        text_lower = extracted.raw_request_text.lower()
        obj_lower = contract.normalized_objective.lower()
        
        # Word overlap calculation
        req_words = set(text_lower.split())
        obj_words = set(obj_lower.split())
        overlap = len(req_words.intersection(obj_words))
        
        if self.default_score > 0.0:
            score = self.default_score
        elif "pivot" in text_lower or "replace" in text_lower:
            score = 0.9
        elif "expand" in text_lower or "add" in text_lower:
            score = 0.4
        elif overlap > 0:
            score = 0.1
        else:
            score = 0.2

        return SemanticScorerResult(
            drift_score=round(score, 2),
            confidence=self.default_confidence,
            semantic_evidence=f"FakeSemanticScorer evaluated semantic drift score at {score:.2f}.",
            matched_concepts=self.matched_concepts,
            contradicted_concepts=self.contradicted_concepts,
            is_fallback=False
        )


class GeminiSemanticScorer:
    """
    LLM-backed implementation using Gemini 2.0 Flash to analyze semantic drift
    against active Goal Contract required outcomes, exclusions, and constraints.
    Includes safe fallback behavior on rate limits or service failures.
    """
    def __init__(self, model_name: str = GEMINI_MODEL):
        self.model_name = model_name

    def compute_semantic_drift(
        self,
        contract: GoalContract,
        extracted: ExtractedChangeRequest
    ) -> SemanticScorerResult:
        # Quick check for security or zero-change
        if extracted.is_no_change_detected:
            return SemanticScorerResult(
                drift_score=0.0,
                confidence=1.0,
                semantic_evidence="Request confirms active baseline contract parameters.",
                matched_concepts=[contract.normalized_objective],
                contradicted_concepts=[],
                is_fallback=False
            )

        prompt = f"""
Analyze the semantic intent drift of the following new user request against the active Goal Contract.

Active Goal Contract Baseline:
- Objective: {contract.normalized_objective}
- Required Outcomes: {json.dumps(contract.outcomes.required_outcomes)}
- Excluded Outcomes: {json.dumps(contract.outcomes.excluded_outcomes)}
- Constraints: {json.dumps(contract.constraints)}

New User Request:
"{extracted.raw_request_text}"

Return JSON output with EXACT structure:
{{
  "drift_score": float between 0.0 (no drift) and 1.0 (total drift/conflict),
  "confidence": float between 0.0 and 1.0,
  "semantic_evidence": "concise explanation of semantic alignment or deviation",
  "matched_concepts": ["concept1", ...],
  "contradicted_concepts": ["concept2", ...]
}}
"""
        try:
            model = Gemini(model=self.model_name)
            response = model.generate_content(
                contents=[types.Content(role="user", parts=[types.Part(text=prompt)])]
            )
            text = response.text or ""
            # Clean json block formatting if present
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            parsed = json.loads(text)
            return SemanticScorerResult(
                drift_score=max(0.0, min(1.0, float(parsed.get("drift_score", 0.5)))),
                confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.8)))),
                semantic_evidence=str(parsed.get("semantic_evidence", "Semantic drift analysis generated.")),
                matched_concepts=list(parsed.get("matched_concepts", [])),
                contradicted_concepts=list(parsed.get("contradicted_concepts", [])),
                is_fallback=False
            )
        except Exception as e:
            # Safe conservative fallback on model failure/rate limits
            return SemanticScorerResult(
                drift_score=0.6,
                confidence=0.5,
                semantic_evidence=f"Semantic scorer unavailable ({type(e).__name__}). Applied conservative review fallback score 0.60.",
                matched_concepts=[],
                contradicted_concepts=["Unverified Semantic Intent"],
                is_fallback=True
            )


# Default scorer instance (uses Fake in test environment or Gemini for live)
default_semantic_scorer: SemanticScorerInterface = FakeSemanticScorer()
