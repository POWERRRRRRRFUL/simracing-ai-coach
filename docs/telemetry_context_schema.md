# Telemetry Context Schema

This document describes the JSON structure passed to the LLM for analysis.

## Overview

The context is built by `ContextBuilder` in `src/simcoach/context_builder/builder.py`.
It is intentionally compact: raw telemetry is resampled to **100 evenly-spaced points** per lap
to keep token usage reasonable while preserving the shape of each driving channel.

---

## Top-level structure

```json
{
  "car_id": "ferrari_458_gt2",
  "track_id": "ks_nurburgring_sprint",
  "session_id": "a1b2c3d4",
  "session_date": "2026-03-09T10:00:00+00:00",
  "total_laps": 6,
  "valid_laps": 5,
  "best_lap": { ... },
  "reference_lap": { ... } | null,
  "all_lap_summaries": [ ... ],
  "delta_vs_reference_ms": -234
}
```

| Field | Type | Description |
|-------|------|-------------|
| `car_id` | string | AC car model identifier |
| `track_id` | string | AC track identifier |
| `session_id` | string | Unique 8-char session ID |
| `session_date` | ISO-8601 string | When the session was recorded |
| `total_laps` | int | Total laps in session (including invalid) |
| `valid_laps` | int | Laps with `is_valid=true` and time > 30s |
| `best_lap` | LapContextEntry | The fastest valid lap in this session |
| `reference_lap` | LapContextEntry \| null | Stored personal best for comparison |
| `all_lap_summaries` | array | Light summary of all valid laps |
| `delta_vs_reference_ms` | int \| null | `best_lap_time - reference_lap_time` in ms |

---

## LapContextEntry

Used for both `best_lap` and `reference_lap`.

```json
{
  "lap_id": 3,
  "lap_time_str": "1:57.234",
  "is_best": true,
  "is_reference": false,
  "stats": { ... },
  "trace": [ ... ]
}
```

### stats (LapStats)

```json
{
  "max_speed_kmh": 268.4,
  "avg_speed_kmh": 172.1,
  "max_throttle": 1.0,
  "avg_throttle": 0.612,
  "max_brake": 0.94,
  "avg_brake": 0.071,
  "max_steering_abs": 0.81,
  "avg_steering_abs": 0.142,
  "full_throttle_pct": 0.41,
  "heavy_brake_pct": 0.07,
  "gear_changes": 42,
  "abs_events": 3,
  "tc_events": 1
}
```

| Field | Description |
|-------|-------------|
| `full_throttle_pct` | Fraction of lap at >95% throttle (0–1) |
| `heavy_brake_pct` | Fraction of lap at >80% brake pressure (0–1) |
| `abs_events` | Number of ABS activations (leading-edge count) |
| `tc_events` | Number of TC activations (leading-edge count) |

### trace

Array of **100 evenly-spaced samples** by normalized track position.

```json
[
  { "pos": 0.0,   "spd": 142.3, "thr": 0.95, "brk": 0.0,  "str": 0.02,  "gear": 3, "rpm": 6820 },
  { "pos": 0.0101,"spd": 155.1, "thr": 1.0,  "brk": 0.0,  "str": 0.01,  "gear": 4, "rpm": 7100 },
  ...
  { "pos": 1.0,   "spd": 148.2, "thr": 0.92, "brk": 0.0,  "str": 0.03,  "gear": 3, "rpm": 6900 }
]
```

| Key | Description |
|-----|-------------|
| `pos` | Normalized track position (0.0 = start/finish, 1.0 = end of lap) |
| `spd` | Speed in km/h |
| `thr` | Throttle (0 = none, 1 = full) |
| `brk` | Brake pressure (0 = none, 1 = full) |
| `str` | Steering angle (−1 = full left, +1 = full right) |
| `gear` | Current gear (1–6, 0 = neutral, −1 = reverse) |
| `rpm` | Engine RPM |

---

## all_lap_summaries

Light summary of every valid lap for trend analysis.

```json
[
  {
    "lap_id": 0,
    "lap_time_str": "2:01.456",
    "lap_time_ms": 121456,
    "is_best": false,
    "max_speed_kmh": 261.2,
    "avg_speed_kmh": 168.4,
    "gear_changes": 39,
    "abs_events": 5,
    "tc_events": 3
  },
  ...
]
```

---

## Design decisions

### Why 100 resampled points?

Raw telemetry at 25 Hz produces ~2,900 frames for a ~118s lap.
Sending all frames would cost ~50,000 tokens per lap.
100 points preserves the shape of every channel (braking zones, throttle application, steering arcs)
while costing ~2,000 tokens — well within GPT-4o-mini's context window.

### Why normalized track position instead of time?

Time-aligned comparison is complicated by different lap times.
Position-aligned comparison makes it natural to say "at position 0.32 (the hairpin), the best lap shows
heavier braking earlier than the reference". The LLM can reason about this directly.

### What is NOT included

- Raw frame-level data (too large)
- Tyre temperatures and pressures (planned for v2)
- Sector times (planned for v2)
- World coordinates / track map (planned for v2)
