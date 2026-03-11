"""
Reference lap manager — manages personal bests, .simcoachref library, and active selection.

Storage layout:
  Legacy PB:   output/pb_laps/{car_id}/{track_id}/pb.json
  Library:     output/references/{car_id}/{track_id}/
                 ├── pb.simcoachref
                 ├── imported_*.simcoachref
                 └── active.json   ({"active_ref": "pb.simcoachref"})

Active reference resolution order:
  1. active.json explicit selection
  2. pb.simcoachref (auto-generated from PB)
  3. Legacy pb.json (backward compat)
  4. None
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from simcoach.models.reference import SimcoachReference
from simcoach.models.telemetry import Lap, LapStats, ReferenceLap, Session
from simcoach.utils.sampling import compute_lap_stats


class ReferenceManager:
    """Manages reference laps: PB tracking, .simcoachref library, and active selection."""

    def __init__(
        self,
        pb_dir: str = "output/pb_laps",
        library_dir: str = "output/references",
        trace_points: int = 1000,
    ) -> None:
        self._pb_dir = Path(pb_dir)
        self._library_dir = Path(library_dir)
        self._trace_points = trace_points

    # ── Loading ──────────────────────────────────────────────────────────────

    def load_active(
        self, car_id: str, track_id: str
    ) -> SimcoachReference | ReferenceLap | None:
        """Load the active reference for this car+track, following the resolution chain."""
        lib_dir = self._lib_path(car_id, track_id)

        # 1. Check active.json for explicit selection
        active_name = self._read_active_name(car_id, track_id)
        if active_name:
            active_path = lib_dir / active_name
            if active_path.exists():
                return self._load_simcoachref(active_path)

        # 2. Check pb.simcoachref
        pb_ref_path = lib_dir / "pb.simcoachref"
        if pb_ref_path.exists():
            return self._load_simcoachref(pb_ref_path)

        # 3. Fall back to legacy pb.json
        return self.load_pb(car_id, track_id)

    def load_pb(self, car_id: str, track_id: str) -> Optional[ReferenceLap]:
        """Load the stored personal best (legacy pb.json format), or None."""
        path = self._pb_path(car_id, track_id)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return ReferenceLap.model_validate(data)

    # ── Export / Import ──────────────────────────────────────────────────────

    def export_ref(
        self,
        session: Session,
        lap: Lap,
        output_path: Path | None = None,
        source: str = "personal_best",
        driver_name: str = "",
    ) -> Path:
        """Export a session lap as a .simcoachref file.

        If output_path is None, writes to the library directory.
        Returns the path of the written file.
        """
        ref = SimcoachReference.from_lap(
            session, lap,
            trace_points=self._trace_points,
            source=source,
            driver_name=driver_name,
        )

        if output_path is None:
            lib_dir = self._lib_path(session.car_id, session.track_id)
            lib_dir.mkdir(parents=True, exist_ok=True)
            time_str = ref.metadata.lap_time_ms
            output_path = lib_dir / f"export_{session.session_id}_{time_str}.simcoachref"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._save_simcoachref(ref, output_path)
        return output_path

    def import_ref(
        self, file_path: Path
    ) -> tuple[SimcoachReference, Path]:
        """Import a .simcoachref file into the library.

        Validates the file, copies it to the appropriate car/track library directory.
        Returns (parsed SimcoachReference, destination path in library).
        Raises ValueError if the file is invalid.
        """
        ref = self._load_simcoachref(file_path)

        # Copy to library
        lib_dir = self._lib_path(ref.metadata.car_id, ref.metadata.track_id)
        lib_dir.mkdir(parents=True, exist_ok=True)

        dest = lib_dir / file_path.name
        # Avoid overwriting — add a suffix if needed
        if dest.exists() and dest.resolve() != file_path.resolve():
            stem = dest.stem
            suffix = dest.suffix
            counter = 1
            while dest.exists():
                dest = lib_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        if dest.resolve() != file_path.resolve():
            shutil.copy2(file_path, dest)

        return ref, dest

    # ── Library management ───────────────────────────────────────────────────

    def list_refs(self, car_id: str, track_id: str) -> list[dict]:
        """List all .simcoachref files for a car+track combo.

        Returns a list of dicts: [{name, lap_time_ms, source, active}].
        """
        lib_dir = self._lib_path(car_id, track_id)
        if not lib_dir.is_dir():
            return []

        active_name = self._read_active_name(car_id, track_id)
        results = []
        for path in sorted(lib_dir.glob("*.simcoachref")):
            try:
                ref = self._load_simcoachref(path)
                results.append({
                    "name": path.name,
                    "lap_time_ms": ref.metadata.lap_time_ms,
                    "source": ref.metadata.source,
                    "driver_name": ref.metadata.driver_name,
                    "active": path.name == active_name,
                })
            except Exception:
                continue
        return results

    def set_active(self, car_id: str, track_id: str, ref_filename: str) -> None:
        """Set the active reference for a car+track combo."""
        lib_dir = self._lib_path(car_id, track_id)
        ref_path = lib_dir / ref_filename
        if not ref_path.exists():
            raise FileNotFoundError(f"Reference file not found: {ref_path}")

        # Validate it's a valid .simcoachref
        self._load_simcoachref(ref_path)

        active_path = lib_dir / "active.json"
        with open(active_path, "w", encoding="utf-8") as f:
            json.dump({"active_ref": ref_filename}, f, indent=2)

    def get_active_name(self, car_id: str, track_id: str) -> str | None:
        """Return the filename of the active reference, or None."""
        return self._read_active_name(car_id, track_id)

    # ── PB update ────────────────────────────────────────────────────────────

    def update_pb_if_faster(
        self,
        session: Session,
        best_lap: Lap,
    ) -> tuple[bool, Optional[ReferenceLap]]:
        """Compare best_lap against the stored PB. Update if faster.

        Saves both legacy pb.json AND pb.simcoachref for dual compatibility.
        Returns (was_updated, new_pb).
        """
        current_pb = self.load_pb(session.car_id, session.track_id)

        if current_pb is not None and current_pb.lap_time_ms <= best_lap.lap_time_ms:
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

        # Save legacy pb.json
        self._save_pb(new_pb)

        # Also save pb.simcoachref in the library
        simcoach_ref = SimcoachReference.from_lap(
            session, best_lap,
            trace_points=self._trace_points,
            source="personal_best",
        )
        lib_dir = self._lib_path(session.car_id, session.track_id)
        lib_dir.mkdir(parents=True, exist_ok=True)
        self._save_simcoachref(simcoach_ref, lib_dir / "pb.simcoachref")

        return True, new_pb

    # ── Internal ─────────────────────────────────────────────────────────────

    def _pb_path(self, car_id: str, track_id: str) -> Path:
        return self._pb_dir / _sanitise(car_id) / _sanitise(track_id) / "pb.json"

    def _lib_path(self, car_id: str, track_id: str) -> Path:
        return self._library_dir / _sanitise(car_id) / _sanitise(track_id)

    def _save_pb(self, ref: ReferenceLap) -> None:
        path = self._pb_path(ref.car_id, ref.track_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ref.model_dump(), f, indent=2)

    def _read_active_name(self, car_id: str, track_id: str) -> str | None:
        active_path = self._lib_path(car_id, track_id) / "active.json"
        if not active_path.exists():
            return None
        try:
            with open(active_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("active_ref")
        except Exception:
            return None

    @staticmethod
    def _load_simcoachref(path: Path) -> SimcoachReference:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return SimcoachReference.model_validate(data)

    @staticmethod
    def _save_simcoachref(ref: SimcoachReference, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ref.model_dump(), f, indent=2)


def _sanitise(name: str) -> str:
    """Make a string safe to use as a directory name."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
