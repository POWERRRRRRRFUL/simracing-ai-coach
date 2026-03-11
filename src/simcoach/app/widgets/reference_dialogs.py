"""Dialogs for reference lap export and import workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from simcoach.models.telemetry import Lap


class ExportLapDialog(QDialog):
    """Dialog for selecting a lap to export as a .simcoachref file."""

    def __init__(self, valid_laps: list[Lap], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Reference Lap")
        self.setMinimumWidth(380)
        self._valid_laps = valid_laps
        self._selected: Lap | None = None
        self._build_ui()

    @property
    def selected_lap(self) -> Lap | None:
        return self._selected

    # ── Internal ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Description
        desc = QLabel(
            "Reference laps can be shared with other drivers for telemetry comparison."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; padding: 8px 12px; "
                           "background: #f0f4ff; border-radius: 6px; "
                           "color: #1d1d1f;")
        layout.addWidget(desc)

        # Lap list
        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        self._list.setMinimumHeight(140)
        layout.addWidget(self._list)

        # Populate laps
        best_time = min(l.lap_time_ms for l in self._valid_laps)
        best_index = 0
        for i, lap in enumerate(self._valid_laps):
            is_best = lap.lap_time_ms == best_time
            label = f"Lap {lap.lap_id + 1}  —  {lap.lap_time_str}"
            if is_best:
                label += "  (Best)"
                best_index = i
            item = QListWidgetItem(label)
            if is_best:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self._list.addItem(item)

        self._list.setCurrentRow(best_index)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)

        # Button row — explicit QPushButton instances so theme class props apply
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setProperty("class", "secondary")
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)

        self._ok_btn = QPushButton("Select Lap")
        self._ok_btn.setProperty("class", "primary")
        self._ok_btn.clicked.connect(self._accept)
        btn_row.addWidget(self._ok_btn)

        layout.addLayout(btn_row)

    def _on_selection_changed(self) -> None:
        self._ok_btn.setEnabled(bool(self._list.selectedItems()))

    def _accept(self) -> None:
        row = self._list.currentRow()
        if 0 <= row < len(self._valid_laps):
            self._selected = self._valid_laps[row]
            self.accept()
