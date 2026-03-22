"""Abstract base for LLM providers.

Each provider handles HTTP transport to a specific API shape.
Providers return raw response dicts — normalization into ``LLMResponse``
is handled by the adapter layer, not by the provider itself.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):
    """Abstract interface for LLM provider implementations."""

    PROVIDER_NAME: str = "base"

    @abstractmethod
    def raw_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        """Send a completion request and return the raw API response as a dict.

        Raises:
            httpx.HTTPStatusError: if the API returns a 4xx/5xx response.
        """

    def close(self) -> None:
        """Release any resources held by the provider."""

    def __enter__(self) -> BaseProvider:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
