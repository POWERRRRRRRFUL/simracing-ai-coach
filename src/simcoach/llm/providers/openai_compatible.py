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

import dataclasses
import logging
import time
from typing import Any

import httpx

from simcoach.config.settings import LLMConfig
from simcoach.llm.providers.base import BaseProvider

log = logging.getLogger(__name__)

_MAX_TRANSPORT_RETRIES = 2  # total attempts = _MAX_TRANSPORT_RETRIES + 1


# ── Model capability layer ───────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class ModelCapabilities:
    """Describes which API parameters a model accepts."""

    supports_temperature: bool = True
    supports_max_tokens: bool = True
    supports_max_completion_tokens: bool = False
    supports_response_format: bool = True
    is_reasoning: bool = False
    min_max_tokens: int = 0  # token-limit floor for heavy reasoning models


_REASONING_CAPS = ModelCapabilities(
    supports_temperature=False,
    supports_max_tokens=False,
    supports_max_completion_tokens=True,
    supports_response_format=False,
    is_reasoning=True,
)

_GPT54_CAPS = ModelCapabilities(
    supports_temperature=False,
    supports_max_tokens=False,
    supports_max_completion_tokens=True,
    supports_response_format=False,
    is_reasoning=False,
)

_GPT54_HEAVY_CAPS = ModelCapabilities(
    supports_temperature=False,
    supports_max_tokens=False,
    supports_max_completion_tokens=True,
    supports_response_format=False,
    is_reasoning=False,
    min_max_tokens=16384,
)

_DEFAULT_CAPS = ModelCapabilities()


def _get_model_capabilities(model: str) -> ModelCapabilities:
    """Determine API capabilities based on model name."""
    name = model.lower()

    # GPT-5.4 heavy reasoning variants: need a larger token budget floor.
    if name.startswith("gpt-5.4-high") or name.startswith("gpt-5.4-pro"):
        return _GPT54_HEAVY_CAPS

    # GPT-5.4 standard variants.
    if name.startswith("gpt-5.4"):
        return _GPT54_CAPS

    # Reasoning / thinking models.
    if "reasoner" in name or "-think" in name or "thinking" in name:
        return _REASONING_CAPS

    return _DEFAULT_CAPS


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
    # Public API
    # ------------------------------------------------------------------

    def raw_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        """POST to ``/chat/completions`` and return the raw JSON response dict."""
        caps = _get_model_capabilities(self._config.model)

        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        # Token limit parameter (apply model-specific floor if set).
        token_limit = max(self._config.max_tokens, caps.min_max_tokens)
        if caps.min_max_tokens and token_limit > self._config.max_tokens:
            log.debug(
                "Token limit raised from %d to %d (model floor for %s)",
                self._config.max_tokens,
                token_limit,
                self._config.model,
            )

        if caps.supports_max_completion_tokens:
            payload["max_completion_tokens"] = token_limit
        elif caps.supports_max_tokens:
            payload["max_tokens"] = token_limit

        # Sampling temperature.
        if caps.supports_temperature:
            payload["temperature"] = self._config.temperature

        # Structured output format.
        if json_mode and caps.supports_response_format:
            payload["response_format"] = {"type": "json_object"}

        log.debug(
            "LLM request: model=%s, base_url=%s, json_mode=%s, "
            "capabilities=%s, payload_keys=%s",
            self._config.model,
            self._config.base_url,
            json_mode,
            caps,
            sorted(payload.keys()),
        )

        # Retry loop for transient transport errors (SSL, connection reset, …).
        for attempt in range(_MAX_TRANSPORT_RETRIES + 1):
            try:
                response = self._client.post("/chat/completions", json=payload)
                break
            except httpx.TransportError as exc:
                if attempt < _MAX_TRANSPORT_RETRIES:
                    wait = 2**attempt  # 1 s, 2 s
                    log.debug(
                        "Transport error (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1,
                        _MAX_TRANSPORT_RETRIES + 1,
                        wait,
                        exc,
                    )
                    time.sleep(wait)
                else:
                    log.error(
                        "Transport error after %d attempts — model=%s, "
                        "base_url=%s: %s",
                        _MAX_TRANSPORT_RETRIES + 1,
                        self._config.model,
                        self._config.base_url,
                        exc,
                    )
                    raise

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
