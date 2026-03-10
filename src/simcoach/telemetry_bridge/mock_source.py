"""
Mock telemetry source — generates realistic synthetic AC session data.

Simulates a ~2-minute lap around a fictional circuit with:
  - Long straight, heavy braking zone, chicane, technical section, hairpin
  - Consistent base lap with random variation between laps
  - Tyre and driver degradation modelling
"""

from __future__ import annotations

import math
import random
import time
from typing import Optional

from simcoach.models.telemetry import TelemetryFrame
from .base import TelemetrySource


# ─── Track profile ────────────────────────────────────────────────────────────
# Each segment: (start_pos, end_pos, type, max_speed_kmh, min_speed_kmh)
# Types: "straight" | "corner" | "chicane" | "hairpin"

TRACK_SEGMENTS = [
    # pos_start, pos_end, type,        max_spd, min_spd, braking_pos
    (0.00, 0.12, "straight",  240,  -1,   None),
    (0.12, 0.18, "corner",    190, 160,   0.11),   # fast corner
    (0.18, 0.32, "straight",  270,  -1,   None),   # main straight
    (0.32, 0.38, "hairpin",   230,  75,   0.30),   # heavy brake
    (0.38, 0.50, "straight",  210,  -1,   None),
    (0.50, 0.58, "chicane",   190,  95,   0.49),   # left-right
    (0.58, 0.70, "straight",  230,  -1,   None),
    (0.70, 0.76, "corner",    200, 130,   0.69),   # medium corner
    (0.76, 0.88, "straight",  250,  -1,   None),
    (0.88, 0.94, "corner",    220, 110,   0.87),   # final sector
    (0.94, 1.00, "straight",  240,  -1,   None),   # back to start
]

BASE_LAP_TIME_S = 118.0  # ~1:58


class MockTelemetrySource(TelemetrySource):
    """
    Generates realistic-looking synthetic telemetry frames.
    Useful for testing the full pipeline without Assetto Corsa running.
    """

    def __init__(
        self,
        car_id: str = "ferrari_458_gt2",
        track_id: str = "ks_nurburgring_sprint",
        n_laps: int = 6,
        sample_rate_hz: int = 25,
        seed: int | None = None,
    ) -> None:
        self._car_id = car_id
        self._track_id = track_id
        self._n_laps = n_laps
        self._sample_rate = sample_rate_hz
        self._rng = random.Random(seed)

        self._current_lap = 0
        self._pos = 0.0             # normalised track position
        self._lap_start_time = 0.0
        self._session_start = 0.0
        self._done = False
        self._started = False

        # Pre-generate per-lap pace variation: lap 0 slow (out lap), best around lap 3-4
        self._lap_offsets: list[float] = []

    def connect(self) -> bool:
        # Generate lap pace offsets: first lap slow, then improving, then slight degradation
        offsets = [3.5, 1.2, 0.3, 0.0, 0.4, 0.9, 1.5]
        self._lap_offsets = offsets[:self._n_laps]
        while len(self._lap_offsets) < self._n_laps:
            self._lap_offsets.append(offsets[-1] + 0.5 * (len(self._lap_offsets) - len(offsets) + 1))

        self._session_start = time.time()
        self._lap_start_time = self._session_start
        self._started = True
        return True

    def disconnect(self) -> None:
        self._started = False

    def read_frame(self) -> Optional[TelemetryFrame]:
        if not self._started or self._done:
            return None

        ts = time.time()
        lap_offset_s = self._lap_offsets[self._current_lap] if self._current_lap < len(self._lap_offsets) else 2.0
        effective_lap_time = BASE_LAP_TIME_S + lap_offset_s

        # Advance position
        step = 1.0 / (effective_lap_time * self._sample_rate)
        noise = self._rng.gauss(0, step * 0.05)
        self._pos += step + noise
        self._pos = max(0.0, self._pos)

        # Lap boundary
        if self._pos >= 1.0:
            self._pos -= 1.0
            self._current_lap += 1
            self._lap_start_time = ts
            if self._current_lap >= self._n_laps:
                self._done = True
                return None

        pos = self._pos
        seg = _get_segment(pos)

        speed, throttle, brake, gear, rpm, steering = _compute_controls(
            pos, seg, self._rng, lap_offset_s
        )
        wx, wy, wz = _world_position(pos)

        return TelemetryFrame(
            timestamp=ts,
            lap_id=self._current_lap,
            normalized_track_position=round(pos, 5),
            speed_kmh=speed,
            throttle=throttle,
            brake=brake,
            steering=steering,
            gear=gear,
            rpm=rpm,
            clutch=0.0,
            g_lat=round(-steering * speed / 150.0 + self._rng.gauss(0, 0.05), 3),
            g_lon=round((throttle - brake) * 0.8 + self._rng.gauss(0, 0.05), 3),
            abs_active=brake > 0.8 and speed > 120,
            tc_active=throttle > 0.9 and speed < 80 and gear <= 2,
            world_pos_x=wx,
            world_pos_y=wy,
            world_pos_z=wz,
        )

    @property
    def car_id(self) -> str:
        return self._car_id

    @property
    def track_id(self) -> str:
        return self._track_id

    @property
    def is_session_active(self) -> bool:
        return self._started and not self._done

    @property
    def is_done(self) -> bool:
        return self._done


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _world_position(pos: float) -> tuple[float, float, float]:
    """Map normalized track position [0, 1] to (x, y, z) world coordinates in metres.

    Produces a plausible closed-circuit shape using a parametric formula:
    - Base shape: stretched oval with slight asymmetry
    - Hairpin notch at ~pos=0.33 (matching the TRACK_SEGMENTS hairpin)
    - Chicane kink at ~pos=0.53 (matching the chicane segment)
    """
    theta = 2 * math.pi * pos
    x = 350.0 * math.cos(theta)
    z = 250.0 * math.sin(theta) * (1 + 0.25 * math.cos(theta))
    # hairpin notch
    z -= 80.0 * math.exp(-((pos - 0.33) ** 2) / 0.04)
    # chicane kink
    x += 30.0 * math.sin(2 * math.pi * pos) * math.exp(-((pos - 0.53) ** 2) / 0.02)
    return round(x, 2), 0.0, round(z, 2)


def _get_segment(pos: float) -> tuple:
    for seg in TRACK_SEGMENTS:
        if seg[0] <= pos < seg[1]:
            return seg
    return TRACK_SEGMENTS[-1]


def _compute_controls(
    pos: float,
    seg: tuple,
    rng: random.Random,
    lap_offset: float,
) -> tuple[float, float, float, int, float, float]:
    """Return (speed, throttle, brake, gear, rpm, steering) for a track position."""
    seg_start, seg_end, seg_type, max_spd, min_spd, brake_pos = seg

    seg_len = seg_end - seg_start
    seg_progress = (pos - seg_start) / max(seg_len, 0.001)

    # ── Speed profile ────────────────────────────────────────────────────────
    if seg_type == "straight":
        # Accelerating along straight
        speed = max_spd * (0.7 + 0.3 * seg_progress) + rng.gauss(0, 2)
        # Look ahead: if next segment needs heavy braking, start slowing
        next_seg_idx = TRACK_SEGMENTS.index(seg) + 1
        if next_seg_idx < len(TRACK_SEGMENTS):
            next_seg = TRACK_SEGMENTS[next_seg_idx]
            if next_seg[2] in ("hairpin", "chicane") and seg_progress > 0.75:
                brake_approach = (seg_progress - 0.75) / 0.25
                speed = speed * (1.0 - brake_approach * 0.25)
    elif seg_type in ("corner", "hairpin", "chicane"):
        # Speed valley: slow in, fast out
        valley = math.sin(math.pi * seg_progress)  # 0→1→0
        speed = min_spd + (max_spd - min_spd) * (1.0 - valley * 0.85)
        speed += rng.gauss(0, 3)
    else:
        speed = max_spd * 0.9

    speed = max(40.0, min(300.0, speed))
    speed += rng.gauss(0, 0.5)

    # ── Throttle / brake ────────────────────────────────────────────────────
    if seg_type == "straight":
        if seg_progress > 0.80 and brake_pos is None:
            # Start coasting / minor lift
            throttle = rng.uniform(0.5, 0.8)
            brake = 0.0
        else:
            throttle = rng.uniform(0.92, 1.0)
            brake = 0.0
    elif seg_type in ("hairpin", "chicane"):
        if seg_progress < 0.30:
            # Hard braking zone
            throttle = 0.0
            brake = rng.uniform(0.70, 0.95)
            # Better drivers apply brake later / harder → lap_offset penalty
            brake *= (1.0 - lap_offset * 0.015)
        elif seg_progress < 0.55:
            # Trail braking + turn-in
            throttle = rng.uniform(0.0, 0.15)
            brake = rng.uniform(0.10, 0.45)
        else:
            # Acceleration out
            throttle = rng.uniform(0.60, 0.95)
            brake = 0.0
    elif seg_type == "corner":
        if seg_progress < 0.25:
            throttle = rng.uniform(0.0, 0.25)
            brake = rng.uniform(0.05, 0.35)
        elif seg_progress < 0.60:
            throttle = rng.uniform(0.20, 0.55)
            brake = 0.0
        else:
            throttle = rng.uniform(0.60, 0.95)
            brake = 0.0
    else:
        throttle = 0.7
        brake = 0.0

    throttle = max(0.0, min(1.0, throttle + rng.gauss(0, 0.02)))
    brake    = max(0.0, min(1.0, brake    + rng.gauss(0, 0.02)))

    # ── Gear and RPM ────────────────────────────────────────────────────────
    gear_thresholds = [0, 50, 90, 130, 175, 210, 245]
    gear = 1
    for g, threshold in enumerate(gear_thresholds[1:], 1):
        if speed > threshold:
            gear = g + 1
    gear = max(1, min(6, gear))

    max_rpm = 8500
    rpm_base = 2500 + (speed / 280.0) * (max_rpm - 2500)
    rpm = max(800, min(max_rpm, rpm_base + rng.gauss(0, 150)))

    # ── Steering ────────────────────────────────────────────────────────────
    if seg_type == "straight":
        steering = rng.gauss(0, 0.03)
    elif seg_type == "hairpin":
        # Right hairpin
        peak_steer = 0.75 + rng.gauss(0, 0.05)
        steering = peak_steer * math.sin(math.pi * seg_progress)
    elif seg_type == "chicane":
        # Left then right
        if seg_progress < 0.5:
            steering = -0.45 * math.sin(math.pi * seg_progress * 2)
        else:
            steering = 0.40 * math.sin(math.pi * (seg_progress - 0.5) * 2)
    elif seg_type == "corner":
        steering = 0.40 * math.sin(math.pi * seg_progress) + rng.gauss(0, 0.03)
    else:
        steering = 0.0

    steering = max(-1.0, min(1.0, steering + rng.gauss(0, 0.01)))

    return (
        round(speed, 1),
        round(throttle, 3),
        round(brake, 3),
        gear,
        round(rpm),
        round(steering, 3),
    )
