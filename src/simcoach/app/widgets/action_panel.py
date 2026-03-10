"""Action panel — primary and secondary action buttons."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QVBoxLayout


class ActionPanel(QFrame):
    """Panel containing all user-facing action buttons."""

    start_clicked = Signal()
    stop_clicked = Signal()
    open_report_clicked = Signal()
    open_folder_clicked = Signal()
    demo_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    # ── Public API ──────────────────────────────────────────────────────────

    def set_recording(self, is_recording: bool) -> None:
        self._start_btn.setEnabled(not is_recording)
        self._stop_btn.setEnabled(is_recording)
        self._demo_btn.setEnabled(not is_recording)

    def set_analyzing(self, is_analyzing: bool) -> None:
        self._start_btn.setEnabled(not is_analyzing)
        self._stop_btn.setEnabled(False)
        self._demo_btn.setEnabled(not is_analyzing)

    def set_report_available(self, available: bool) -> None:
        self._report_btn.setEnabled(available)

    def reset(self) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._demo_btn.setEnabled(True)

    # ── Internal ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Start Recording — lambda prevents the clicked(bool) arg from reaching
        # the parameterless Signal(), which would cause a PySide6 TypeError.
        self._start_btn = QPushButton("Start Recording")
        self._start_btn.setProperty("class", "primary")
        self._start_btn.clicked.connect(lambda: self.start_clicked.emit())
        layout.addWidget(self._start_btn)

        # Stop & Analyze
        self._stop_btn = QPushButton("Stop && Analyze")
        self._stop_btn.setProperty("class", "danger")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(lambda: self.stop_clicked.emit())
        layout.addWidget(self._stop_btn)

        # Utility row
        util_row = QHBoxLayout()
        util_row.setSpacing(10)

        self._report_btn = QPushButton("Open Last Report")
        self._report_btn.setProperty("class", "secondary")
        self._report_btn.setEnabled(False)
        self._report_btn.clicked.connect(lambda: self.open_report_clicked.emit())
        util_row.addWidget(self._report_btn)

        self._folder_btn = QPushButton("Open Output Folder")
        self._folder_btn.setProperty("class", "secondary")
        self._folder_btn.clicked.connect(lambda: self.open_folder_clicked.emit())
        util_row.addWidget(self._folder_btn)

        layout.addLayout(util_row)

        # Demo Analysis — distinct signal, never wired to RecordingWorker
        self._demo_btn = QPushButton("Demo Analysis")
        self._demo_btn.setProperty("class", "tertiary")
        self._demo_btn.clicked.connect(lambda: self.demo_clicked.emit())
        layout.addWidget(self._demo_btn)
