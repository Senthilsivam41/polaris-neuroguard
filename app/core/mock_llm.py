"""Deterministic offline stand-in for Gemini (OFFLINE_MODE / MOCK_MODE).

When the app runs without LLM connectivity or quota, each LlmAgent is given a
CannedResponseLlm that emits a fixed, schema-valid JSON payload. All symbolic
logic (static deadlock detection, path physics, HITL interception) still runs;
only the semantic LLM judgment is replaced with a permissive default.
"""
from typing import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types as genai_types


class CannedResponseLlm(BaseLlm):
    model: str = "offline-mock"
    canned_json: str

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        yield LlmResponse(
            content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text=self.canned_json)],
            ),
            partial=False,
            turn_complete=True,
        )
