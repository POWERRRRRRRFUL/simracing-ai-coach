"""AppService — facade over core simcoach modules for the desktop UI."""

from __future__ import annotations

import json
import os
import shutil
import webbrowser
from pathlib import Path
from typing import Any, Callable, Optional

from simcoach.config.settings import AppConfig, load_config, save_config
from simcoach.models.telemetry import Session, Lap
from simcoach.recorder.session_recorder import SessionRecorder
from simcoach.telemetry_bridge.base import TelemetrySource


class AppService:
    """High-level operations for the desktop application.

    All blocking work (recording, analysis) is intended to be called from
    background worker threads — not directly from the UI thread.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path: Path = config_path or Path("config.yaml")
        self._ensure_first_run()
        self._config: AppConfig = load_config(self._config_path)
        self._recorder: SessionRecorder | None = None
        self._source: TelemetrySource | None = None
        self._last_session: Session | None = None
        self._last_session_path: Path | None = None

    # ── Settings ────────────────────────────────────────────────────────────

    def load_settings(self) -> AppConfig:
        """Re-read configuration from disk."""
        self._config = load_config(self._config_path)
        return self._config

    def save_settings(self, config: AppConfig) -> None:
        """Persist configuration to config.yaml."""
        save_config(config, self._config_path)
        self._config = config

    def get_config(self) -> AppConfig:
        """Return the in-memory configuration (no disk I/O)."""
        return self._config

    # ── AC Detection ────────────────────────────────────────────────────────

    def detect_ac(self) -> bool:
        """Return True only when AC has an active driving session (LIVE or PAUSE).

        On Windows, AC's memory-mapped files can persist after the game exits
        until the next reboot — so merely opening the mmap is insufficient.
        We read ACGraphics.status and require it to be LIVE (2) or PAUSE (3).
        """
        try:
            from simcoach.telemetry_bridge.ac_shared_memory import (
                ACGraphics,
                ACSharedMemorySource,
                AC_STATUS_LIVE,
                AC_STATUS_PAUSE,
            )

            src = ACSharedMemorySource()
            if not src.connect():
                return False

            try:
                gfx = src._read_struct(ACGraphics, src._graphics_map)
                active = gfx.status in (AC_STATUS_LIVE, AC_STATUS_PAUSE)
            except Exception:
                active = False

            src.disconnect()
            return active
        except Exception:
            return False

    def get_ac_info(self) -> tuple[str, str] | None:
        """Return (car_id, track_id) when AC has an active session, else None."""
        try:
            from simcoach.telemetry_bridge.ac_shared_memory import (
                ACGraphics,
                ACSharedMemorySource,
                AC_STATUS_LIVE,
                AC_STATUS_PAUSE,
            )

            src = ACSharedMemorySource()
            if not src.connect():
                return None

            try:
                gfx = src._read_struct(ACGraphics, src._graphics_map)
                if gfx.status not in (AC_STATUS_LIVE, AC_STATUS_PAUSE):
                    src.disconnect()
                    return None
            except Exception:
                src.disconnect()
                return None

            info = (src.car_id, src.track_id)
            src.disconnect()
            return info
        except Exception:
            return None

    # ── Recording ───────────────────────────────────────────────────────────

    def create_recorder(
        self,
        source_type: str = "ac_shared_memory",
        mock_laps: int = 5,
    ) -> SessionRecorder:
        """Instantiate telemetry source and recorder.  Does NOT start recording.

        Raises ``ConnectionError`` if the source cannot connect.
        """
        if source_type == "ac_shared_memory":
            from simcoach.telemetry_bridge.ac_shared_memory import (
                ACSharedMemorySource,
            )

            self._source = ACSharedMemorySource()
        else:
            from simcoach.telemetry_bridge.mock_source import MockTelemetrySource

            self._source = MockTelemetrySource(n_laps=mock_laps, seed=42)

        if not self._source.connect():
            raise ConnectionError(
                f"Failed to connect to telemetry source ({source_type})."
            )

        self._recorder = SessionRecorder(
            source=self._source,
            sample_rate_hz=self._config.recorder.sample_rate_hz,
            output_dir=self._config.recorder.output_dir,
        )
        return self._recorder

    def get_recorder(self) -> SessionRecorder | None:
        return self._recorder

    def stop_recording(self) -> None:
        """Thread-safe signal to exit the recording loop."""
        if self._recorder is not None:
            self._recorder.request_stop()

    def save_session(self, session: Session) -> Path:
        """Persist session to JSON via the recorder."""
        if self._recorder is None:
            raise RuntimeError("No recorder available.")
        path = self._recorder.save(session)
        self._last_session = session
        self._last_session_path = path
        return path

    def disconnect_source(self) -> None:
        """Cleanly close the telemetry source."""
        if self._source is not None:
            try:
                self._source.disconnect()
            except Exception:
                pass
            self._source = None
        self._recorder = None

    # ── Analysis ────────────────────────────────────────────────────────────

    def load_session(self, path: Path) -> Session:
        """Deserialise a session JSON file."""
        with open(path, encoding="utf-8") as f:
            return Session.model_validate(json.load(f))

    def run_analysis(
        self,
        session: Session,
        stage_callback: Callable[[str], None] | None = None,
    ) -> tuple[Path, bool]:
        """Full analysis pipeline (blocking — call from worker thread).

        Returns ``(report_path, had_llm_analysis)``.
        """
        from simcoach.context_builder import ContextBuilder
        from simcoach.llm import LLMProvider, build_system_prompt, build_user_prompt
        from simcoach.reference import ReferenceManager
        from simcoach.report import ReportGenerator

        cfg = self._config

        def _stage(msg: str) -> None:
            if stage_callback:
                stage_callback(msg)

        # 1. Reference lap
        _stage("Loading reference lap...")
        ref_mgr = ReferenceManager(pb_dir=cfg.reference.pb_dir)
        reference_lap = ref_mgr.load_pb(session.car_id, session.track_id)

        # 2. Build context
        _stage("Building telemetry context...")
        builder = ContextBuilder(resample_points=cfg.context_builder.resample_points)
        context = builder.build(session, reference_lap)

        # 3. Chart traces
        _stage("Building chart traces...")
        chart_traces = builder.build_chart_traces(
            session, reference_lap, chart_points=cfg.context_builder.chart_points
        )

        # 4. LLM call (or placeholder)
        had_llm = False
        if cfg.llm.api_key:
            _stage(f"Calling {cfg.llm.model}...")
            context_json = builder.to_json(context)
            system_prompt = build_system_prompt()
            user_prompt = build_user_prompt(context_json)
            with LLMProvider(cfg.llm) as provider:
                llm_response = provider.complete(
                    system_prompt, user_prompt, json_mode=True
                )
            had_llm = True
        else:
            _stage("No API key — generating placeholder report...")
            llm_response = json.dumps(
                {
                    "best_lap_vs_reference": {
                        "summary": "No API key configured — AI analysis was not performed.",
                        "time_loss_sections": [],
                        "main_causes": [],
                    },
                    "session_findings": {
                        "consistency_note": "Add your API key in Settings and re-run analysis.",
                        "repeated_patterns": [],
                        "outliers": [],
                    },
                    "coaching_summary": {
                        "top_takeaways": [
                            "Telemetry collected and context built successfully",
                            "Configure your LLM provider to receive the full analysis",
                            "Review the telemetry charts for a manual overview",
                        ]
                    },
                    "next_training_focus": {
                        "priorities": [
                            {
                                "title": "Configure LLM",
                                "action": "Add your API key in Settings, then re-analyse.",
                            }
                        ]
                    },
                }
            )

        # 5. Generate report
        _stage("Generating HTML report...")
        gen = ReportGenerator(output_dir=cfg.report.output_dir)
        report = gen.build_report(
            context, llm_response, cfg.llm.model if had_llm else "no-llm",
            chart_traces=chart_traces,
        )
        report_path = gen.render_html(report, open_browser=False)

        # 6. Update personal best
        _stage("Updating personal best...")
        valid_laps = [l for l in session.laps if l.is_valid and l.frames]
        if valid_laps:
            best_lap_obj = min(valid_laps, key=lambda l: l.lap_time_ms)
            ref_mgr.update_pb_if_faster(session, best_lap_obj)

        _stage("Done.")
        return report_path, had_llm

    def generate_demo_session(self) -> Session:
        """Generate a synthetic session instantly (fast_mode=True)."""
        from simcoach.telemetry_bridge.mock_source import MockTelemetrySource

        src = MockTelemetrySource(n_laps=5, seed=7)
        src.connect()

        recorder = SessionRecorder(
            src,
            sample_rate_hz=25,
            output_dir=self._config.recorder.output_dir,
        )
        session = recorder.record(fast_mode=True)
        src.disconnect()

        path = recorder.save(session)
        self._last_session = session
        self._last_session_path = path
        return session

    # ── File utilities ──────────────────────────────────────────────────────

    def get_latest_session(self) -> Path | None:
        """Return the most recently modified session JSON, or None."""
        session_dir = Path(self._config.recorder.output_dir)
        if not session_dir.is_dir():
            return None
        files = sorted(session_dir.glob("session_*.json"), key=os.path.getmtime, reverse=True)
        return files[0] if files else None

    def get_latest_report(self) -> Path | None:
        """Return the most recently modified HTML report, or None."""
        report_dir = Path(self._config.report.output_dir)
        if not report_dir.is_dir():
            return None
        files = sorted(report_dir.glob("report_*.html"), key=os.path.getmtime, reverse=True)
        return files[0] if files else None

    def open_report(self, path: Path) -> None:
        """Open an HTML report in the default browser."""
        webbrowser.open(str(path.resolve()))

    def open_folder(self, path: Path) -> None:
        """Open a folder in Windows Explorer."""
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path.resolve()))

    # ── Internal ────────────────────────────────────────────────────────────

    def _ensure_first_run(self) -> None:
        """If config.yaml is missing, bootstrap from template (like ``simcoach init``)."""
        if self._config_path.exists():
            return

        # Locate template relative to the package
        pkg_root = Path(__file__).parent.parent.parent.parent
        example = pkg_root / "configs" / "config.example.yaml"
        if example.exists():
            shutil.copy(example, self._config_path)

        # Ensure output directories exist
        for d in ("output/sessions", "output/reports", "output/pb_laps"):
            Path(d).mkdir(parents=True, exist_ok=True)
