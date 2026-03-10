"""Settings card widget — provider, API key, model, auto-open toggle."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from simcoach.config.settings import AppConfig


class SettingsCard(QFrame):
    """Collapsible settings card exposing the 4 user-facing config fields."""

    save_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("class", "card")
        self._build_ui()

    # ── Public API ──────────────────────────────────────────────────────────

    def load_from_config(self, config: AppConfig) -> None:
        self._base_url.setText(config.llm.base_url)
        self._api_key.setText(config.llm.api_key)
        self._model.setText(config.llm.model)
        self._auto_open.setChecked(config.report.open_browser)

    def apply_to_config(self, config: AppConfig) -> AppConfig:
        """Return a new AppConfig with the widget values applied."""
        data = config.model_dump()
        data["llm"]["base_url"] = self._base_url.text().strip()
        data["llm"]["api_key"] = self._api_key.text().strip()
        data["llm"]["model"] = self._model.text().strip()
        data["report"]["open_browser"] = self._auto_open.isChecked()
        return AppConfig.model_validate(data)

    # ── Internal ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(0)   # Controlled per-field via addSpacing()

        # Section title
        title = QLabel("SETTINGS")
        title.setProperty("class", "section-title")
        layout.addWidget(title)
        layout.addSpacing(14)

        # Provider base URL
        layout.addWidget(self._make_label("Provider Base URL"))
        layout.addSpacing(4)
        self._base_url = QLineEdit()
        self._base_url.setPlaceholderText("https://api.openai.com/v1")
        layout.addWidget(self._base_url)
        layout.addSpacing(12)

        # API key
        layout.addWidget(self._make_label("API Key"))
        layout.addSpacing(4)
        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        key_row.setContentsMargins(0, 0, 0, 0)
        self._api_key = QLineEdit()
        self._api_key.setPlaceholderText("sk-...")
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        key_row.addWidget(self._api_key)

        self._eye_btn = QPushButton("👁")
        self._eye_btn.setProperty("class", "icon-btn")
        self._eye_btn.setToolTip("Toggle visibility")
        self._eye_btn.setCheckable(True)
        self._eye_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self._eye_btn)
        layout.addLayout(key_row)
        layout.addSpacing(12)

        # Model
        layout.addWidget(self._make_label("Model"))
        layout.addSpacing(4)
        self._model = QLineEdit()
        self._model.setPlaceholderText("gpt-4o-mini")
        layout.addWidget(self._model)
        layout.addSpacing(14)

        # Auto-open report
        self._auto_open = QCheckBox("Open report in browser automatically")
        layout.addWidget(self._auto_open)
        layout.addSpacing(16)

        # Save button — lambda avoids passing clicked(bool) to parameterless signal
        save_btn = QPushButton("Save Settings")
        save_btn.setProperty("class", "secondary")
        save_btn.clicked.connect(lambda: self.save_clicked.emit())
        layout.addWidget(save_btn)

    def _toggle_key_visibility(self, checked: bool) -> None:
        if checked:
            self._api_key.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self._api_key.setEchoMode(QLineEdit.EchoMode.Password)

    @staticmethod
    def _make_label(text: str) -> QLabel:
        """Small muted field label — no negative margins to avoid clipping."""
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 12px; color: #86868b;")
        lbl.setWordWrap(True)
        return lbl
