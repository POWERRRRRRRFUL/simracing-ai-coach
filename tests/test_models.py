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


# ── SimcoachReference ─────────────────────────────────────────────────────────

def _make_session() -> Session:
    return Session(
        session_id="ref_test_01",
        car_id="ferrari_458_gt2",
        track_id="ks_nurburgring_sprint",
        recorded_at="2026-03-09T10:00:00+00:00",
        source="mock",
        laps=[_make_lap(0, 118000), _make_lap(1, 116000)],
    )


def test_simcoachref_from_lap():
    """Create a SimcoachReference from a session lap."""
    from simcoach.models.reference import SimcoachReference

    session = _make_session()
    ref = SimcoachReference.from_lap(session, session.laps[1], trace_points=50)

    assert ref.metadata.car_id == "ferrari_458_gt2"
    assert ref.metadata.track_id == "ks_nurburgring_sprint"
    assert ref.metadata.lap_time_ms == 116000
    assert ref.trace.n_points == 50
    assert len(ref.trace.pos) == 50
    assert ref.stats is not None


def test_simcoachref_roundtrip():
    """Serialize and deserialize a SimcoachReference."""
    import json
    from simcoach.models.reference import SimcoachReference

    session = _make_session()
    ref = SimcoachReference.from_lap(session, session.laps[0], trace_points=20)

    # Serialize
    data = ref.model_dump()
    json_str = json.dumps(data)

    # Deserialize
    ref2 = SimcoachReference.model_validate(json.loads(json_str))
    assert ref2.metadata.lap_time_ms == ref.metadata.lap_time_ms
    assert ref2.trace.n_points == ref.trace.n_points
    assert len(ref2.trace.spd) == 20


def test_simcoachref_to_trace_dicts():
    """to_trace_dicts() converts columnar back to row-based."""
    from simcoach.models.reference import SimcoachReference

    session = _make_session()
    ref = SimcoachReference.from_lap(session, session.laps[0], trace_points=10)
    dicts = ref.to_trace_dicts()

    assert len(dicts) == 10
    assert all("pos" in d and "spd" in d and "str" in d for d in dicts)
    # Verify values match columnar data
    assert dicts[0]["pos"] == ref.trace.pos[0]
    assert dicts[0]["spd"] == ref.trace.spd[0]


def test_simcoachref_from_reference_lap():
    """Convert a legacy ReferenceLap to SimcoachReference."""
    from simcoach.models.reference import SimcoachReference
    from simcoach.models.telemetry import ReferenceLap

    frames = [_make_frame(i / 99) for i in range(100)]
    ref_lap = ReferenceLap(
        source="personal_best",
        car_id="test_car",
        track_id="test_track",
        lap_time_ms=120000,
        session_id="s001",
        frames=frames,
    )
    ref = SimcoachReference.from_reference_lap(ref_lap, trace_points=25)
    assert ref.metadata.car_id == "test_car"
    assert ref.metadata.lap_time_ms == 120000
    assert ref.trace.n_points == 25


def test_export_import_cycle(tmp_path):
    """Export a lap → import the file → verify data matches."""
    from simcoach.reference import ReferenceManager

    session = _make_session()
    mgr = ReferenceManager(
        pb_dir=str(tmp_path / "pb"),
        library_dir=str(tmp_path / "lib"),
        trace_points=50,
    )

    # Export
    out = mgr.export_ref(session, session.laps[1], source="exported")
    assert out.exists()
    assert out.suffix == ".simcoachref"

    # Import
    ref = mgr.import_ref(out)
    assert ref.metadata.car_id == "ferrari_458_gt2"
    assert ref.metadata.lap_time_ms == 116000
    assert ref.trace.n_points == 50


def test_load_active_resolution(tmp_path):
    """Test active reference resolution: active.json → pb.simcoachref → pb.json."""
    from simcoach.reference import ReferenceManager

    session = _make_session()
    mgr = ReferenceManager(
        pb_dir=str(tmp_path / "pb"),
        library_dir=str(tmp_path / "lib"),
        trace_points=50,
    )

    # No references at all → None
    assert mgr.load_active("ferrari_458_gt2", "ks_nurburgring_sprint") is None

    # Save PB (creates both pb.json and pb.simcoachref)
    mgr.update_pb_if_faster(session, session.laps[1])

    # load_active should find pb.simcoachref
    from simcoach.models.reference import SimcoachReference
    active = mgr.load_active("ferrari_458_gt2", "ks_nurburgring_sprint")
    assert active is not None
    assert isinstance(active, SimcoachReference)
    assert active.metadata.lap_time_ms == 116000


def test_backward_compat_legacy_pb(tmp_path):
    """When only legacy pb.json exists, load_active falls back to it."""
    import json
    from simcoach.models.telemetry import ReferenceLap
    from simcoach.reference import ReferenceManager
    from simcoach.utils.sampling import compute_lap_stats

    mgr = ReferenceManager(
        pb_dir=str(tmp_path / "pb"),
        library_dir=str(tmp_path / "lib"),
        trace_points=50,
    )

    # Manually create a legacy pb.json (no .simcoachref)
    frames = [_make_frame(i / 99) for i in range(100)]
    stats = compute_lap_stats(frames)
    ref_lap = ReferenceLap(
        source="personal_best",
        car_id="test_car",
        track_id="test_track",
        lap_time_ms=115000,
        session_id="legacy_s",
        frames=frames,
        stats=stats,
    )
    pb_dir = tmp_path / "pb" / "test_car" / "test_track"
    pb_dir.mkdir(parents=True)
    with open(pb_dir / "pb.json", "w") as f:
        json.dump(ref_lap.model_dump(), f)

    # load_active should fall back to legacy pb.json
    active = mgr.load_active("test_car", "test_track")
    assert active is not None
    assert isinstance(active, ReferenceLap)
    assert active.lap_time_ms == 115000


def test_set_active_reference(tmp_path):
    """Set a specific reference as active and verify load_active picks it up."""
    from simcoach.models.reference import SimcoachReference
    from simcoach.reference import ReferenceManager

    session = _make_session()
    mgr = ReferenceManager(
        pb_dir=str(tmp_path / "pb"),
        library_dir=str(tmp_path / "lib"),
        trace_points=50,
    )

    # Create PB
    mgr.update_pb_if_faster(session, session.laps[1])

    # Export a different lap
    out = mgr.export_ref(session, session.laps[0], source="exported")

    # Set the exported ref as active
    mgr.set_active("ferrari_458_gt2", "ks_nurburgring_sprint", out.name)

    # load_active should now return the exported ref (118000ms) not the PB (116000ms)
    active = mgr.load_active("ferrari_458_gt2", "ks_nurburgring_sprint")
    assert isinstance(active, SimcoachReference)
    assert active.metadata.lap_time_ms == 118000


def test_list_refs(tmp_path):
    """list_refs returns all .simcoachref files for a car+track."""
    from simcoach.reference import ReferenceManager

    session = _make_session()
    mgr = ReferenceManager(
        pb_dir=str(tmp_path / "pb"),
        library_dir=str(tmp_path / "lib"),
        trace_points=50,
    )

    # Create PB + export
    mgr.update_pb_if_faster(session, session.laps[1])
    mgr.export_ref(session, session.laps[0], source="exported")

    refs = mgr.list_refs("ferrari_458_gt2", "ks_nurburgring_sprint")
    assert len(refs) >= 2
    names = [r["name"] for r in refs]
    assert any("pb.simcoachref" in n for n in names)


def test_context_builder_with_simcoachref():
    """ContextBuilder.build() works with a SimcoachReference input."""
    from simcoach.context_builder import ContextBuilder
    from simcoach.models.reference import SimcoachReference

    session = _make_session()
    ref = SimcoachReference.from_lap(session, session.laps[0], trace_points=100)

    builder = ContextBuilder(resample_points=20)
    context = builder.build(session, reference_lap=ref)

    assert context.reference_lap is not None
    assert context.reference_lap.is_reference is True
    assert context.delta_vs_reference_ms is not None
