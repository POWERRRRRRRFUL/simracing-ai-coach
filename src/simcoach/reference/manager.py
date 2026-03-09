"""
Reference lap manager — persists and retrieves personal best (PB) laps.

PB laps are stored as JSON files under:
  output/pb_laps/{car_id}/{track_id}/pb.json

On each analyse run, we:
1. Load the existing PB for (car, track) if any
2. Compare with this session's best lap
3. Update the PB if this session is faster
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from simcoach.models.telemetry import Lap, ReferenceLap, Session
from simcoach.utils.sampling import compute_lap_stats


class ReferenceManager:
    """Manages personal-best lap storage and retrieval."""

    def __init__(self, pb_dir: str = "output/pb_laps") -> None:
        self._pb_dir = Path(pb_dir)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_pb(self, car_id: str, track_id: str) -> Optional[ReferenceLap]:
        """Load the stored personal best for this car + track combo, or None."""
        path = self._pb_path(car_id, track_id)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return ReferenceLap.model_validate(data)

    def update_pb_if_faster(
        self,
        session: Session,
        best_lap: Lap,
    ) -> tuple[bool, Optional[ReferenceLap]]:
        """
        Compare best_lap against the stored PB.
        If best_lap is faster (or no PB exists), save it as the new PB.

        Returns:
            (was_updated: bool, new_pb: ReferenceLap | None)
        """
        current_pb = self.load_pb(session.car_id, session.track_id)

        if current_pb is not None and current_pb.lap_time_ms <= best_lap.lap_time_ms:
            # Existing PB is equal or faster — no update
            return False, current_pb

        # Build and save new PB
        if best_lap.stats is None:
            best_lap.stats = compute_lap_stats(best_lap.frames)

        new_pb = ReferenceLap(
            source="personal_best",
            car_id=session.car_id,
            track_id=session.track_id,
            lap_time_ms=best_lap.lap_time_ms,
            session_id=session.session_id,
            frames=best_lap.frames,
            stats=best_lap.stats,
        )
        self._save_pb(new_pb)
        return True, new_pb

    # ── Internal ──────────────────────────────────────────────────────────────

    def _pb_path(self, car_id: str, track_id: str) -> Path:
        safe_car = _sanitise(car_id)
        safe_track = _sanitise(track_id)
        return self._pb_dir / safe_car / safe_track / "pb.json"

    def _save_pb(self, ref: ReferenceLap) -> None:
        path = self._pb_path(ref.car_id, ref.track_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ref.model_dump(), f, indent=2)


def _sanitise(name: str) -> str:
    """Make a string safe to use as a directory name."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
