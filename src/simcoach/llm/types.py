"""Normalized LLM response model.

All downstream code (report generation, GUI, CLI) should consume
``LLMResponse.final_text`` instead of parsing raw provider payloads.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    """Provider-agnostic normalized response from an LLM completion call."""

    final_text: str = Field(
        ...,
        description="Extracted assistant content for downstream use. "
        "For standard providers this is message.content; for reasoning "
        "models this may come from reasoning_content.",
    )
    source_field: str = Field(
        default="",
        description="Which response field produced final_text "
        "(e.g. 'content', 'reasoning_content', 'text').",
    )
    reasoning_text: str | None = Field(
        default=None,
        description="Chain-of-thought / reasoning content when the model "
        "provides it separately (e.g. DeepSeek reasoner).",
    )
    provider_name: str = Field(
        default="",
        description="Provider implementation that handled the request "
        "(e.g. 'openai_compatible').",
    )
    model: str = Field(
        default="",
        description="Model identifier echoed back from the API response.",
    )
    raw_response: dict[str, Any] = Field(
        default_factory=dict,
        description="Complete raw JSON response from the API, for debugging.",
    )
    finish_reason: str = Field(
        default="",
        description="Why generation stopped (e.g. 'stop', 'length').",
    )
    usage: dict[str, Any] = Field(
        default_factory=dict,
        description="Token usage information if present in response.",
    )
