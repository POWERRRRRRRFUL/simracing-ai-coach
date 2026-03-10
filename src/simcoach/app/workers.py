"""Background workers for recording and analysis (QThread-based)."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from simcoach.app.service import AppService
from simcoach.models.telemetry import Session


class RecordingWorker(QObject):
    """Runs SessionRecorder.record() on a background QThread."""

    # Signals emitted back to the UI thread
    progress = Signal(int, int)           # (lap_id, frame_count)
    lap_complete = Signal(int, str)       # (lap_id, lap_time_str)
    finished = Signal(object)             # Session object
    error = Signal(str)                   # error message

    def __init__(
        self,
        service: AppService,
        source_type: str = "ac_shared_memory",
        mock_laps: int = 5,
    ) -> None:
        super().__init__()
        self._service = service
        self._source_type = source_type
        self._mock_laps = mock_laps

    @Slot()
    def run(self) -> None:
        try:
            recorder = self._service.create_recorder(
                self._source_type, self._mock_laps
            )

            # Wire lap-complete callback → signal
            recorder._on_lap_complete = self._on_lap

            is_mock = self._source_type != "ac_shared_memory"
            session = recorder.record(
                progress_callback=self._on_progress,
                fast_mode=is_mock,
            )

            if session and session.laps:
                self._service.save_session(session)
                self.finished.emit(session)
            else:
                self.error.emit("No valid laps recorded.")
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self._service.disconnect_source()

    def _on_progress(self, lap_id: int, frame_count: int) -> None:
        self.progress.emit(lap_id, frame_count)

    def _on_lap(self, lap) -> None:
        self.lap_complete.emit(lap.lap_id, lap.lap_time_str)


class AnalysisWorker(QObject):
    """Runs the full analysis pipeline on a background QThread."""

    stage = Signal(str)            # current stage description
    finished = Signal(str, bool)   # (report_path, had_llm)
    error = Signal(str)            # error message

    def __init__(self, service: AppService, session: Session) -> None:
        super().__init__()
        self._service = service
        self._session = session

    @Slot()
    def run(self) -> None:
        try:
            report_path, had_llm = self._service.run_analysis(
                self._session,
                stage_callback=lambda msg: self.stage.emit(msg),
            )
            self.finished.emit(str(report_path), had_llm)
        except Exception as exc:
            self.error.emit(str(exc))


class DemoWorker(QObject):
    """Generates a demo session then analyses it."""

    stage = Signal(str)
    finished = Signal(str, bool)   # (report_path, had_llm)
    error = Signal(str)

    def __init__(self, service: AppService) -> None:
        super().__init__()
        self._service = service

    @Slot()
    def run(self) -> None:
        try:
            self.stage.emit("Generating demo session...")
            session = self._service.generate_demo_session()
            self.stage.emit("Demo session ready. Starting analysis...")

            report_path, had_llm = self._service.run_analysis(
                session,
                stage_callback=lambda msg: self.stage.emit(msg),
            )
            self.finished.emit(str(report_path), had_llm)
        except Exception as exc:
            self.error.emit(str(exc))
