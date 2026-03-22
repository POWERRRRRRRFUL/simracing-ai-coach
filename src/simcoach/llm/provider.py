"""
LLM provider — thin wrapper around OpenAI-compatible REST API.

Designed to work with:
  - OpenAI          (https://api.openai.com/v1)
  - OpenRouter      (https://openrouter.ai/api/v1)
  - local Ollama    (http://localhost:11434/v1)
  - any other OpenAI-compatible endpoint

Uses httpx directly to avoid a mandatory openai dependency.

Reasoning model support (e.g. deepseek-reasoner):
  - ``reasoning_content`` (chain-of-thought) is NEVER used as report input.
  - Only ``content`` (the final answer) is returned to callers.
  - If ``content`` is empty, a single retry is attempted with an explicit
    "return JSON only" instruction before raising ValueError.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from simcoach.config.settings import LLMConfig

_log = logging.getLogger("simcoach.llm")


class LLMProvider:
    """Makes chat completion requests to an OpenAI-compatible API."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> str:
        """
        Send a chat completion request and return the assistant message content.

        For reasoning models the response may contain ``reasoning_content``
        (chain-of-thought) alongside ``content`` (final answer).  Only
        ``content`` is used; ``reasoning_content`` is logged for diagnostics
        but never returned.

        If ``content`` is empty on the first attempt, one automatic retry is
        made with an explicit "return JSON only" instruction appended.

        Args:
            json_mode: Request ``response_format: {type: json_object}``.
                       Supported by OpenAI GPT-4o / GPT-4o-mini and compatible
                       providers.  For other endpoints the system prompt already
                       demands JSON so this is a best-effort hint.

        Raises:
            httpx.HTTPStatusError: if the API returns a 4xx/5xx response.
            ValueError: if the response cannot be parsed or content is empty.
        """
        last_error: ValueError | None = None

        for attempt in range(2):
            prompt = user_prompt
            if attempt == 1:
                _log.info("[llm] retrying with explicit final-answer instruction")
                prompt = user_prompt + (
                    "\n\nIMPORTANT: Return only the final JSON answer. "
                    "Do not include reasoning or chain-of-thought."
                )

            payload: dict[str, Any] = {
                "model": self._config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": prompt},
                ],
                "max_tokens": self._config.max_tokens,
                "temperature": self._config.temperature,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            response = self._client.post("/chat/completions", json=payload)
            response.raise_for_status()

            data = response.json()
            try:
                return self._extract_content(data)
            except ValueError as exc:
                last_error = exc
                if attempt == 0:
                    continue
                raise

        # Should not reach here, but satisfy type checker
        assert last_error is not None
        raise last_error

    # ── Response extraction ──────────────────────────────────────────────────

    def _extract_content(self, data: dict[str, Any]) -> str:
        """Extract the final answer from an API response.

        For reasoning models (e.g. deepseek-reasoner) the response includes
        ``reasoning_content`` (internal chain-of-thought).  This field is
        logged but NEVER used as report input — only ``content`` (the final
        answer) is returned.
        """
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            raise ValueError(f"Unexpected API response format: {data}") from e

        model = self._config.model
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""

        _log.info("[llm] model=%s", model)
        _log.info("[llm] content len=%d", len(content))
        if reasoning:
            _log.info("[llm] reasoning_content len=%d (chain-of-thought, ignored)", len(reasoning))

        content = content.strip()

        if content:
            _log.info("[llm] using content (final answer)")
            return content

        # content is empty — this is an error, NOT a fallback to reasoning_content
        if reasoning:
            _log.warning(
                "[llm] ERROR: content empty but reasoning_content present "
                "(len=%d). reasoning_content is chain-of-thought, NOT the "
                "final answer — refusing to use it.",
                len(reasoning),
            )

        raise ValueError(
            f"LLM returned empty content (model={model}). "
            f"reasoning_content={'present' if reasoning else 'absent'}. "
            "The model may not have produced a final answer."
        )

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "LLMProvider":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
