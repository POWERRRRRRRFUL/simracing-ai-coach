"""Tests for OpenAI-compatible provider payload construction and error handling."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import httpx
import pytest

from simcoach.config.settings import LLMConfig
from simcoach.llm.providers.openai_compatible import (
    ModelCapabilities,
    OpenAICompatibleProvider,
    _get_model_capabilities,
)


def _make_provider(model: str = "gpt-4o-mini", **kwargs) -> OpenAICompatibleProvider:
    """Create a provider with a given model name (no real HTTP client needed)."""
    config = LLMConfig(
        model=model,
        api_key="test-key",
        base_url="https://api.example.com/v1",
        max_tokens=2048,
        temperature=0.3,
        **kwargs,
    )
    return OpenAICompatibleProvider(config)


def _capture_payload(provider: OpenAICompatibleProvider, json_mode: bool = False) -> dict:
    """Call raw_complete with a mocked httpx client and return the sent payload."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "model": provider._config.model,
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider._client, "post", return_value=mock_response) as mock_post:
        provider.raw_complete("system", "user", json_mode=json_mode)
        _, call_kwargs = mock_post.call_args
        return call_kwargs["json"]


# ── Model capability detection ───────────────────────────────────────────────


class TestModelCapabilityDetection:
    def test_deepseek_reasoner(self):
        caps = _get_model_capabilities("deepseek-reasoner")
        assert caps.is_reasoning is True
        assert caps.supports_temperature is False
        assert caps.supports_max_tokens is False
        assert caps.supports_max_completion_tokens is True
        assert caps.supports_response_format is False

    def test_claude_think(self):
        caps = _get_model_capabilities("claude-3-5-sonnet-think")
        assert caps.is_reasoning is True
        assert caps.supports_temperature is False

    def test_thinking_variant(self):
        caps = _get_model_capabilities("some-model-thinking-v2")
        assert caps.is_reasoning is True

    def test_gpt54(self):
        caps = _get_model_capabilities("gpt-5.4")
        assert caps.is_reasoning is False
        assert caps.supports_temperature is False
        assert caps.supports_max_tokens is False
        assert caps.supports_max_completion_tokens is True
        assert caps.supports_response_format is False

    def test_gpt54_mini(self):
        caps = _get_model_capabilities("gpt-5.4-mini")
        assert caps.is_reasoning is False
        assert caps.supports_temperature is False
        assert caps.supports_max_completion_tokens is True

    def test_gpt54_pro_is_heavy(self):
        caps = _get_model_capabilities("gpt-5.4-pro")
        assert caps.is_reasoning is False
        assert caps.supports_temperature is False
        assert caps.min_max_tokens == 16384

    def test_gpt54_high(self):
        caps = _get_model_capabilities("gpt-5.4-high")
        assert caps.is_reasoning is False
        assert caps.supports_temperature is False
        assert caps.min_max_tokens == 16384

    def test_gpt54_nano_is_standard(self):
        caps = _get_model_capabilities("gpt-5.4-nano")
        assert caps.min_max_tokens == 0

    def test_normal_deepseek_chat(self):
        caps = _get_model_capabilities("deepseek-chat")
        assert caps == ModelCapabilities()
        assert caps.is_reasoning is False

    def test_normal_gpt4o(self):
        caps = _get_model_capabilities("gpt-4o-mini")
        assert caps == ModelCapabilities()

    def test_normal_claude(self):
        caps = _get_model_capabilities("claude-3-5-sonnet")
        assert caps == ModelCapabilities()


# ── Normal model payload ─────────────────────────────────────────────────────


class TestNormalModelPayload:
    def test_includes_temperature(self):
        p = _make_provider("deepseek-chat")
        payload = _capture_payload(p)
        assert payload["temperature"] == 0.3

    def test_includes_max_tokens(self):
        p = _make_provider("gpt-4o-mini")
        payload = _capture_payload(p)
        assert payload["max_tokens"] == 2048
        assert "max_completion_tokens" not in payload

    def test_json_mode_adds_response_format(self):
        p = _make_provider("gpt-4o-mini")
        payload = _capture_payload(p, json_mode=True)
        assert payload["response_format"] == {"type": "json_object"}

    def test_no_json_mode_no_response_format(self):
        p = _make_provider("gpt-4o-mini")
        payload = _capture_payload(p, json_mode=False)
        assert "response_format" not in payload


# ── Reasoning model payload ──────────────────────────────────────────────────


class TestReasoningModelPayload:
    def test_strips_temperature(self):
        p = _make_provider("deepseek-reasoner")
        payload = _capture_payload(p)
        assert "temperature" not in payload

    def test_uses_max_completion_tokens(self):
        p = _make_provider("deepseek-reasoner")
        payload = _capture_payload(p)
        assert payload["max_completion_tokens"] == 2048
        assert "max_tokens" not in payload

    def test_no_response_format_even_with_json_mode(self):
        p = _make_provider("deepseek-reasoner")
        payload = _capture_payload(p, json_mode=True)
        assert "response_format" not in payload

    def test_messages_still_present(self):
        p = _make_provider("claude-3-5-sonnet-think")
        payload = _capture_payload(p)
        assert payload["model"] == "claude-3-5-sonnet-think"
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"


# ── GPT-5.4 model payload ────────────────────────────────────────────────────


class TestGPT54Payload:
    def test_no_temperature(self):
        p = _make_provider("gpt-5.4-mini")
        payload = _capture_payload(p)
        assert "temperature" not in payload

    def test_uses_max_completion_tokens(self):
        p = _make_provider("gpt-5.4")
        payload = _capture_payload(p)
        assert payload["max_completion_tokens"] == 2048
        assert "max_tokens" not in payload

    def test_no_response_format_even_with_json_mode(self):
        p = _make_provider("gpt-5.4-pro")
        payload = _capture_payload(p, json_mode=True)
        assert "response_format" not in payload

    def test_messages_present(self):
        p = _make_provider("gpt-5.4-mini")
        payload = _capture_payload(p)
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"


# ── Token floor ──────────────────────────────────────────────────────────────


class TestTokenFloor:
    def test_heavy_model_raises_token_limit(self):
        p = _make_provider("gpt-5.4-high")  # default max_tokens=2048
        payload = _capture_payload(p)
        assert payload["max_completion_tokens"] == 16384

    def test_user_override_above_floor(self):
        config = LLMConfig(
            model="gpt-5.4-high",
            api_key="test-key",
            base_url="https://api.example.com/v1",
            max_tokens=32000,
            temperature=0.3,
        )
        p = OpenAICompatibleProvider(config)
        payload = _capture_payload(p)
        assert payload["max_completion_tokens"] == 32000

    def test_normal_model_unaffected(self):
        p = _make_provider("gpt-4o-mini")
        payload = _capture_payload(p)
        assert payload["max_tokens"] == 2048

    def test_standard_gpt54_unaffected(self):
        p = _make_provider("gpt-5.4-mini")
        payload = _capture_payload(p)
        assert payload["max_completion_tokens"] == 2048


# ── Transport retry ─────────────────────────────────────────────────────────


class TestTransportRetry:
    def test_retries_on_transport_error(self):
        p = _make_provider("deepseek-chat")
        mock_ok = MagicMock()
        mock_ok.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "model": "deepseek-chat",
        }
        mock_ok.raise_for_status = MagicMock()

        with patch.object(
            p._client,
            "post",
            side_effect=[httpx.ReadError("SSL: UNEXPECTED_EOF"), mock_ok],
        ):
            with patch("simcoach.llm.providers.openai_compatible.time.sleep"):
                result = p.raw_complete("system", "user")
        assert result["choices"][0]["message"]["content"] == "ok"

    def test_does_not_retry_http_status_error(self):
        p = _make_provider("deepseek-chat")
        mock_response = httpx.Response(
            status_code=400,
            request=httpx.Request(
                "POST", "https://api.example.com/v1/chat/completions"
            ),
            text='{"error": "bad request"}',
        )
        with patch.object(p._client, "post", return_value=mock_response):
            with pytest.raises(httpx.HTTPStatusError):
                p.raw_complete("system", "user")

    def test_raises_after_max_retries(self):
        p = _make_provider("deepseek-chat")
        with patch.object(
            p._client,
            "post",
            side_effect=httpx.ReadError("SSL: UNEXPECTED_EOF"),
        ):
            with patch("simcoach.llm.providers.openai_compatible.time.sleep"):
                with pytest.raises(httpx.ReadError):
                    p.raw_complete("system", "user")


# ── Error logging ────────────────────────────────────────────────────────────


class TestHTTPErrorLogging:
    def test_400_logs_response_body(self, caplog):
        p = _make_provider("deepseek-chat")

        error_body = '{"error": {"message": "temperature is not supported"}}'
        mock_response = httpx.Response(
            status_code=400,
            request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
            text=error_body,
        )

        with patch.object(p._client, "post", return_value=mock_response):
            with caplog.at_level(logging.ERROR):
                with pytest.raises(httpx.HTTPStatusError):
                    p.raw_complete("system", "user")

        assert "temperature is not supported" in caplog.text
        assert "400" in caplog.text

    def test_error_does_not_leak_api_key(self, caplog):
        p = _make_provider("deepseek-chat")

        mock_response = httpx.Response(
            status_code=401,
            request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
            text='{"error": "invalid api key"}',
        )

        with patch.object(p._client, "post", return_value=mock_response):
            with caplog.at_level(logging.ERROR):
                with pytest.raises(httpx.HTTPStatusError):
                    p.raw_complete("system", "user")

        # The log should contain the error body but NOT the api key
        assert "test-key" not in caplog.text
        assert "invalid api key" in caplog.text
