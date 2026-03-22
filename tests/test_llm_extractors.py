"""Tests for LLM response extraction and normalization logic."""

from __future__ import annotations

import pytest

from simcoach.llm.adapter import _extract_text, extract_response
from simcoach.llm.types import LLMResponse


# ── _extract_text helper ─────────────────────────────────────────────────────


class TestExtractText:
    def test_string_content(self):
        assert _extract_text("hello world") == "hello world"

    def test_string_stripped(self):
        assert _extract_text("  hello  ") == "hello"

    def test_none_returns_empty(self):
        assert _extract_text(None) == ""

    def test_content_blocks(self):
        blocks = [
            {"type": "text", "text": "Part 1"},
            {"type": "text", "text": "Part 2"},
        ]
        assert _extract_text(blocks) == "Part 1\nPart 2"

    def test_blocks_without_type(self):
        blocks = [{"text": "fallback"}]
        assert _extract_text(blocks) == "fallback"

    def test_blocks_mixed_types(self):
        blocks = [
            {"type": "image", "url": "..."},
            {"type": "text", "text": "only this"},
        ]
        assert _extract_text(blocks) == "only this"

    def test_list_of_strings(self):
        assert _extract_text(["a", "b"]) == "a\nb"

    def test_empty_list(self):
        assert _extract_text([]) == ""

    def test_non_string_non_list(self):
        assert _extract_text(12345) == ""


# ── extract_response ─────────────────────────────────────────────────────────


class TestExtractResponse:
    def test_standard_openai(self):
        """Case A: standard OpenAI content string."""
        data = {
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "message": {"content": '{"best_lap_vs_reference": {}}'},
                    "finish_reason": "stop",
                }
            ],
        }
        result = extract_response(data)
        assert isinstance(result, LLMResponse)
        assert result.final_text == '{"best_lap_vs_reference": {}}'
        assert result.source_field == "content"
        assert result.reasoning_text is None
        assert result.model == "gpt-4o-mini"
        assert result.finish_reason == "stop"
        assert result.raw_response == data

    def test_deepseek_reasoner_both_fields(self):
        """Case B: DeepSeek with reasoning_content AND content."""
        data = {
            "model": "deepseek-reasoner",
            "choices": [
                {
                    "message": {
                        "reasoning_content": "Let me think step by step...",
                        "content": '{"best_lap_vs_reference": {"summary": "test"}}',
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        result = extract_response(data)
        # content wins as final_text
        assert result.final_text == '{"best_lap_vs_reference": {"summary": "test"}}'
        assert result.source_field == "content"
        # reasoning stored separately
        assert result.reasoning_text == "Let me think step by step..."

    def test_deepseek_reasoner_empty_content(self):
        """Case B variant: content is empty, reasoning has the answer."""
        data = {
            "model": "deepseek-reasoner",
            "choices": [
                {
                    "message": {
                        "reasoning_content": '{"best_lap_vs_reference": {}}',
                        "content": "",
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        result = extract_response(data)
        assert result.final_text == '{"best_lap_vs_reference": {}}'
        assert result.source_field == "reasoning_content"

    def test_deepseek_reasoner_content_none(self):
        """Case B variant: content is None, reasoning has the answer."""
        data = {
            "model": "deepseek-reasoner",
            "choices": [
                {
                    "message": {
                        "reasoning_content": "The answer is here",
                        "content": None,
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        result = extract_response(data)
        assert result.final_text == "The answer is here"
        assert result.source_field == "reasoning_content"

    def test_text_field_variant(self):
        """Case C: message has 'text' instead of 'content'."""
        data = {
            "model": "some-model",
            "choices": [
                {
                    "message": {"text": "response via text field"},
                    "finish_reason": "stop",
                }
            ],
        }
        result = extract_response(data)
        assert result.final_text == "response via text field"
        assert result.source_field == "message.text"

    def test_content_blocks_array(self):
        """Case D: Anthropic-style content blocks via proxy."""
        data = {
            "model": "claude-3",
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": '{"best_lap_vs_reference": {}}'},
                        ],
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        result = extract_response(data)
        assert result.final_text == '{"best_lap_vs_reference": {}}'
        assert result.source_field == "content"

    def test_top_level_text_fallback(self):
        """Rare endpoint returning top-level text field."""
        data = {"text": "some response", "model": "local-llm"}
        result = extract_response(data)
        assert result.final_text == "some response"
        assert result.source_field == "text"

    def test_empty_choices_raises(self):
        data = {"choices": [], "model": "test"}
        with pytest.raises(ValueError, match="Cannot extract text"):
            extract_response(data)

    def test_missing_content_raises(self):
        """message exists but has no extractable text field."""
        data = {"choices": [{"message": {}, "finish_reason": "stop"}]}
        with pytest.raises(ValueError, match="Cannot extract text"):
            extract_response(data)

    def test_no_choices_no_text_raises(self):
        data = {"model": "test", "usage": {"total_tokens": 100}}
        with pytest.raises(ValueError, match="Cannot extract text"):
            extract_response(data)

    def test_provider_name_passed_through(self):
        data = {
            "choices": [
                {"message": {"content": "x"}, "finish_reason": "stop"}
            ],
        }
        result = extract_response(data, provider_name="openai_compatible")
        assert result.provider_name == "openai_compatible"

    def test_usage_preserved(self):
        data = {
            "model": "gpt-4o",
            "choices": [
                {"message": {"content": "x"}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }
        result = extract_response(data)
        assert result.usage == {"prompt_tokens": 10, "completion_tokens": 20}


# ── LLMResponse model ────────────────────────────────────────────────────────


class TestLLMResponse:
    def test_minimal_construction(self):
        r = LLMResponse(final_text="hello")
        assert r.final_text == "hello"
        assert r.reasoning_text is None
        assert r.model == ""
        assert r.raw_response == {}
        assert r.finish_reason == ""
        assert r.source_field == ""
        assert r.usage == {}

    def test_full_construction(self):
        r = LLMResponse(
            final_text="answer",
            source_field="content",
            reasoning_text="thinking",
            provider_name="openai_compatible",
            model="test-model",
            raw_response={"key": "val"},
            finish_reason="stop",
            usage={"total_tokens": 50},
        )
        assert r.final_text == "answer"
        assert r.reasoning_text == "thinking"
        assert r.provider_name == "openai_compatible"
        assert r.usage == {"total_tokens": 50}

    def test_serialization_roundtrip(self):
        r = LLMResponse(final_text="test", model="m", source_field="content")
        d = r.model_dump()
        r2 = LLMResponse.model_validate(d)
        assert r2.final_text == "test"
        assert r2.model == "m"
        assert r2.source_field == "content"
