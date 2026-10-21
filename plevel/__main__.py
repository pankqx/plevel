import sys

from PySide6.QtWidgets import QApplication

from . import APP_NAME
from .main_window import MainWindow
from . import theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("plevel")
    theme.load_fonts()
    app.setStyleSheet(theme.stylesheet())
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
