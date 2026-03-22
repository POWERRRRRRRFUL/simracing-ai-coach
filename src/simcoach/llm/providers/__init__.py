"""Provider registry — factory for creating the appropriate LLM provider."""

from __future__ import annotations

from simcoach.config.settings import LLMConfig
from simcoach.llm.providers.base import BaseProvider
from simcoach.llm.providers.openai_compatible import OpenAICompatibleProvider


def create_provider(config: LLMConfig) -> BaseProvider:
    """Return the appropriate provider for the given configuration.

    Currently always returns ``OpenAICompatibleProvider``.
    Future providers (Anthropic native, Gemini, etc.) can be selected here
    based on ``config.base_url`` or a dedicated provider-type field.
    """
    return OpenAICompatibleProvider(config)


__all__ = ["BaseProvider", "OpenAICompatibleProvider", "create_provider"]
