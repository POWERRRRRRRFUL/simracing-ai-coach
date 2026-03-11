"""
Telemetry Context Builder — the core data pipeline.

Responsibilities:
1. Parse and clean a session (filter invalid / very short laps)
2. Select the best lap (lowest valid lap time)
3. Accept an optional reference lap for comparison
4. Resample both laps to N evenly-spaced points
5. Compute per-lap statistics
6. Assemble a structured LLMAnalysisContext

The goal is NOT to diagnose driving problems — that's the LLM's job.
The goal is to produce clean, compact, human-readable context.
"""

from __future__ import annotations

import json
from typing import Any

from simcoach.models.reference import SimcoachReference
from simcoach.models.telemetry import (
    Lap,
    LapContextEntry,
    LLMAnalysisContext,
    ReferenceLap,
    Session,
)
from simcoach.utils.sampling import compute_lap_stats, resample_trace


def _extract_pos_arrays(trace: list[dict]) -> dict:
    """Extract world position arrays from a resampled trace.

    Returns {"x": [...], "z": [...]} or {"x": None, "z": None} when the trace
    has no position data (old sessions recorded before this feature).
    """
    xs = [p.get("wx") for p in trace]
    zs = [p.get("wz") for p in trace]
    if all(v is None for v in xs):
        return {"x": None, "z": None}
    return {"x": xs, "z": zs}


class ContextBuilder:
    """Transforms a Session (and optional ReferenceLap) into an LLMAnalysisContext."""

    def __init__(
        self,
        resample_points: int = 100,
    ) -> None:
        self._n_points = resample_points

    # ── Public API ────────────────────────────────────────────────────────────

    def build(
        self,
        session: Session,
        reference_lap: ReferenceLap | SimcoachReference | None = None,
    ) -> LLMAnalysisContext:
        """
        Build the LLM context from a session.

        Args:
            session:       Recorded session with laps and frames.
            reference_lap: Optional reference (ReferenceLap or SimcoachReference).

        Returns:
            LLMAnalysisContext ready to be serialised as JSON for the LLM prompt.
        """
        valid_laps = self._filter_valid_laps(session.laps)
        if not valid_laps:
            raise ValueError("Session has no valid laps to analyse.")

        # Ensure all laps have stats computed
        for lap in valid_laps:
            if lap.stats is None and lap.frames:
                lap.stats = compute_lap_stats(lap.frames)

        best_lap = self._select_best_lap(valid_laps)
        best_entry = self._build_lap_entry(best_lap, is_best=True)

        ref_entry: LapContextEntry | None = None
        delta_ms: int | None = None

        if reference_lap is not None:
            ref_time_ms = _ref_lap_time_ms(reference_lap)
            ref_entry = self._build_reference_entry(reference_lap)
            delta_ms = best_lap.lap_time_ms - ref_time_ms

        all_summaries = self._build_lap_summaries(valid_laps, best_lap.lap_id)

        return LLMAnalysisContext(
            car_id=session.car_id,
            track_id=session.track_id,
            session_id=session.session_id,
            session_date=session.recorded_at,
            total_laps=len(session.laps),
            valid_laps=len(valid_laps),
            best_lap=best_entry,
            reference_lap=ref_entry,
            all_lap_summaries=all_summaries,
            delta_vs_reference_ms=delta_ms,
        )

    def to_json(self, context: LLMAnalysisContext) -> str:
        """Serialise context to compact JSON string for inclusion in LLM prompt."""
        return json.dumps(context.model_dump(), indent=2)

    def build_chart_traces(
        self,
        session: Session,
        reference_lap: ReferenceLap | SimcoachReference | None = None,
        chart_points: int = 1000,
    ) -> dict[str, list | None]:
        """
        Build high-resolution traces for HTML chart rendering.

        Separate from build() so the LLM prompt stays compact (100 pts)
        while the interactive chart gets full detail (default 1 000 pts).

        Returns a dict with keys:
            "best"      – list of point dicts (always present)
            "reference" – list of point dicts, or None if no reference lap
        """
        valid_laps = self._filter_valid_laps(session.laps)
        if not valid_laps:
            return {"best": [], "reference": None}

        best_lap = self._select_best_lap(valid_laps)
        # Use all available frames; if fewer than chart_points just return them all
        n = min(chart_points, len(best_lap.frames)) if best_lap.frames else 0
        best_trace = resample_trace(best_lap.frames, n) if n > 0 else []

        ref_trace: list | None = None
        if reference_lap is not None:
            ref_trace = _get_ref_trace(reference_lap, chart_points)

        return {
            "best": best_trace,
            "reference": ref_trace,
            "best_pos": _extract_pos_arrays(best_trace),
            "ref_pos": _extract_pos_arrays(ref_trace) if ref_trace is not None else None,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _filter_valid_laps(self, laps: list[Lap]) -> list[Lap]:
        """Keep only laps with valid flag and a reasonable lap time (>30s)."""
        return [
            lap for lap in laps
            if lap.is_valid and lap.lap_time_ms > 30_000 and lap.frames
        ]

    def _select_best_lap(self, valid_laps: list[Lap]) -> Lap:
        return min(valid_laps, key=lambda l: l.lap_time_ms)

    def _build_lap_entry(self, lap: Lap, is_best: bool = False) -> LapContextEntry:
        trace = resample_trace(lap.frames, self._n_points)
        return LapContextEntry(
            lap_id=lap.lap_id,
            lap_time_str=lap.lap_time_str,
            is_best=is_best,
            is_reference=False,
            stats=lap.stats,
            trace=trace,
        )

    def _build_reference_entry(
        self, ref: ReferenceLap | SimcoachReference
    ) -> LapContextEntry:
        if isinstance(ref, SimcoachReference):
            # Already resampled — just subsample if needed for LLM context
            all_dicts = ref.to_trace_dicts()
            if len(all_dicts) > self._n_points and self._n_points > 1:
                step = len(all_dicts) / self._n_points
                trace = [all_dicts[int(i * step)] for i in range(self._n_points)]
            else:
                trace = all_dicts
            return LapContextEntry(
                lap_id=-1,
                lap_time_str=_format_time(ref.metadata.lap_time_ms),
                is_best=False,
                is_reference=True,
                stats=ref.stats,
                trace=trace,
            )
        # Legacy ReferenceLap path
        if ref.stats is None and ref.frames:
            ref.stats = compute_lap_stats(ref.frames)
        trace = resample_trace(ref.frames, self._n_points)
        return LapContextEntry(
            lap_id=-1,
            lap_time_str=ref.lap_time_str,
            is_best=False,
            is_reference=True,
            stats=ref.stats,
            trace=trace,
        )

    def _build_lap_summaries(
        self, valid_laps: list[Lap], best_lap_id: int
    ) -> list[dict[str, Any]]:
        summaries = []
        for lap in valid_laps:
            summaries.append({
                "lap_id": lap.lap_id,
                "lap_time_str": lap.lap_time_str,
                "lap_time_ms": lap.lap_time_ms,
                "is_best": lap.lap_id == best_lap_id,
                "max_speed_kmh": lap.stats.max_speed_kmh if lap.stats else None,
                "avg_speed_kmh": lap.stats.avg_speed_kmh if lap.stats else None,
                "gear_changes": lap.stats.gear_changes if lap.stats else None,
                "abs_events": lap.stats.abs_events if lap.stats else None,
                "tc_events": lap.stats.tc_events if lap.stats else None,
            })
        return summaries


# ── Module-level helpers ─────────────────────────────────────────────────────

def _ref_lap_time_ms(ref: ReferenceLap | SimcoachReference) -> int:
    if isinstance(ref, SimcoachReference):
        return ref.metadata.lap_time_ms
    return ref.lap_time_ms


def _get_ref_trace(
    ref: ReferenceLap | SimcoachReference, chart_points: int
) -> list[dict] | None:
    """Extract high-res trace from either reference type."""
    if isinstance(ref, SimcoachReference):
        return ref.to_trace_dicts() if ref.trace.n_points > 0 else None
    # Legacy ReferenceLap
    if not ref.frames:
        return None
    n_ref = min(chart_points, len(ref.frames))
    return resample_trace(ref.frames, n_ref) if n_ref > 0 else None


def _format_time(lap_time_ms: int) -> str:
    total_s = lap_time_ms / 1000.0
    minutes = int(total_s // 60)
    seconds = total_s % 60
    return f"{minutes}:{seconds:06.3f}"
