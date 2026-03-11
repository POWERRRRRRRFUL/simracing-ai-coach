"""Session recorder — polls a TelemetrySource and writes a session JSON file."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# Auto-stop if no valid telemetry frame arrives within this window (AC probably exited)
STALE_DATA_TIMEOUT_S: float = 8.0

from simcoach.models.telemetry import Session, Lap, TelemetryFrame
from simcoach.telemetry_bridge.base import TelemetrySource
from simcoach.utils.sampling import compute_lap_stats


class SessionRecorder:
    """
    Polls a TelemetrySource at the configured sample rate, detects lap boundaries,
    and assembles a Session object.  Call record() to run the blocking loop.

    Lap segmentation strategy:
      - The first segment (recording-start → first S/F crossing) is kept in
        session data but marked ``complete=False, is_valid=False`` (prologue).
      - Each subsequent crossing finalises a *completed* lap (``complete=True``).
      - When recording stops the unfinished current segment is likewise kept
        but marked ``complete=False, is_valid=False``.
      - Only laps with ``complete=True`` and a lap time > 30 s are ``is_valid``.
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
        self._stop_requested = False  # set by request_stop() or KI handler
        self._last_frame_time: float = 0.0  # wall-clock time of last non-None frame

        self._session: Optional[Session] = None
        self._current_lap_frames: list[TelemetryFrame] = []
        self._current_lap_id: int = -1
        self._last_lap_complete_time: float = 0.0

        # For lap time estimation when shared memory doesn't provide it directly
        self._lap_start_time: float = 0.0
        self._first_crossing_seen: bool = False
        # Secondary crossing signal: track the last frame's position so we can
        # detect a pos wrap (>0.9 → <0.1) even when lap_id hasn't updated yet.
        self._prev_pos: float | None = None

    # ── Public stop API ───────────────────────────────────────────────────────

    def request_stop(self) -> None:
        """Signal the recording loop to exit cleanly after the current frame.
        Safe to call from another thread."""
        self._stop_requested = True

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
        self._stop_requested = False
        self._last_frame_time = 0.0
        self._first_crossing_seen = False
        self._prev_pos = None
        last_progress_report = time.time()

        print(f"[recorder] Session {session_id} | {self._source.track_id} / {self._source.car_id}")

        try:
            # Phase 1: sampling loop — exits cleanly when _stop_requested is set.
            while not self._stop_requested:
                loop_start = time.time()

                if stop_condition and stop_condition():
                    break
                if hasattr(self._source, "is_done") and self._source.is_done:
                    break

                frame = self._source.read_frame()
                if frame is not None:
                    self._process_frame(frame)
                    self._last_frame_time = time.time()

                # Auto-stop: AC has probably exited (shared memory frozen / stale)
                if (not fast_mode
                        and self._last_frame_time > 0
                        and time.time() - self._last_frame_time > STALE_DATA_TIMEOUT_S):
                    print(f"\n[recorder] No telemetry for {STALE_DATA_TIMEOUT_S:.0f}s "
                          f"— auto-stopping (AC may have exited)")
                    break

                if time.time() - last_progress_report >= 1.0:
                    if progress_callback:
                        progress_callback(
                            self._current_lap_id,
                            len(self._session.raw_frames),
                        )
                    last_progress_report = time.time()

                # Sleep in small slices so _stop_requested is checked promptly.
                if not fast_mode:
                    deadline = loop_start + self._interval
                    while time.time() < deadline and not self._stop_requested:
                        time.sleep(min(0.02, deadline - time.time()))

        except KeyboardInterrupt:
            # KI can arrive during read_frame() or _process_frame() (non-sleep code).
            # Set the flag; execution falls through to Phase 2 below.
            print(f"\n[recorder] Stop requested, finishing current capture... "
                  f"({len(self._session.raw_frames)} frames collected)")
            self._stop_requested = True

        # Phase 2: finalise — always runs, regardless of how the loop exited.
        # Re-read car_id in case it was "unknown" at connect() but populated later.
        if self._session.car_id == "unknown":
            resolved = self._source.car_id
            if resolved not in ("unknown", "", "0"):
                self._session.car_id = resolved

        print("[recorder] Finalizing laps...")
        self._flush_current_lap(complete=False)  # final segment is always incomplete
        valid = sum(1 for l in self._session.laps if l.is_valid)
        complete = sum(1 for l in self._session.laps if l.complete)
        print(f"[recorder] Laps: {len(self._session.laps)} total, {complete} complete, {valid} valid "
              f"| Frames: {len(self._session.raw_frames)}")

        return self._session

    def save(self, session: Session) -> Path:
        """Atomically serialise session to JSON (write tmp → rename).

        Raises ValueError if the session has no laps (nothing worth saving).
        Raises any OS / serialisation error without swallowing it.
        """
        if not session.laps:
            raise ValueError("Session contains no laps — nothing to save.")

        self._output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        fname = f"session_{ts}_{session.session_id}_{session.track_id}.json"
        final_path = self._output_dir / fname
        tmp_path   = self._output_dir / (fname + ".tmp")

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(session.model_dump(), f, indent=2)
            # Atomic on the same filesystem — partial writes never reach final_path.
            tmp_path.replace(final_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        return final_path

    # ── Internal ──────────────────────────────────────────────────────────────

    def _process_frame(self, frame: TelemetryFrame) -> None:
        """Process a single telemetry frame, detecting S/F crossings via two signals:

        1. **lap_id change** (primary): AC's ``completedLaps`` counter incremented.
           Authoritative but delivered on the *first frame after* the physical crossing,
           so it can be missed if recording stops in that gap.

        2. **position wrap** (secondary): ``normalized_track_position`` drops from >0.9
           to <0.1 between consecutive frames.  This fires on the frame that contains the
           crossing, one frame *before* ``completedLaps`` updates in shared memory.

        Using both signals means a completed lap is preserved even when AC exits or the
        user stops recording immediately after crossing the line.

        To prevent double-counting when both signals arrive close together (which is the
        normal case): after a pos-wrap-only crossing we advance ``_current_lap_id`` by 1
        as a sentinel, so the delayed ``lap_id`` update on the following frame is seen as
        equal to ``_current_lap_id`` and does not trigger a second flush.
        """
        assert self._session is not None

        self._session.raw_frames.append(frame)

        lap_id_changed = frame.lap_id != self._current_lap_id
        pos_wrap = (
            self._prev_pos is not None
            and self._prev_pos > 0.9
            and frame.normalized_track_position < 0.1
        )

        if lap_id_changed or pos_wrap:
            # S/F crossing detected — decide whether this is prologue or a real lap.
            if not self._first_crossing_seen:
                self._flush_current_lap(complete=False)   # prologue
                self._first_crossing_seen = True
            else:
                self._flush_current_lap(complete=True)    # completed lap

            if lap_id_changed:
                # Take AC's authoritative new lap id.
                self._current_lap_id = frame.lap_id
            else:
                # pos_wrap only: AC hasn't incremented lap_id yet.
                # Advance by 1 as a sentinel so the next frame (when lap_id DOES
                # update) doesn't look like a second crossing.
                self._current_lap_id += 1

            self._lap_start_time = time.time()

        self._prev_pos = frame.normalized_track_position
        self._current_lap_frames.append(frame)

    def _flush_current_lap(self, *, complete: bool) -> None:
        """Finalise the current lap buffer into a Lap object.

        Args:
            complete: True when the lap was finalised by a S/F crossing event
                      (i.e. the car actually completed a full lap cycle).
                      False for the initial prologue and the final incomplete segment.
        """
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

        # Only laps that completed a full S/F cycle AND have a reasonable
        # duration (> 30 s) are considered valid for analysis and PB tracking.
        is_valid = complete and lap_time_ms > 30_000

        stats = compute_lap_stats(frames) if is_valid else None

        lap = Lap(
            lap_id=lap_id,
            lap_time_ms=lap_time_ms,
            is_valid=is_valid,
            complete=complete,
            frames=frames,
            stats=stats,
        )
        self._session.laps.append(lap)

        if self._on_lap_complete and is_valid:
            self._on_lap_complete(lap)

        self._current_lap_frames = []
