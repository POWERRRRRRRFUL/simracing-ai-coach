"""Session recorder — polls a TelemetrySource and writes a session JSON file."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from simcoach.models.telemetry import Session, Lap, TelemetryFrame
from simcoach.telemetry_bridge.base import TelemetrySource
from simcoach.utils.sampling import compute_lap_stats


class SessionRecorder:
    """
    Polls a TelemetrySource at the configured sample rate, detects lap boundaries,
    and assembles a Session object.  Call record() to run the blocking loop.
    """

    def __init__(
        self,
        source: TelemetrySource,
        sample_rate_hz: int = 25,
        output_dir: str = "output/sessions",
        on_lap_complete: Optional[Callable[[Lap], None]] = None,
    ) -> None:
        self._source = source
        self._sample_rate = sample_rate_hz
        self._interval = 1.0 / sample_rate_hz
        self._output_dir = Path(output_dir)
        self._on_lap_complete = on_lap_complete
        self._fast_mode = False  # set during record()

        self._session: Optional[Session] = None
        self._current_lap_frames: list[TelemetryFrame] = []
        self._current_lap_id: int = -1
        self._last_lap_complete_time: float = 0.0

        # For lap time estimation when shared memory doesn't provide it directly
        self._lap_start_time: float = 0.0

    # ── Public API ────────────────────────────────────────────────────────────

    def record(
        self,
        stop_condition: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        fast_mode: bool = False,
    ) -> Session:
        """
        Run the recording loop.

        Args:
            stop_condition: Callable returning True when recording should stop.
                            If None, recording stops when the source reports done.
            fast_mode: Skip sleep throttling — generates data as fast as possible.
                       Use this with MockTelemetrySource for instant demo sessions.
            progress_callback: Called with (current_lap, total_frames) each second.

        Returns:
            The completed Session object.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)

        session_id = str(uuid.uuid4())[:8]
        recorded_at = datetime.now(timezone.utc).isoformat()

        self._session = Session(
            session_id=session_id,
            car_id=self._source.car_id,
            track_id=self._source.track_id,
            recorded_at=recorded_at,
            source=self._source.__class__.__name__,
        )

        self._current_lap_id = 0
        self._current_lap_frames = []
        self._lap_start_time = time.time()
        self._fast_mode = fast_mode
        last_progress_report = time.time()

        print(f"[recorder] Recording session {session_id} on {self._source.track_id} / {self._source.car_id}")

        while True:
            loop_start = time.time()

            # Check stop condition
            if stop_condition and stop_condition():
                break
            if hasattr(self._source, "is_done") and self._source.is_done:
                break

            # Read a frame
            frame = self._source.read_frame()
            if frame is not None:
                self._process_frame(frame)

            # Progress callback ~every second
            if time.time() - last_progress_report >= 1.0:
                if progress_callback:
                    progress_callback(
                        self._current_lap_id,
                        len(self._session.raw_frames),
                    )
                last_progress_report = time.time()

            # Throttle to target sample rate (skip in fast_mode for instant mock sessions)
            if not fast_mode:
                elapsed = time.time() - loop_start
                sleep_time = self._interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        # Flush final partial lap
        self._flush_current_lap(is_final=True)

        return self._session

    def save(self, session: Session) -> Path:
        """Serialise session to JSON and return the file path."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        fname = f"session_{session.session_id}_{session.track_id}.json"
        path = self._output_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session.model_dump(), f, indent=2)
        return path

    # ── Internal ──────────────────────────────────────────────────────────────

    def _process_frame(self, frame: TelemetryFrame) -> None:
        assert self._session is not None

        self._session.raw_frames.append(frame)

        if frame.lap_id != self._current_lap_id:
            # Lap boundary detected
            self._flush_current_lap(is_final=False)
            self._current_lap_id = frame.lap_id
            self._lap_start_time = time.time()

        self._current_lap_frames.append(frame)

    def _flush_current_lap(self, is_final: bool) -> None:
        assert self._session is not None

        if not self._current_lap_frames:
            return

        frames = self._current_lap_frames
        lap_id = self._current_lap_id

        # Estimate lap time.
        # In fast_mode wall-clock is meaningless; derive time from frame count.
        if self._fast_mode:
            lap_time_ms = int(len(frames) / self._sample_rate * 1000)
        else:
            lap_time_ms = int((time.time() - self._lap_start_time) * 1000)
        # Discard obviously invalid laps (out-lap fragments < 30s)
        is_valid = lap_time_ms > 30_000

        stats = compute_lap_stats(frames) if is_valid else None

        lap = Lap(
            lap_id=lap_id,
            lap_time_ms=lap_time_ms,
            is_valid=is_valid,
            frames=frames,
            stats=stats,
        )
        self._session.laps.append(lap)

        if self._on_lap_complete and is_valid:
            self._on_lap_complete(lap)

        self._current_lap_frames = []
