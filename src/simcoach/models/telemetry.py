"""Core data models for simcoach using Pydantic v2."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


# ─── Raw telemetry ────────────────────────────────────────────────────────────

class TelemetryFrame(BaseModel):
    """A single sample captured from the telemetry source."""

    timestamp: float = Field(..., description="Unix timestamp of this sample (seconds)")
    lap_id: int = Field(..., description="Lap number (0-indexed within the session)")

    # Position on track, 0.0 = start/finish, 1.0 = end of lap
    normalized_track_position: float = Field(..., ge=0.0, le=1.0)

    # Core channels — all values normalised to driver-friendly ranges
    speed_kmh: float = Field(..., ge=0.0)
    throttle: float = Field(..., ge=0.0, le=1.0, description="0 = no throttle, 1 = full throttle")
    brake: float = Field(..., ge=0.0, le=1.0, description="0 = no brake, 1 = full brake")
    steering: float = Field(..., ge=-1.0, le=1.0, description="-1 = full left, 1 = full right")
    gear: int = Field(..., ge=-1, description="-1=Reverse, 0=Neutral, 1+=gears")
    rpm: float = Field(..., ge=0.0)
    clutch: float = Field(0.0, ge=0.0, le=1.0)

    # Extended channels (optional, filled when AC shared memory is available)
    g_lat: float | None = Field(None, description="Lateral G-force")
    g_lon: float | None = Field(None, description="Longitudinal G-force")
    tyre_slip_fl: float | None = None
    tyre_slip_fr: float | None = None
    tyre_slip_rl: float | None = None
    tyre_slip_rr: float | None = None
    abs_active: bool = False
    tc_active: bool = False

    # World position (AC coordinate system: X=lateral, Y=elevation, Z=longitudinal)
    # Populated by AC SHM source and mock source; None for old sessions / unsupported sources.
    world_pos_x: float | None = Field(None)
    world_pos_y: float | None = Field(None)
    world_pos_z: float | None = Field(None)

    model_config = ConfigDict(extra="ignore")


# ─── Lap ─────────────────────────────────────────────────────────────────────

class LapStats(BaseModel):
    """Derived statistics for a single lap."""
    max_speed_kmh: float
    avg_speed_kmh: float
    max_throttle: float
    avg_throttle: float
    max_brake: float
    avg_brake: float
    max_steering_abs: float
    avg_steering_abs: float
    full_throttle_pct: float = Field(..., description="Fraction of lap at >95% throttle")
    heavy_brake_pct: float = Field(..., description="Fraction of lap at >80% brake")
    gear_changes: int
    abs_events: int
    tc_events: int


class Lap(BaseModel):
    """All data for a single timed lap."""

    lap_id: int
    lap_time_ms: int = Field(..., description="Lap time in milliseconds, -1 if invalid")
    is_valid: bool = True
    complete: bool = Field(
        True,
        description="True when the lap completed a full start/finish crossing cycle. "
                    "False for the initial partial segment (prologue) and the final "
                    "incomplete segment when recording stops mid-lap.",
    )
    frames: list[TelemetryFrame] = Field(default_factory=list)
    stats: LapStats | None = None

    @property
    def lap_time_s(self) -> float:
        return self.lap_time_ms / 1000.0

    @property
    def lap_time_str(self) -> str:
        if self.lap_time_ms <= 0:
            return "invalid"
        total_s = self.lap_time_ms / 1000.0
        minutes = int(total_s // 60)
        seconds = total_s % 60
        return f"{minutes}:{seconds:06.3f}"


# ─── Session ─────────────────────────────────────────────────────────────────

class Session(BaseModel):
    """A complete recorded session."""

    session_id: str
    car_id: str
    track_id: str
    recorded_at: str = Field(..., description="ISO-8601 datetime string")
    source: str = Field("unknown", description="'ac_shared_memory' or 'mock'")

    laps: list[Lap] = Field(default_factory=list)

    # Raw frames before lap segmentation (used during recording)
    raw_frames: list[TelemetryFrame] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


# ─── Reference lap ───────────────────────────────────────────────────────────

class ReferenceLap(BaseModel):
    """A reference lap used for comparison (personal best or session best)."""

    source: str = Field(..., description="'personal_best' or 'session_best'")
    car_id: str
    track_id: str
    lap_time_ms: int
    session_id: str
    frames: list[TelemetryFrame] = Field(default_factory=list)
    stats: LapStats | None = None

    @property
    def lap_time_str(self) -> str:
        total_s = self.lap_time_ms / 1000.0
        minutes = int(total_s // 60)
        seconds = total_s % 60
        return f"{minutes}:{seconds:06.3f}"


# ─── LLM context ─────────────────────────────────────────────────────────────

class LapContextEntry(BaseModel):
    """Condensed representation of a lap for LLM consumption."""
    lap_id: int
    lap_time_str: str
    is_best: bool = False
    is_reference: bool = False
    stats: LapStats
    # Resampled trace — list of {pos, speed, throttle, brake, steering, gear, rpm}
    trace: list[dict[str, Any]] = Field(default_factory=list)


class LLMAnalysisContext(BaseModel):
    """The structured context passed to the LLM for analysis."""

    car_id: str
    track_id: str
    session_id: str
    session_date: str
    total_laps: int
    valid_laps: int

    best_lap: LapContextEntry
    reference_lap: LapContextEntry | None = None
    all_lap_summaries: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Light summary of all laps (lap_id, time, valid)"
    )

    delta_vs_reference_ms: int | None = Field(
        None, description="best_lap_time - reference_lap_time in ms"
    )


# ─── Report ──────────────────────────────────────────────────────────────────

class AnalysisReport(BaseModel):
    """Final output combining telemetry context and LLM response."""

    session_id: str
    car_id: str
    track_id: str
    session_date: str
    best_lap_time_str: str
    reference_lap_time_str: str | None = None
    delta_vs_reference_str: str | None = None

    llm_model: str
    llm_raw_response: str

    # Structured sections — populated when LLM returns valid JSON.
    # Schema mirrors the four-section JSON contract defined in prompts.py.
    structured_analysis: dict[str, Any] = Field(default_factory=dict)

    # Legacy flat-string fields kept for backward-compat / no-API fallback.
    # When structured_analysis is present these are populated from it too.
    best_vs_reference_analysis: str = ""
    session_findings: str = ""
    coaching_summary: str = ""
    next_training_focus: str = ""

    # High-resolution traces for the HTML chart (independent of LLM context).
    # Keys: "best" (list of point dicts), "reference" (list or None).
    # When present, render_html() uses these instead of the low-res context_json traces.
    chart_traces: dict[str, Any] = Field(default_factory=dict)

    # The context that was sent to LLM (for transparency / debugging)
    context_json: dict[str, Any] = Field(default_factory=dict)
