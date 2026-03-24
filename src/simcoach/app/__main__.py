"""Entry point: python -m simcoach.app"""

import sys

_APP_ID = "simcoach.desktop.app"


def _set_windows_app_id() -> None:
    """Set AppUserModelID so Windows uses our icon for taskbar grouping.

    Without this, Windows may group the process under python.exe and show
    the Python icon instead of simcoach's icon on the taskbar.
    """
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_APP_ID)
    except (AttributeError, OSError):
        pass  # not Windows, or windll unavailable


def _resolve_icon_path():
    """Return the path to app.ico, handling both dev and PyInstaller layouts."""
    from pathlib import Path

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "simcoach" / "app"
    else:
        base = Path(__file__).parent
    return base / "style" / "icons" / "app.ico"


def main() -> None:
    _set_windows_app_id()

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("simcoach")
    app.setOrganizationName("simcoach")

    # Apply global stylesheet
    from simcoach.app.style.theme import STYLESHEET

    app.setStyleSheet(STYLESHEET)

    # Set window icon — applied to both app-level (Alt-Tab / taskbar)
    # and window-level (title bar) for consistent display across Windows configs.
    icon_path = _resolve_icon_path()
    app_icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    from simcoach.app.main_window import MainWindow

    window = MainWindow()
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
