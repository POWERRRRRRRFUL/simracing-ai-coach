"""Main application window — assembles all widgets and wires signals."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsDropShadowEffect,
    QLabel,
    QHBoxLayout,
    QMessageBox,
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
from simcoach.app.widgets.reference_dialogs import ExportLapDialog


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
            "font-size: 22px; font-weight: 700; color: #e8eaf0; letter-spacing: -0.3px;"
        )
        header.addWidget(title)

        version = QLabel(f"v{__version__}")
        version.setStyleSheet("font-size: 12px; color: #7a7f9a; padding-top: 8px;")
        header.addWidget(version)
        header.addStretch()

        layout.addLayout(header)

        subtitle = QLabel("AI-powered post-session racing coach for Assetto Corsa")
        subtitle.setStyleSheet("font-size: 13px; color: #7a7f9a;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Accent separator — mirrors the report's header border-bottom
        from PySide6.QtWidgets import QFrame as _QFrame
        sep = _QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #2e3250; margin: 2px 0;")
        layout.addWidget(sep)

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
        self._actions.export_ref_clicked.connect(self._export_reference)
        self._actions.import_ref_clicked.connect(self._import_reference)

    # ── Settings ────────────────────────────────────────────────────────────

    def _load_settings(self) -> None:
        config = self._service.get_config()
        self._settings.load_from_config(config)

    def _save_settings(self) -> None:
        try:
            config = self._settings.apply_to_config(self._service.get_config())
            self._service.save_settings(config)
            cfg_path = self._service.get_config_path()
            self._log(f"Settings saved → {cfg_path}")
            # Refresh the displayed values to reflect exactly what was persisted
            self._load_settings()
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

    # ── Reference export / import ────────────────────────────────────────────

    def _get_current_session(self):
        """Return the most recent session from memory or the latest file on disk."""
        if self._last_session:
            return self._last_session
        s = self._service.get_last_session()
        if s:
            return s
        path = self._service.get_latest_session()
        if path:
            try:
                return self._service.load_session(path)
            except Exception:
                pass
        return None

    def _export_reference(self) -> None:
        # ── Step 1: choose source ────────────────────────────────────────────
        src_msg = QMessageBox(self)
        src_msg.setWindowTitle("Export Reference Lap")
        src_msg.setText("Which session do you want to export from?")
        current_btn = src_msg.addButton(
            "Latest Session", QMessageBox.ButtonRole.AcceptRole
        )
        file_btn = src_msg.addButton(
            "Choose File…", QMessageBox.ButtonRole.ActionRole
        )
        src_msg.addButton(QMessageBox.StandardButton.Cancel)
        src_msg.exec()

        clicked = src_msg.clickedButton()
        if clicked is current_btn:
            session = self._get_current_session()
            if session is None:
                self._log(
                    "No session available. Run a recording or Demo Analysis first."
                )
                return
        elif clicked is file_btn:
            session_dir = str(Path(self._service.get_config().recorder.output_dir))
            session_file, _ = QFileDialog.getOpenFileName(
                self,
                "Choose Session File",
                session_dir,
                "Session Files (session_*.json);;JSON Files (*.json)",
            )
            if not session_file:
                return
            try:
                session = self._service.load_session(Path(session_file))
            except Exception as exc:
                self._log(f"Could not load session: {exc}")
                QMessageBox.critical(self, "Load Failed", str(exc))
                return
        else:
            return  # Cancel / window-close

        # ── Step 2: lap selection ────────────────────────────────────────────
        valid_laps = [l for l in session.laps if l.is_valid and l.frames]
        if not valid_laps:
            self._log("No valid laps in that session to export.")
            return

        dialog = ExportLapDialog(valid_laps, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        lap = dialog.selected_lap
        if lap is None:
            return

        # ── Step 3: save destination ─────────────────────────────────────────
        default_name = f"{session.car_id}_{session.track_id}_{lap.lap_time_ms}.simcoachref"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Reference Lap",
            default_name,
            "SimCoach Reference (*.simcoachref)",
        )
        if not file_path:
            return

        try:
            out_path = self._service.export_reference(session, lap.lap_id, Path(file_path))
            self._log(f"Reference exported: {out_path.name}")
            QMessageBox.information(
                self,
                "Export Successful",
                f"Reference lap exported to:\n{out_path}",
            )
        except Exception as exc:
            self._log(f"Export error: {exc}")
            QMessageBox.critical(self, "Export Failed", str(exc))

    def _import_reference(self) -> None:
        QMessageBox.information(
            self,
            "Import Reference Lap",
            "Import a .simcoachref file shared by another driver.",
        )

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Reference Lap",
            "",
            "SimCoach Reference (*.simcoachref)",
        )
        if not file_path:
            return

        try:
            ref, dest_path = self._service.import_reference(Path(file_path))
        except Exception as exc:
            self._log(f"Import error: {exc}")
            QMessageBox.critical(self, "Import Failed", str(exc))
            return

        m = ref.metadata
        time_s = m.lap_time_ms / 1000.0
        mins, secs = int(time_s // 60), time_s % 60
        summary = f"Car:   {m.car_id}\nTrack: {m.track_id}\nTime:  {mins}:{secs:06.3f}"
        if m.driver_name:
            summary += f"\nDriver: {m.driver_name}"

        reply = QMessageBox.question(
            self,
            "Reference Imported",
            f"Successfully imported reference lap.\n\n{summary}\n\nSet this reference as active?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._service.set_active_reference(m.car_id, m.track_id, dest_path.name)
                self._log(f"Active reference set: {dest_path.name}")
            except Exception as exc:
                self._log(f"Could not set active reference: {exc}")

        self._log(f"Reference imported: {Path(file_path).name}")

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
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 60))
        widget.setGraphicsEffect(shadow)
