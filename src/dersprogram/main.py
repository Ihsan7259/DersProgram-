from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .db import Database
from .ui import theme
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Ders Programı")
    theme.load_fonts()
    app.setFont(QFont(theme.FONT_BODY))

    db = Database()
    window = MainWindow(db)
    window.show()

    exit_code = app.exec()
    db.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
