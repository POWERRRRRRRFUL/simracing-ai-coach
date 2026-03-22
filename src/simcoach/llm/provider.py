"""LLM provider facade.

Public entry point for all LLM calls.  Delegates HTTP transport to a
concrete provider (see ``providers/``) and normalizes the raw response
via the adapter layer into an ``LLMResponse``.
"""

from __future__ import annotations

from typing import Any

from simcoach.config.settings import LLMConfig
from simcoach.llm.adapter import extract_response
from simcoach.llm.providers import create_provider
from simcoach.llm.types import LLMResponse


class LLMProvider:
    """Facade: sends chat completion requests and returns normalized responses."""

    def __init__(self, config: LLMConfig) -> None:
        self._provider = create_provider(config)

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Send a chat completion request and return a normalized ``LLMResponse``.

        Args:
            json_mode: Request ``response_format: {type: json_object}``.
                       Supported by OpenAI GPT-4o / GPT-4o-mini and compatible
                       providers.  For other endpoints the system prompt already
                       demands JSON so this is a best-effort hint.

        Raises:
            httpx.HTTPStatusError: if the API returns a 4xx/5xx response.
            ValueError: if the response cannot be parsed.
        """
        raw = self._provider.raw_complete(system_prompt, user_prompt, json_mode)
        return extract_response(raw, provider_name=self._provider.PROVIDER_NAME)

    def close(self) -> None:
        self._provider.close()

    def __enter__(self) -> LLMProvider:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
