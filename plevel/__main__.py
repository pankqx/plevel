import sys

from PySide6.QtWidgets import QApplication

from . import APP_NAME
from .main_window import MainWindow
from .theme import STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("plevel")
    app.setStyleSheet(STYLESHEET)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
