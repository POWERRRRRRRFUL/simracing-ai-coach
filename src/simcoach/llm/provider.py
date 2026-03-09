"""
LLM provider — thin wrapper around OpenAI-compatible REST API.

Designed to work with:
  - OpenAI          (https://api.openai.com/v1)
  - OpenRouter      (https://openrouter.ai/api/v1)
  - local Ollama    (http://localhost:11434/v1)
  - any other OpenAI-compatible endpoint

Uses httpx directly to avoid a mandatory openai dependency.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from simcoach.config.settings import LLMConfig


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

        Args:
            json_mode: Request ``response_format: {type: json_object}``.
                       Supported by OpenAI GPT-4o / GPT-4o-mini and compatible
                       providers.  For other endpoints the system prompt already
                       demands JSON so this is a best-effort hint.

        Raises:
            httpx.HTTPStatusError: if the API returns a 4xx/5xx response.
            ValueError: if the response cannot be parsed.
        """
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
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
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise ValueError(f"Unexpected API response format: {data}") from e

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "LLMProvider":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
