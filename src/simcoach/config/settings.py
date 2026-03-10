"""Configuration loading — merges config.yaml with .env overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv()


class LLMConfig(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    max_tokens: int = 2048
    temperature: float = 0.3
    api_key: str = ""


class RecorderConfig(BaseModel):
    sample_rate_hz: int = 25
    source: str = "mock"  # "ac_shared_memory" | "mock"
    output_dir: str = "output/sessions"


class ContextBuilderConfig(BaseModel):
    resample_points: int = 100   # points sent to LLM (keep small for token budget)
    chart_points: int = 1000     # points used in HTML chart (higher = more zoom detail)
    max_brake_events: int = 10
    max_gear_events: int = 15


class ReportConfig(BaseModel):
    output_dir: str = "output/reports"
    open_browser: bool = True


class ReferenceConfig(BaseModel):
    pb_dir: str = "output/pb_laps"


class AppConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    recorder: RecorderConfig = Field(default_factory=RecorderConfig)
    context_builder: ContextBuilderConfig = Field(default_factory=ContextBuilderConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    reference: ReferenceConfig = Field(default_factory=ReferenceConfig)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """
    Load configuration from:
    1. Built-in defaults (AppConfig defaults)
    2. config.yaml (if it exists)
    3. Environment variables (highest priority)

    Priority: env vars > config.yaml > defaults
    """
    raw: dict[str, Any] = {}

    # 1. Try to load YAML config
    if config_path is None:
        # Search common locations
        candidates = [
            Path("config.yaml"),
            Path("configs/config.yaml"),
        ]
        for candidate in candidates:
            if candidate.exists():
                config_path = candidate
                break

    if config_path and Path(config_path).exists():
        with open(config_path, encoding="utf-8") as f:
            file_data = yaml.safe_load(f) or {}
        raw = _deep_merge(raw, file_data)

    # 2. Apply environment variable overrides
    env_api_key = os.getenv("LLM_API_KEY", "")
    env_base_url = os.getenv("LLM_BASE_URL", "")
    env_model = os.getenv("LLM_MODEL", "")

    if env_api_key:
        raw.setdefault("llm", {})["api_key"] = env_api_key
    if env_base_url:
        raw.setdefault("llm", {})["base_url"] = env_base_url
    if env_model:
        raw.setdefault("llm", {})["model"] = env_model

    config = AppConfig.model_validate(raw)

    # If api_key still empty, try direct env read (handles case where dotenv wasn't loaded)
    if not config.llm.api_key:
        config.llm.api_key = os.environ.get("LLM_API_KEY", "")

    return config
