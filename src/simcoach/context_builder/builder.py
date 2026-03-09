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

from simcoach.models.telemetry import (
    Lap,
    LapContextEntry,
    LLMAnalysisContext,
    ReferenceLap,
    Session,
)
from simcoach.utils.sampling import compute_lap_stats, resample_trace


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
        reference_lap: ReferenceLap | None = None,
    ) -> LLMAnalysisContext:
        """
        Build the LLM context from a session.

        Args:
            session:       Recorded session with laps and frames.
            reference_lap: Optional personal-best lap loaded from the PB store.

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
            if reference_lap.stats is None and reference_lap.frames:
                reference_lap.stats = compute_lap_stats(reference_lap.frames)
            ref_entry = self._build_reference_entry(reference_lap)
            delta_ms = best_lap.lap_time_ms - reference_lap.lap_time_ms

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

    def _build_reference_entry(self, ref: ReferenceLap) -> LapContextEntry:
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
