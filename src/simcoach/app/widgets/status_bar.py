"""Status bar — AC connection pill + app state pill."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


def _restyle(label: QLabel, class_name: str) -> None:
    """Swap the QSS class property and force a re-polish."""
    label.setProperty("class", class_name)
    label.style().unpolish(label)
    label.style().polish(label)
    label.update()


class StatusBar(QFrame):
    """Horizontal bar with two status pills."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._ac_pill = QLabel("AC: Not Running")
        self._ac_pill.setProperty("class", "pill-danger")
        layout.addWidget(self._ac_pill)

        self._state_pill = QLabel("Idle")
        self._state_pill.setProperty("class", "pill-idle")
        layout.addWidget(self._state_pill)

        layout.addStretch()

    # ── Public API ──────────────────────────────────────────────────────────

    def set_ac_status(self, connected: bool, info: str = "") -> None:
        if connected:
            text = f"AC: Connected"
            if info:
                text += f" — {info}"
            self._ac_pill.setText(text)
            _restyle(self._ac_pill, "pill-success")
        else:
            self._ac_pill.setText("AC: Not Running")
            _restyle(self._ac_pill, "pill-danger")

    def set_app_state(self, state: str) -> None:
        """State: idle, recording, analyzing, done, error."""
        labels = {
            "idle": "Idle",
            "recording": "Recording...",
            "analyzing": "Analyzing...",
            "done": "Done",
            "error": "Error",
        }
        self._state_pill.setText(labels.get(state, state.title()))
        _restyle(self._state_pill, f"pill-{state}")
