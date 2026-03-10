"""Apple-inspired light theme — color palette and QSS stylesheet."""

# ── Colour palette ───────────────────────────────────────────────────────────

BG_PRIMARY = "#f5f5f7"
BG_SECONDARY = "#fafafa"
SURFACE = "#ffffff"
BORDER = "#e5e5ea"
BORDER_FOCUS = "#007AFF"

TEXT_PRIMARY = "#1d1d1f"
TEXT_SECONDARY = "#86868b"
TEXT_PLACEHOLDER = "#aeaeb2"

ACCENT = "#007AFF"
ACCENT_HOVER = "#0056CC"
ACCENT_PRESSED = "#004099"
ACCENT_TEXT = "#ffffff"

SUCCESS = "#34C759"
SUCCESS_BG = "#e8f8ed"
WARNING = "#FF9500"
WARNING_BG = "#fff4e0"
DANGER = "#FF3B30"
DANGER_BG = "#fde8e7"

FONT_FAMILY = "'Segoe UI', system-ui, sans-serif"
FONT_MONO = "'Cascadia Code', 'Consolas', monospace"

# ── QSS stylesheet ──────────────────────────────────────────────────────────

STYLESHEET = f"""
/* ── Global ─────────────────────────────────────────────────────────────── */
QWidget {{
    font-family: {FONT_FAMILY};
    font-size: 13px;
    color: {TEXT_PRIMARY};
    background: transparent;
}}

QMainWindow, #centralWidget {{
    background: {BG_PRIMARY};
}}

/* ── Scroll area ────────────────────────────────────────────────────────── */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 4px 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* ── Cards (QFrame with property class=card) ────────────────────────────── */
QFrame[class="card"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}

/* ── Section labels ─────────────────────────────────────────────────────── */
QLabel[class="section-title"] {{
    font-size: 11px;
    font-weight: 700;
    color: {TEXT_SECONDARY};
    letter-spacing: 0.5px;
    padding: 0;
    margin: 0;
}}

/* ── Inputs ─────────────────────────────────────────────────────────────── */
QLineEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    min-height: 18px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}
QLineEdit:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled {{
    background: {BG_PRIMARY};
    color: {TEXT_SECONDARY};
}}

/* ── Combo box ──────────────────────────────────────────────────────────── */
QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    min-height: 18px;
}}
QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 4px;
    selection-background-color: {ACCENT};
    selection-color: white;
    padding: 4px;
}}

/* ── Check box ──────────────────────────────────────────────────────────── */
QCheckBox {{
    spacing: 8px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1.5px solid {BORDER};
    background: {SURFACE};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

/* ── Primary button ─────────────────────────────────────────────────────── */
QPushButton[class="primary"] {{
    background: {ACCENT};
    color: {ACCENT_TEXT};
    border: none;
    border-radius: 10px;
    padding: 12px 24px;
    font-size: 14px;
    font-weight: 600;
    min-height: 22px;
}}
QPushButton[class="primary"]:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton[class="primary"]:pressed {{
    background: {ACCENT_PRESSED};
}}
QPushButton[class="primary"]:disabled {{
    background: {BORDER};
    color: {TEXT_SECONDARY};
}}

/* ── Danger button ──────────────────────────────────────────────────────── */
QPushButton[class="danger"] {{
    background: {DANGER};
    color: white;
    border: none;
    border-radius: 10px;
    padding: 12px 24px;
    font-size: 14px;
    font-weight: 600;
    min-height: 22px;
}}
QPushButton[class="danger"]:hover {{
    background: #E0342D;
}}
QPushButton[class="danger"]:pressed {{
    background: #C02D27;
}}
QPushButton[class="danger"]:disabled {{
    background: {BORDER};
    color: {TEXT_SECONDARY};
}}

/* ── Secondary button (outlined) ────────────────────────────────────────── */
QPushButton[class="secondary"] {{
    background: transparent;
    color: {ACCENT};
    border: 1.5px solid {ACCENT};
    border-radius: 10px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 500;
    min-height: 18px;
}}
QPushButton[class="secondary"]:hover {{
    background: rgba(0, 122, 255, 0.06);
}}
QPushButton[class="secondary"]:pressed {{
    background: rgba(0, 122, 255, 0.12);
}}
QPushButton[class="secondary"]:disabled {{
    border-color: {BORDER};
    color: {TEXT_SECONDARY};
}}

/* ── Tertiary button (text-only) ────────────────────────────────────────── */
QPushButton[class="tertiary"] {{
    background: transparent;
    color: {ACCENT};
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    min-height: 16px;
}}
QPushButton[class="tertiary"]:hover {{
    background: rgba(0, 122, 255, 0.06);
}}
QPushButton[class="tertiary"]:disabled {{
    color: {TEXT_SECONDARY};
}}

/* ── Small icon button (eye toggle, etc.) ───────────────────────────────── */
QPushButton[class="icon-btn"] {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px 6px;
    font-size: 14px;
    color: {TEXT_SECONDARY};
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
}}
QPushButton[class="icon-btn"]:hover {{
    background: rgba(0, 0, 0, 0.05);
}}

/* ── Status pills ───────────────────────────────────────────────────────── */
QLabel[class="pill-success"] {{
    background: {SUCCESS};
    color: white;
    border-radius: 10px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[class="pill-idle"] {{
    background: {BORDER};
    color: {TEXT_SECONDARY};
    border-radius: 10px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 500;
}}
QLabel[class="pill-danger"] {{
    background: {DANGER};
    color: white;
    border-radius: 10px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[class="pill-recording"] {{
    background: {ACCENT};
    color: white;
    border-radius: 10px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[class="pill-analyzing"] {{
    background: {WARNING};
    color: white;
    border-radius: 10px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[class="pill-done"] {{
    background: {SUCCESS};
    color: white;
    border-radius: 10px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[class="pill-error"] {{
    background: {DANGER};
    color: white;
    border-radius: 10px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}

/* ── Log panel ──────────────────────────────────────────────────────────── */
QPlainTextEdit[class="log"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 12px;
    font-family: {FONT_MONO};
    font-size: 12px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT};
    selection-color: white;
}}

/* ── Tooltip ────────────────────────────────────────────────────────────── */
QToolTip {{
    background: {TEXT_PRIMARY};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}
"""
