"""Telemetry resampling and statistics utilities."""

from __future__ import annotations

import statistics
from typing import Any

from simcoach.models.telemetry import TelemetryFrame, LapStats


def resample_trace(frames: list[TelemetryFrame], n_points: int = 100) -> list[dict[str, Any]]:
    """
    Resample a list of TelemetryFrames to exactly n_points evenly spaced by
    normalized_track_position (0.0–1.0).

    Returns a list of dicts suitable for JSON serialisation and LLM consumption.
    Each dict contains the key channels at that track position.
    """
    if not frames:
        return []

    # Sort by track position to handle any ordering issues
    sorted_frames = sorted(frames, key=lambda f: f.normalized_track_position)

    # Target positions
    targets = [i / (n_points - 1) for i in range(n_points)]

    result: list[dict[str, Any]] = []
    frame_idx = 0

    for target_pos in targets:
        # Advance until we find the closest frame
        while frame_idx < len(sorted_frames) - 1:
            next_frame = sorted_frames[frame_idx + 1]
            if next_frame.normalized_track_position <= target_pos:
                frame_idx += 1
            else:
                break

        f = sorted_frames[frame_idx]

        # Linear interpolation to the next frame if possible
        if frame_idx < len(sorted_frames) - 1:
            f2 = sorted_frames[frame_idx + 1]
            span = f2.normalized_track_position - f.normalized_track_position
            if span > 0:
                t = (target_pos - f.normalized_track_position) / span
                t = max(0.0, min(1.0, t))
                result.append({
                    "pos": round(target_pos, 4),
                    "spd": round(_lerp(f.speed_kmh, f2.speed_kmh, t), 1),
                    "thr": round(_lerp(f.throttle, f2.throttle, t), 3),
                    "brk": round(_lerp(f.brake, f2.brake, t), 3),
                    "str": round(_lerp(f.steering, f2.steering, t), 3),
                    "gear": f.gear,
                    "rpm": round(_lerp(f.rpm, f2.rpm, t)),
                    "wx": round(_lerp(f.world_pos_x, f2.world_pos_x, t), 2)
                          if (f.world_pos_x is not None and f2.world_pos_x is not None) else None,
                    "wz": round(_lerp(f.world_pos_z, f2.world_pos_z, t), 2)
                          if (f.world_pos_z is not None and f2.world_pos_z is not None) else None,
                })
                continue

        result.append({
            "pos": round(target_pos, 4),
            "spd": round(f.speed_kmh, 1),
            "thr": round(f.throttle, 3),
            "brk": round(f.brake, 3),
            "str": round(f.steering, 3),
            "gear": f.gear,
            "rpm": round(f.rpm),
            "wx": f.world_pos_x,
            "wz": f.world_pos_z,
        })

    return result


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def compute_lap_stats(frames: list[TelemetryFrame]) -> LapStats:
    """Compute derived statistics for a lap from its raw frames."""
    if not frames:
        return LapStats(
            max_speed_kmh=0, avg_speed_kmh=0,
            max_throttle=0, avg_throttle=0,
            max_brake=0, avg_brake=0,
            max_steering_abs=0, avg_steering_abs=0,
            full_throttle_pct=0, heavy_brake_pct=0,
            gear_changes=0, abs_events=0, tc_events=0,
        )

    speeds = [f.speed_kmh for f in frames]
    throttles = [f.throttle for f in frames]
    brakes = [f.brake for f in frames]
    steerings = [abs(f.steering) for f in frames]

    n = len(frames)
    gear_changes = sum(
        1 for i in range(1, n) if frames[i].gear != frames[i - 1].gear
    )

    abs_events = 0
    tc_events = 0
    prev_abs = False
    prev_tc = False
    for f in frames:
        if f.abs_active and not prev_abs:
            abs_events += 1
        if f.tc_active and not prev_tc:
            tc_events += 1
        prev_abs = f.abs_active
        prev_tc = f.tc_active

    return LapStats(
        max_speed_kmh=max(speeds),
        avg_speed_kmh=round(statistics.mean(speeds), 1),
        max_throttle=max(throttles),
        avg_throttle=round(statistics.mean(throttles), 3),
        max_brake=max(brakes),
        avg_brake=round(statistics.mean(brakes), 3),
        max_steering_abs=max(steerings),
        avg_steering_abs=round(statistics.mean(steerings), 3),
        full_throttle_pct=round(sum(1 for t in throttles if t > 0.95) / n, 3),
        heavy_brake_pct=round(sum(1 for b in brakes if b > 0.80) / n, 3),
        gear_changes=gear_changes,
        abs_events=abs_events,
        tc_events=tc_events,
    )
