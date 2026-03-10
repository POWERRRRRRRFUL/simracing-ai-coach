"""Main application window — assembles all widgets and wires signals."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QLabel,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from simcoach.app import __version__
from simcoach.app.service import AppService
from simcoach.app.widgets.action_panel import ActionPanel
from simcoach.app.widgets.log_panel import LogPanel
from simcoach.app.widgets.settings_card import SettingsCard
from simcoach.app.widgets.status_bar import StatusBar
from simcoach.app.workers import AnalysisWorker, DemoWorker, RecordingWorker


class MainWindow(QWidget):
    """Top-level application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("simcoach")
        self.resize(500, 740)
        self.setMinimumSize(420, 600)

        self._service = AppService()
        self._recording_thread: QThread | None = None
        self._recording_worker: RecordingWorker | None = None
        self._analysis_thread: QThread | None = None
        self._analysis_worker: AnalysisWorker | DemoWorker | None = None
        self._last_session = None

        self._build_ui()
        self._connect_signals()
        self._load_settings()

        # Check if there's already a report available
        if self._service.get_latest_report():
            self._actions.set_report_available(True)

        # Start AC detection polling
        self._ac_timer = QTimer(self)
        self._ac_timer.timeout.connect(self._check_ac_status)
        self._ac_timer.start(3000)
        self._check_ac_status()  # immediate first check

        self._log("simcoach desktop app started.")

    # ── UI Construction ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scroll area wrapping the entire content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        container = QWidget()
        container.setObjectName("centralWidget")
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # ── Header ──────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel("simcoach")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #1d1d1f; letter-spacing: -0.5px;"
        )
        header.addWidget(title)

        version = QLabel(f"v{__version__}")
        version.setStyleSheet("font-size: 12px; color: #aeaeb2; padding-top: 8px;")
        header.addWidget(version)
        header.addStretch()

        layout.addLayout(header)

        subtitle = QLabel("AI-powered post-session racing coach for Assetto Corsa")
        subtitle.setStyleSheet("font-size: 13px; color: #86868b;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # ── Settings card ───────────────────────────────────────────────────
        self._settings = SettingsCard()
        self._add_card_shadow(self._settings)
        layout.addWidget(self._settings)

        # ── Status bar ──────────────────────────────────────────────────────
        self._status = StatusBar()
        layout.addWidget(self._status)

        # ── Action panel ────────────────────────────────────────────────────
        self._actions = ActionPanel()
        layout.addWidget(self._actions)

        # ── Log panel ───────────────────────────────────────────────────────
        self._log_panel = LogPanel()
        self._add_card_shadow(self._log_panel)
        layout.addWidget(self._log_panel, stretch=1)

    def _connect_signals(self) -> None:
        self._settings.save_clicked.connect(self._save_settings)
        self._actions.start_clicked.connect(self._start_recording)
        self._actions.stop_clicked.connect(self._stop_recording)
        self._actions.open_report_clicked.connect(self._open_last_report)
        self._actions.open_folder_clicked.connect(self._open_output_folder)
        self._actions.demo_clicked.connect(self._run_demo)

    # ── Settings ────────────────────────────────────────────────────────────

    def _load_settings(self) -> None:
        config = self._service.get_config()
        self._settings.load_from_config(config)

    def _save_settings(self) -> None:
        try:
            config = self._settings.apply_to_config(self._service.get_config())
            self._service.save_settings(config)
            self._log("Settings saved.")
        except Exception as exc:
            self._log(f"ERROR saving settings: {exc}")

    # ── AC Detection ────────────────────────────────────────────────────────

    def _check_ac_status(self) -> None:
        connected = self._service.detect_ac()
        if connected:
            info = self._service.get_ac_info()
            label = f"{info[1]}" if info else ""
            self._status.set_ac_status(True, label)
        else:
            self._status.set_ac_status(False)

    # ── Recording ───────────────────────────────────────────────────────────

    def _start_recording(self) -> None:
        # The GUI always records from the real AC source.
        # config.recorder.source is a CLI setting and must not bleed into the GUI.
        source_type = "ac_shared_memory"

        # Guard: refuse to start if AC does not have an active session.
        if not self._service.detect_ac():
            self._log(
                "Assetto Corsa not detected. "
                "Start a session in AC first, then click Start Recording."
            )
            return

        self._log("Starting recording (source: ac_shared_memory)...")
        self._status.set_app_state("recording")
        self._actions.set_recording(True)

        self._recording_thread = QThread()
        self._recording_worker = RecordingWorker(
            self._service, source_type=source_type
        )
        self._recording_worker.moveToThread(self._recording_thread)

        self._recording_thread.started.connect(self._recording_worker.run)
        self._recording_worker.progress.connect(self._on_recording_progress)
        self._recording_worker.lap_complete.connect(self._on_lap_complete)
        self._recording_worker.finished.connect(self._on_recording_finished)
        self._recording_worker.error.connect(self._on_recording_error)
        self._recording_worker.finished.connect(self._recording_thread.quit)
        self._recording_worker.error.connect(self._recording_thread.quit)

        self._recording_thread.start()

    def _stop_recording(self) -> None:
        self._log("Stop requested — finishing current lap...")
        self._service.stop_recording()

    def _on_recording_progress(self, lap_id: int, frame_count: int) -> None:
        self._status.set_app_state("recording")

    def _on_lap_complete(self, lap_id: int, time_str: str) -> None:
        self._log(f"Lap {lap_id + 1} complete — {time_str}")

    def _on_recording_finished(self, session) -> None:
        valid = sum(1 for l in session.laps if l.is_valid)
        self._log(
            f"Recording finished — {len(session.laps)} laps ({valid} valid), "
            f"{len(session.raw_frames)} frames."
        )
        self._actions.set_recording(False)
        self._last_session = session

        # Auto-start analysis
        self._start_analysis(session)

    def _on_recording_error(self, msg: str) -> None:
        self._log(f"Recording error: {msg}")
        self._status.set_app_state("error")
        self._actions.reset()

    # ── Analysis ────────────────────────────────────────────────────────────

    def _start_analysis(self, session) -> None:
        self._log("Starting analysis...")
        self._status.set_app_state("analyzing")
        self._actions.set_analyzing(True)

        self._analysis_thread = QThread()
        self._analysis_worker = AnalysisWorker(self._service, session)
        self._analysis_worker.moveToThread(self._analysis_thread)

        self._analysis_thread.started.connect(self._analysis_worker.run)
        self._analysis_worker.stage.connect(self._on_analysis_stage)
        self._analysis_worker.finished.connect(self._on_analysis_finished)
        self._analysis_worker.error.connect(self._on_analysis_error)
        self._analysis_worker.finished.connect(self._analysis_thread.quit)
        self._analysis_worker.error.connect(self._analysis_thread.quit)

        self._analysis_thread.start()

    def _on_analysis_stage(self, msg: str) -> None:
        self._log(msg)

    def _on_analysis_finished(self, report_path: str, had_llm: bool) -> None:
        self._log(f"Report generated: {report_path}")
        if not had_llm:
            self._log("Note: No API key set — AI analysis was skipped.")
        self._status.set_app_state("done")
        self._actions.reset()
        self._actions.set_report_available(True)

        # Auto-open if enabled
        config = self._service.get_config()
        if config.report.open_browser:
            self._service.open_report(Path(report_path))
            self._log("Report opened in browser.")

    def _on_analysis_error(self, msg: str) -> None:
        self._log(f"Analysis error: {msg}")
        self._status.set_app_state("error")
        self._actions.reset()

    # ── Demo ────────────────────────────────────────────────────────────────

    def _run_demo(self) -> None:
        self._log("Running demo analysis...")
        self._status.set_app_state("analyzing")
        self._actions.set_analyzing(True)

        self._analysis_thread = QThread()
        self._analysis_worker = DemoWorker(self._service)
        self._analysis_worker.moveToThread(self._analysis_thread)

        self._analysis_thread.started.connect(self._analysis_worker.run)
        self._analysis_worker.stage.connect(self._on_analysis_stage)
        self._analysis_worker.finished.connect(self._on_analysis_finished)
        self._analysis_worker.error.connect(self._on_analysis_error)
        self._analysis_worker.finished.connect(self._analysis_thread.quit)
        self._analysis_worker.error.connect(self._analysis_thread.quit)

        self._analysis_thread.start()

    # ── Utility ─────────────────────────────────────────────────────────────

    def _open_last_report(self) -> None:
        path = self._service.get_latest_report()
        if path:
            self._service.open_report(path)
            self._log(f"Opened report: {path.name}")
        else:
            self._log("No reports found.")

    def _open_output_folder(self) -> None:
        config = self._service.get_config()
        self._service.open_folder(Path(config.report.output_dir))
        self._log("Opened output folder.")

    def _log(self, message: str) -> None:
        self._log_panel.append_log(message)

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        """Ensure clean shutdown of background threads."""
        self._ac_timer.stop()

        # Stop recording if active
        if self._recording_thread and self._recording_thread.isRunning():
            self._service.stop_recording()
            self._recording_thread.quit()
            self._recording_thread.wait(5000)

        # Wait for analysis if active
        if self._analysis_thread and self._analysis_thread.isRunning():
            self._analysis_thread.quit()
            self._analysis_thread.wait(5000)

        event.accept()

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _add_card_shadow(widget: QWidget) -> None:
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 25))
        widget.setGraphicsEffect(shadow)
