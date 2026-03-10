"""Log panel — read-only timestamped message log."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QFrame, QLabel, QPlainTextEdit, QVBoxLayout


MAX_LOG_LINES = 500


class LogPanel(QFrame):
    """Scrollable read-only log area with timestamped messages."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("class", "card")
        self._build_ui()

    def append_log(self, message: str) -> None:
        """Append a timestamped line and auto-scroll to bottom."""
        ts = datetime.now().strftime("%H:%M:%S")
        self._text.appendPlainText(f"[{ts}]  {message}")

        # Trim if exceeding max lines
        doc = self._text.document()
        if doc.blockCount() > MAX_LOG_LINES:
            cursor = self._text.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(
                cursor.MoveOperation.Down,
                cursor.MoveMode.KeepAnchor,
                doc.blockCount() - MAX_LOG_LINES,
            )
            cursor.removeSelectedText()
            cursor.deleteChar()  # remove the trailing newline

        # Auto-scroll
        scrollbar = self._text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_log(self) -> None:
        self._text.clear()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        title = QLabel("LOG")
        title.setProperty("class", "section-title")
        layout.addWidget(title)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setProperty("class", "log")
        self._text.setMinimumHeight(120)
        layout.addWidget(self._text)
