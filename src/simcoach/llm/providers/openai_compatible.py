"""OpenAI-compatible provider — httpx-based transport.

Works with any endpoint that implements the ``/chat/completions`` API:
  - OpenAI          (https://api.openai.com/v1)
  - DeepSeek        (https://api.deepseek.com/v1)
  - OpenRouter      (https://openrouter.ai/api/v1)
  - local Ollama    (http://localhost:11434/v1)
  - any other OpenAI-compatible endpoint

Uses httpx directly to avoid a mandatory openai SDK dependency.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from simcoach.config.settings import LLMConfig
from simcoach.llm.providers.base import BaseProvider

log = logging.getLogger(__name__)

# Model-name substrings that indicate a reasoning / thinking model.
# These models reject standard sampling parameters (temperature, top_p, etc.)
# and use ``max_completion_tokens`` instead of ``max_tokens``.
_REASONING_TAGS = ("reasoner", "-think", "thinking")


class OpenAICompatibleProvider(BaseProvider):
    """Sends chat completion requests to an OpenAI-compatible API."""

    PROVIDER_NAME = "openai_compatible"

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_reasoning_model(self) -> bool:
        """Detect reasoning/thinking models that reject standard sampling params."""
        model = self._config.model.lower()
        return any(tag in model for tag in _REASONING_TAGS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def raw_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        """POST to ``/chat/completions`` and return the raw JSON response dict."""
        reasoning_mode = self._is_reasoning_model()

        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        if reasoning_mode:
            # Reasoning models: minimal payload — no temperature, no response_format.
            # Use max_completion_tokens (OpenAI o-series / DeepSeek reasoner naming).
            payload["max_completion_tokens"] = self._config.max_tokens
            log.debug(
                "Reasoning-model mode: stripped temperature, response_format; "
                "using max_completion_tokens=%d",
                self._config.max_tokens,
            )
        else:
            # Normal models: include all parameters.
            payload["max_tokens"] = self._config.max_tokens
            payload["temperature"] = self._config.temperature
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

        log.debug(
            "LLM request: model=%s, base_url=%s, json_mode=%s, "
            "reasoning_mode=%s, payload_keys=%s",
            self._config.model,
            self._config.base_url,
            json_mode,
            reasoning_mode,
            sorted(payload.keys()),
        )

        response = self._client.post("/chat/completions", json=payload)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text
            log.error(
                "LLM API error %s %s — model=%s, base_url=%s\nResponse body: %s",
                exc.response.status_code,
                exc.response.reason_phrase,
                self._config.model,
                self._config.base_url,
                body,
            )
            raise

        return response.json()

    def close(self) -> None:
        self._client.close()
