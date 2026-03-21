"""Entry point: python -m simcoach.app"""

import sys


def main() -> None:
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
    from pathlib import Path

    icon_path = Path(__file__).parent / "style" / "icons" / "app.ico"
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
