"""Basic smoke tests for simcoach models and core pipeline."""

import pytest
from simcoach.models.telemetry import TelemetryFrame, Lap, Session
from simcoach.utils.sampling import compute_lap_stats, resample_trace


def _make_frame(pos: float, lap_id: int = 0) -> TelemetryFrame:
    return TelemetryFrame(
        timestamp=1000.0 + pos * 120,
        lap_id=lap_id,
        normalized_track_position=pos,
        speed_kmh=150.0 + pos * 50,
        throttle=0.8 if pos > 0.5 else 0.1,
        brake=0.6 if pos < 0.3 else 0.0,
        steering=0.1 * (pos - 0.5),
        gear=4 if pos > 0.4 else 2,
        rpm=6000.0,
    )


def _make_lap(lap_id: int = 0, lap_time_ms: int = 118000) -> Lap:
    frames = [_make_frame(i / 99, lap_id) for i in range(100)]
    return Lap(lap_id=lap_id, lap_time_ms=lap_time_ms, is_valid=True, frames=frames)


# ── TelemetryFrame ─────────────────────────────────────────────────────────────

def test_frame_creation():
    f = _make_frame(0.5)
    assert f.normalized_track_position == 0.5
    assert 0.0 <= f.throttle <= 1.0
    assert 0.0 <= f.brake <= 1.0


def test_frame_clamps_invalid():
    """Pydantic should reject values outside [0,1] for throttle."""
    with pytest.raises(Exception):
        TelemetryFrame(
            timestamp=0, lap_id=0,
            normalized_track_position=0.5,
            speed_kmh=100,
            throttle=1.5,  # invalid
            brake=0,
            steering=0,
            gear=3,
            rpm=5000,
        )


# ── compute_lap_stats ──────────────────────────────────────────────────────────

def test_compute_lap_stats_basic():
    frames = [_make_frame(i / 99) for i in range(100)]
    stats = compute_lap_stats(frames)
    assert stats.max_speed_kmh > 150
    assert 0.0 <= stats.avg_throttle <= 1.0
    assert stats.gear_changes >= 0


def test_compute_lap_stats_empty():
    stats = compute_lap_stats([])
    assert stats.max_speed_kmh == 0
    assert stats.gear_changes == 0


# ── resample_trace ─────────────────────────────────────────────────────────────

def test_resample_returns_n_points():
    frames = [_make_frame(i / 99) for i in range(100)]
    result = resample_trace(frames, n_points=50)
    assert len(result) == 50


def test_resample_keys():
    frames = [_make_frame(i / 99) for i in range(100)]
    result = resample_trace(frames, n_points=10)
    assert all("pos" in p and "spd" in p and "thr" in p and "brk" in p for p in result)


def test_resample_empty():
    result = resample_trace([], n_points=50)
    assert result == []


# ── Lap ────────────────────────────────────────────────────────────────────────

def test_lap_time_str():
    lap = _make_lap(lap_time_ms=118456)
    assert "1:" in lap.lap_time_str


def test_lap_time_str_invalid():
    lap = Lap(lap_id=0, lap_time_ms=-1, is_valid=False)
    assert lap.lap_time_str == "invalid"


# ── Session ────────────────────────────────────────────────────────────────────

def test_session_creation():
    session = Session(
        session_id="abc123",
        car_id="ferrari_458_gt2",
        track_id="ks_nurburgring_sprint",
        recorded_at="2026-03-09T10:00:00+00:00",
        source="mock",
        laps=[_make_lap(0), _make_lap(1, 116000), _make_lap(2, 117500)],
    )
    assert len(session.laps) == 3
    best = min(session.laps, key=lambda l: l.lap_time_ms)
    assert best.lap_time_ms == 116000


# ── ContextBuilder ─────────────────────────────────────────────────────────────

def test_context_builder_end_to_end():
    from simcoach.context_builder import ContextBuilder

    session = Session(
        session_id="test01",
        car_id="ferrari_458_gt2",
        track_id="ks_nurburgring_sprint",
        recorded_at="2026-03-09T10:00:00+00:00",
        source="mock",
        laps=[_make_lap(0, 120000), _make_lap(1, 118000), _make_lap(2, 117000)],
    )
    builder = ContextBuilder(resample_points=50)
    context = builder.build(session)

    assert context.best_lap.lap_id == 2
    assert context.best_lap.is_best is True
    assert len(context.best_lap.trace) == 50
    assert context.valid_laps == 3


def test_context_builder_no_valid_laps():
    from simcoach.context_builder import ContextBuilder

    session = Session(
        session_id="test02",
        car_id="test_car",
        track_id="test_track",
        recorded_at="2026-03-09T10:00:00+00:00",
        source="mock",
        laps=[Lap(lap_id=0, lap_time_ms=5000, is_valid=False)],
    )
    builder = ContextBuilder()
    with pytest.raises(ValueError):
        builder.build(session)


# ── Mock telemetry source ──────────────────────────────────────────────────────

def test_mock_source_generates_frames():
    from simcoach.telemetry_bridge.mock_source import MockTelemetrySource

    src = MockTelemetrySource(n_laps=2, seed=1)
    assert src.connect() is True
    assert src.car_id == "ferrari_458_gt2"

    frames = []
    for _ in range(500):
        f = src.read_frame()
        if f is not None:
            frames.append(f)
        if src.is_done:
            break

    src.disconnect()
    assert len(frames) > 10
    assert all(0.0 <= f.normalized_track_position <= 1.0 for f in frames)


# ── ReferenceManager ──────────────────────────────────────────────────────────

def test_reference_manager_save_load(tmp_path):
    from simcoach.reference import ReferenceManager

    session = Session(
        session_id="ref01",
        car_id="ferrari_458_gt2",
        track_id="ks_nurburgring_sprint",
        recorded_at="2026-03-09T10:00:00+00:00",
        source="mock",
        laps=[_make_lap(0, 118000)],
    )
    mgr = ReferenceManager(pb_dir=str(tmp_path / "pb"))

    # No existing PB — should save
    updated, pb = mgr.update_pb_if_faster(session, session.laps[0])
    assert updated is True
    assert pb.lap_time_ms == 118000

    # Same session again — PB should NOT update
    updated2, pb2 = mgr.update_pb_if_faster(session, session.laps[0])
    assert updated2 is False

    # Faster lap — should update
    faster_lap = _make_lap(0, 116000)
    updated3, pb3 = mgr.update_pb_if_faster(session, faster_lap)
    assert updated3 is True
    assert pb3.lap_time_ms == 116000


# ── World position fields ──────────────────────────────────────────────────────

def test_frame_world_pos_defaults_to_none():
    """world_pos_x/y/z default to None for frames that don't set them."""
    f = _make_frame(0.5)
    assert f.world_pos_x is None
    assert f.world_pos_y is None
    assert f.world_pos_z is None


def test_frame_world_pos_set():
    """world_pos_x/y/z accept arbitrary signed floats."""
    f = TelemetryFrame(
        timestamp=0, lap_id=0,
        normalized_track_position=0.5,
        speed_kmh=100, throttle=0.5, brake=0.0,
        steering=0.0, gear=3, rpm=5000,
        world_pos_x=142.35, world_pos_y=0.0, world_pos_z=-201.88,
    )
    assert abs(f.world_pos_x - 142.35) < 0.01
    assert f.world_pos_y == 0.0
    assert abs(f.world_pos_z - (-201.88)) < 0.01


def test_mock_source_generates_world_pos():
    """MockTelemetrySource populates world_pos_x/z on every frame."""
    from simcoach.telemetry_bridge.mock_source import MockTelemetrySource

    src = MockTelemetrySource(n_laps=1, seed=42)
    src.connect()
    frames = []
    for _ in range(2000):
        f = src.read_frame()
        if f is not None:
            frames.append(f)
        if src.is_done:
            break
    src.disconnect()

    assert len(frames) > 10
    assert all(f.world_pos_x is not None for f in frames)
    assert all(f.world_pos_z is not None for f in frames)
    xs = [f.world_pos_x for f in frames]
    assert max(xs) - min(xs) > 100  # track spans at least 100 m in X


def test_resample_includes_world_pos_keys():
    """resample_trace emits wx/wz keys; None when frames have no position."""
    frames = [_make_frame(i / 99) for i in range(100)]  # no world_pos set
    result = resample_trace(frames, n_points=10)
    assert all("wx" in p and "wz" in p for p in result)
    assert all(p["wx"] is None for p in result)

    # With position data set
    frames_with_pos = []
    for i in range(100):
        pos = i / 99
        f = TelemetryFrame(
            timestamp=pos * 120, lap_id=0,
            normalized_track_position=pos,
            speed_kmh=100, throttle=0.5, brake=0.0,
            steering=0.0, gear=3, rpm=5000,
            world_pos_x=float(i), world_pos_z=float(-i),
        )
        frames_with_pos.append(f)

    result2 = resample_trace(frames_with_pos, n_points=10)
    assert all(p["wx"] is not None for p in result2)
    assert all(p["wz"] is not None for p in result2)
