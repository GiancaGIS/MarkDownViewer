from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

try:
    from .config import APP_NAME, ORG_NAME
    from .main_window import MainWindow
except ImportError:
    from config import APP_NAME, ORG_NAME
    from main_window import MainWindow


def app_icon_path() -> Path:
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")) / "assets" / "app_icon.ico",
        Path(sys.executable).resolve().parent / "assets" / "app_icon.ico",
        Path(__file__).resolve().parents[1] / "assets" / "app_icon.ico",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[-1]


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()
    if len(sys.argv) > 1:
        initial_path = Path(sys.argv[1])
        if initial_path.exists() and initial_path.is_file():
            window.open_file_path(initial_path)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
