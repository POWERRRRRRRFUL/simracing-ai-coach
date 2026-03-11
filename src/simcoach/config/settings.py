"""Configuration loading — config.yaml wins over .env / env vars."""

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
    library_dir: str = "output/references"
    trace_points: int = 1000


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
    """Load configuration.

    Priority (highest wins):
        config.yaml non-empty values  >  env vars / .env  >  built-in defaults

    config.yaml always wins for any LLM credential it explicitly sets to a
    non-empty value.  Env vars (.env or shell) are used only as a fallback when
    config.yaml has no value for that field.

    This guarantees that credentials saved through the GUI persist across
    restarts and are never silently overridden by a stale .env file.
    """
    resolved_path: Path | None = None

    # ── 1. Find and read config.yaml ─────────────────────────────────────────
    if config_path is None:
        for candidate in [Path("config.yaml"), Path("configs/config.yaml")]:
            if candidate.exists():
                config_path = candidate
                break

    yaml_data: dict[str, Any] = {}
    if config_path and Path(config_path).exists():
        resolved_path = Path(config_path)
        with open(resolved_path, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}

    # ── 2. Start from yaml data (highest priority) ────────────────────────────
    raw = dict(yaml_data)

    # ── 3. Apply env vars only for LLM fields absent/empty in config.yaml ────
    yaml_llm = yaml_data.get("llm", {})
    env_api_key = os.getenv("LLM_API_KEY", "")
    env_base_url = os.getenv("LLM_BASE_URL", "")
    env_model = os.getenv("LLM_MODEL", "")

    env_applied: list[str] = []
    yaml_wins: list[str] = []
    llm_raw: dict = dict(raw.get("llm", {}))

    for field, env_val in [
        ("api_key", env_api_key),
        ("base_url", env_base_url),
        ("model", env_model),
    ]:
        yaml_val = yaml_llm.get(field, "")
        if yaml_val:
            # config.yaml has an explicit non-empty value — it wins
            if env_val and env_val != yaml_val:
                yaml_wins.append(field)
        elif env_val:
            # config.yaml field absent/empty — use env var as fallback
            llm_raw[field] = env_val
            env_applied.append(field)

    if llm_raw:
        raw["llm"] = llm_raw

    config = AppConfig.model_validate(raw)

    # ── Logging ───────────────────────────────────────────────────────────────
    if resolved_path:
        print(f"[config] Loaded: {resolved_path.resolve()}")
    else:
        print("[config] No config.yaml found — using built-in defaults + env vars")

    if env_applied:
        print(f"[config] Env var fallback applied for: {', '.join(env_applied)}")
    if yaml_wins:
        print(f"[config] config.yaml overrides env var for: {', '.join(yaml_wins)}")

    return config


def save_config(config: AppConfig, config_path: str | Path = "config.yaml") -> None:
    """Serialize AppConfig back to YAML file."""
    path = Path(config_path)
    data = config.model_dump()
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"[config] Saved: {path.resolve()}")
