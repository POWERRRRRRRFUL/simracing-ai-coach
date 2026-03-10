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

    # Set window icon (if available)
    from pathlib import Path

    icon_path = Path(__file__).parent / "style" / "icons" / "app.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    from simcoach.app.main_window import MainWindow

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
