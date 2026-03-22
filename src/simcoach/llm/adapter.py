"""Response extraction — normalizes provider-specific JSON into LLMResponse.

This is the single place where raw API payloads are inspected and converted
into the normalized ``LLMResponse`` that downstream code consumes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from simcoach.llm.types import LLMResponse

log = logging.getLogger(__name__)


def extract_response(
    data: dict[str, Any],
    provider_name: str = "",
) -> LLMResponse:
    """Extract a normalized ``LLMResponse`` from a raw API JSON payload.

    Supports (in priority order):
      1. ``choices[0].message.content`` — string, non-empty (standard OpenAI)
      2. ``choices[0].message.reasoning_content`` — when content is empty/None
         (DeepSeek reasoner)
      3. ``choices[0].message.content`` — list of content blocks
      4. ``choices[0].message.text`` — text-field variant
      5. Top-level ``data["text"]`` — rare local endpoints
      6. Raise ``ValueError``

    When both *content* and *reasoning_content* are present, *content* wins as
    ``final_text`` (DeepSeek puts the JSON answer there) and
    *reasoning_content* is stored in ``reasoning_text``.

    Raises:
        ValueError: when no text can be extracted from the response.
    """
    model = data.get("model", "")
    finish_reason = ""
    usage = data.get("usage", {}) or {}

    # ── choices-based extraction (OpenAI / DeepSeek / most providers) ─────
    choices = data.get("choices")
    if choices and isinstance(choices, list) and len(choices) > 0:
        choice = choices[0]
        finish_reason = choice.get("finish_reason", "") or ""
        message = choice.get("message") or {}

        content = message.get("content")
        reasoning = message.get("reasoning_content")

        content_text = _extract_text(content)
        reasoning_text = _extract_text(reasoning) if reasoning is not None else None

        # Determine final_text and source_field
        if content_text:
            final_text = content_text
            source_field = "content"
        elif reasoning_text:
            final_text = reasoning_text
            source_field = "reasoning_content"
        else:
            # Try message.text as variant
            text_field = message.get("text")
            if text_field and isinstance(text_field, str) and text_field.strip():
                final_text = text_field.strip()
                source_field = "message.text"
                reasoning_text = None
            else:
                final_text = ""
                source_field = ""

        if final_text:
            # When both exist, store reasoning separately
            if reasoning_text and reasoning_text == final_text:
                stored_reasoning = None
            else:
                stored_reasoning = reasoning_text

            log.debug(
                "LLM response extracted: source_field=%s, reasoning_present=%s, "
                "provider=%s, model=%s, finish_reason=%s",
                source_field,
                reasoning_text is not None,
                provider_name,
                model,
                finish_reason,
            )

            return LLMResponse(
                final_text=final_text,
                source_field=source_field,
                reasoning_text=stored_reasoning,
                provider_name=provider_name,
                model=model,
                raw_response=data,
                finish_reason=finish_reason,
                usage=usage,
            )

    # ── Fallback: top-level "text" field (some simple endpoints) ──────────
    if "text" in data and isinstance(data["text"], str) and data["text"].strip():
        log.debug(
            "LLM response extracted via top-level 'text' fallback: provider=%s",
            provider_name,
        )
        return LLMResponse(
            final_text=data["text"].strip(),
            source_field="text",
            provider_name=provider_name,
            model=model,
            raw_response=data,
            finish_reason=finish_reason,
            usage=usage,
        )

    # ── Nothing found ─────────────────────────────────────────────────────
    snippet = json.dumps(data, default=str)[:500]
    raise ValueError(f"Cannot extract text from API response: {snippet}")


def _extract_text(content: Any) -> str:
    """Normalize a content field to a plain string.

    Handles:
      - ``str`` → returned stripped
      - ``list`` of content blocks (``[{type, text}, ...]``) → concatenated
      - ``None`` / other → ``""``
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and "text" in block:
                    parts.append(block["text"])
                elif "text" in block:
                    parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return ""
