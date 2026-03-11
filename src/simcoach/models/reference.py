"""Portable .simcoachref reference lap format — models and conversion utilities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from simcoach.models.telemetry import Lap, LapStats, ReferenceLap, Session, TelemetryFrame
from simcoach.utils.sampling import compute_lap_stats, resample_trace


class ReferenceMetadata(BaseModel):
    """Metadata envelope for a .simcoachref file."""

    car_id: str
    track_id: str
    sim: str = "assetto_corsa"
    lap_time_ms: int
    session_id: str
    created_at: str  # ISO-8601
    source: str = "personal_best"  # "personal_best" | "imported" | "community"
    driver_name: str = ""


class ReferenceTrace(BaseModel):
    """Columnar pre-resampled trace data."""

    model_config = ConfigDict(populate_by_name=True)

    n_points: int
    pos: list[float]
    spd: list[float]
    thr: list[float]
    brk: list[float]
    str_: list[float] = Field(alias="str")
    gear: list[int]
    rpm: list[float]
    wx: list[float | None]
    wz: list[float | None]

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Override to always use 'str' as the key (not 'str_')."""
        kwargs.setdefault("by_alias", True)
        return super().model_dump(**kwargs)


class SimcoachReference(BaseModel):
    """Top-level .simcoachref file model."""

    simcoach_version: str = "0.1.0"
    format_version: int = 1
    type: str = "reference_lap"
    metadata: ReferenceMetadata
    stats: LapStats
    trace: ReferenceTrace

    # ── Conversion helpers ────────────────────────────────────────────────────

    def to_trace_dicts(self) -> list[dict[str, Any]]:
        """Convert columnar trace back to row-based dicts (for ContextBuilder)."""
        t = self.trace
        return [
            {
                "pos": t.pos[i],
                "spd": t.spd[i],
                "thr": t.thr[i],
                "brk": t.brk[i],
                "str": t.str_[i],
                "gear": t.gear[i],
                "rpm": t.rpm[i],
                "wx": t.wx[i],
                "wz": t.wz[i],
            }
            for i in range(t.n_points)
        ]

    @classmethod
    def from_reference_lap(
        cls, ref: ReferenceLap, trace_points: int = 1000
    ) -> SimcoachReference:
        """Create from a legacy ReferenceLap (resamples frames to columnar trace)."""
        if ref.stats is None and ref.frames:
            ref.stats = compute_lap_stats(ref.frames)

        trace_dicts = resample_trace(ref.frames, trace_points) if ref.frames else []
        trace = _trace_from_dicts(trace_dicts, trace_points)

        return cls(
            metadata=ReferenceMetadata(
                car_id=ref.car_id,
                track_id=ref.track_id,
                lap_time_ms=ref.lap_time_ms,
                session_id=ref.session_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                source=ref.source,
            ),
            stats=ref.stats,
            trace=trace,
        )

    @classmethod
    def from_lap(
        cls,
        session: Session,
        lap: Lap,
        trace_points: int = 1000,
        source: str = "personal_best",
        driver_name: str = "",
    ) -> SimcoachReference:
        """Create from a session lap directly."""
        stats = lap.stats
        if stats is None and lap.frames:
            stats = compute_lap_stats(lap.frames)

        trace_dicts = resample_trace(lap.frames, trace_points) if lap.frames else []
        trace = _trace_from_dicts(trace_dicts, trace_points)

        return cls(
            metadata=ReferenceMetadata(
                car_id=session.car_id,
                track_id=session.track_id,
                lap_time_ms=lap.lap_time_ms,
                session_id=session.session_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                source=source,
                driver_name=driver_name,
            ),
            stats=stats,
            trace=trace,
        )


def _trace_from_dicts(trace_dicts: list[dict], n_points: int) -> ReferenceTrace:
    """Build a columnar ReferenceTrace from row-based dicts."""
    if not trace_dicts:
        return ReferenceTrace(
            n_points=0, pos=[], spd=[], thr=[], brk=[],
            str_=[], gear=[], rpm=[], wx=[], wz=[],
        )
    return ReferenceTrace(
        n_points=len(trace_dicts),
        pos=[p["pos"] for p in trace_dicts],
        spd=[p["spd"] for p in trace_dicts],
        thr=[p["thr"] for p in trace_dicts],
        brk=[p["brk"] for p in trace_dicts],
        str_=[p["str"] for p in trace_dicts],
        gear=[p["gear"] for p in trace_dicts],
        rpm=[p["rpm"] for p in trace_dicts],
        wx=[p.get("wx") for p in trace_dicts],
        wz=[p.get("wz") for p in trace_dicts],
    )
