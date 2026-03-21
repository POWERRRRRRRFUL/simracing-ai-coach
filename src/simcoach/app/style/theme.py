"""Dark theme derived from the HTML report — colour palette and QSS stylesheet.

Both the GUI and the HTML report share the same design language:
  bg       #0f1117   deep dark navy — page/window background
  surface  #1a1d27   card / panel surface (report --surface)
  surface2 #22263a   elevated / input surface (report --surface2)
  accent   #e63946   racing red — matches report accent exactly
  text     #e8eaf0   primary text (report --text)
  muted    #7a7f9a   labels / secondary text (report --muted)
  border   #2e3250   subtle borders (report --border)
  best     #4ade80   green — success / connected (report --best)
  ref      #60a5fa   blue — info / reference (report --ref)
"""

# ── Colour palette ─────────────────────────────────────────────────────────

BG_PRIMARY   = "#0f1117"
BG_SECONDARY = "#1a1d27"
SURFACE      = "#1a1d27"
SURFACE2     = "#22263a"
BORDER       = "#2e3250"
BORDER_FOCUS = "#e63946"

TEXT_PRIMARY     = "#e8eaf0"
TEXT_SECONDARY   = "#7a7f9a"
TEXT_PLACEHOLDER = "#4a4f68"

ACCENT         = "#e63946"
ACCENT_HOVER   = "#c82833"
ACCENT_PRESSED = "#a51f28"
ACCENT_TEXT    = "#ffffff"

SUCCESS    = "#4ade80"
SUCCESS_BG = "rgba(74, 222, 128, 0.12)"
WARNING    = "#f59e0b"
WARNING_BG = "rgba(245, 158, 11, 0.12)"
DANGER     = "#e63946"
DANGER_BG  = "rgba(230, 57, 70, 0.12)"
INFO       = "#60a5fa"
INFO_BG    = "rgba(96, 165, 250, 0.12)"

FONT_FAMILY = "'Segoe UI', system-ui, sans-serif"
FONT_MONO   = "'Cascadia Code', 'Consolas', monospace"

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
    border-radius: 8px;
}}

/* ── Section labels — uppercase with border-bottom like report ───────────── */
QLabel[class="section-title"] {{
    font-size: 11px;
    font-weight: 600;
    color: {TEXT_SECONDARY};
    letter-spacing: 1px;
    padding: 0 0 6px 0;
    border: none;
    border-bottom: 1px solid {BORDER};
}}

/* ── Inputs ─────────────────────────────────────────────────────────────── */
QLineEdit {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
    min-height: 18px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}
QLineEdit:focus {{
    border-color: {BORDER_FOCUS};
}}
QLineEdit:disabled {{
    background: {BG_PRIMARY};
    color: {TEXT_SECONDARY};
}}

/* ── Combo box ──────────────────────────────────────────────────────────── */
QComboBox {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
    min-height: 18px;
}}
QComboBox:focus {{
    border-color: {BORDER_FOCUS};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 4px;
    selection-background-color: {ACCENT};
    selection-color: white;
    padding: 4px;
    color: {TEXT_PRIMARY};
}}

/* ── Check box ──────────────────────────────────────────────────────────── */
QCheckBox {{
    spacing: 8px;
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1.5px solid {BORDER};
    background: {SURFACE2};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

/* ── Primary button — accent fill ───────────────────────────────────────── */
QPushButton[class="primary"] {{
    background: {ACCENT};
    color: {ACCENT_TEXT};
    border: none;
    border-radius: 6px;
    padding: 11px 24px;
    font-size: 13px;
    font-weight: 600;
    min-height: 20px;
    letter-spacing: 0.3px;
}}
QPushButton[class="primary"]:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton[class="primary"]:pressed {{
    background: {ACCENT_PRESSED};
}}
QPushButton[class="primary"]:disabled {{
    background: {SURFACE2};
    color: {TEXT_SECONDARY};
}}

/* ── Danger button — outlined, not solid — less aggressive on dark bg ────── */
QPushButton[class="danger"] {{
    background: transparent;
    color: {DANGER};
    border: 1.5px solid {DANGER};
    border-radius: 6px;
    padding: 10px 24px;
    font-size: 13px;
    font-weight: 600;
    min-height: 20px;
}}
QPushButton[class="danger"]:hover {{
    background: {DANGER_BG};
}}
QPushButton[class="danger"]:pressed {{
    background: rgba(230, 57, 70, 0.20);
}}
QPushButton[class="danger"]:disabled {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border-color: {BORDER};
}}

/* ── Secondary button — subtle outlined ─────────────────────────────────── */
QPushButton[class="secondary"] {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 9px 18px;
    font-size: 13px;
    font-weight: 500;
    min-height: 18px;
}}
QPushButton[class="secondary"]:hover {{
    background: {SURFACE2};
    color: {TEXT_PRIMARY};
    border-color: {TEXT_SECONDARY};
}}
QPushButton[class="secondary"]:pressed {{
    background: {SURFACE2};
    color: {TEXT_PRIMARY};
}}
QPushButton[class="secondary"]:disabled {{
    border-color: {BORDER};
    color: {TEXT_PLACEHOLDER};
}}

/* ── Tertiary button — ghost / low emphasis ─────────────────────────────── */
QPushButton[class="tertiary"] {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 500;
    min-height: 16px;
}}
QPushButton[class="tertiary"]:hover {{
    background: {SURFACE2};
    color: {TEXT_PRIMARY};
}}
QPushButton[class="tertiary"]:disabled {{
    color: {TEXT_PLACEHOLDER};
}}

/* ── Small icon button (eye toggle, etc.) ───────────────────────────────── */
QPushButton[class="icon-btn"] {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px 6px;
    font-size: 14px;
    color: {TEXT_SECONDARY};
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
}}
QPushButton[class="icon-btn"]:hover {{
    background: {SURFACE2};
}}

/* ── Status pills — subtle tinted backgrounds, coloured text ─────────────
   Matches the badge / indicator semantics of the HTML report:
   green = best/connected, red = error/not-running, amber = in-progress  */
QLabel[class="pill-success"] {{
    background: {SUCCESS_BG};
    color: {SUCCESS};
    border: 1px solid rgba(74, 222, 128, 0.25);
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QLabel[class="pill-idle"] {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.5px;
}}
QLabel[class="pill-danger"] {{
    background: {DANGER_BG};
    color: {DANGER};
    border: 1px solid rgba(230, 57, 70, 0.25);
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QLabel[class="pill-recording"] {{
    background: {DANGER_BG};
    color: {ACCENT};
    border: 1px solid rgba(230, 57, 70, 0.30);
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QLabel[class="pill-analyzing"] {{
    background: {WARNING_BG};
    color: {WARNING};
    border: 1px solid rgba(245, 158, 11, 0.25);
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QLabel[class="pill-done"] {{
    background: {SUCCESS_BG};
    color: {SUCCESS};
    border: 1px solid rgba(74, 222, 128, 0.25);
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QLabel[class="pill-error"] {{
    background: {DANGER_BG};
    color: {DANGER};
    border: 1px solid rgba(230, 57, 70, 0.25);
    border-radius: 4px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}

/* ── Log panel — darker than card surface, monospace activity feed ───────── */
QPlainTextEdit[class="log"] {{
    background: {BG_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 10px 14px;
    font-family: {FONT_MONO};
    font-size: 11px;
    color: {TEXT_SECONDARY};
    selection-background-color: {ACCENT};
    selection-color: white;
}}

/* ── Tooltip ────────────────────────────────────────────────────────────── */
QToolTip {{
    background: {SURFACE2};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ── Dialogs ─────────────────────────────────────────────────────────────── */
QDialog {{
    background: {BG_SECONDARY};
}}
QDialog QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}

/* ── List widget ─────────────────────────────────────────────────────────── */
QListWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    outline: none;
    padding: 4px;
}}
QListWidget::item {{
    padding: 8px 12px;
    color: {TEXT_PRIMARY};
    border-radius: 4px;
}}
QListWidget::item:selected {{
    background: {ACCENT};
    color: white;
}}
QListWidget::item:hover:!selected {{
    background: {SURFACE2};
}}

/* ── Message box ─────────────────────────────────────────────────────────── */
QMessageBox {{
    background: {BG_SECONDARY};
}}
QMessageBox QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
    font-size: 13px;
}}
QMessageBox QPushButton {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 500;
    min-width: 0;
}}
QMessageBox QPushButton:hover {{
    background: {SURFACE2};
    color: {TEXT_PRIMARY};
    border-color: {TEXT_SECONDARY};
}}
QMessageBox QPushButton:pressed {{
    background: {SURFACE2};
}}
QMessageBox QPushButton:default {{
    background: {ACCENT};
    color: white;
    border: none;
}}
QMessageBox QPushButton:default:hover {{
    background: {ACCENT_HOVER};
}}
QMessageBox QPushButton:default:pressed {{
    background: {ACCENT_PRESSED};
}}
"""
