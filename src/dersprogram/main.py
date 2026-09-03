from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .db import Database
from . import seed
from .ui import theme
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Ders Programı")
    theme.load_fonts()
    app.setFont(QFont(theme.FONT_BODY))

    db = Database()
    if seed.is_empty(db):
        seed.seed_demo_data(db)

    # Fusion stili + kendi paletimiz: Windows'un açık/koyu sistem temasından
    # bağımsız, her zaman tutarlı ve okunaklı bir görünüm sağlar (aksi halde
    # onay kutusu/menü gibi bazı bileşenler sistem temasını miras alıp
    # metinlerin okunmaz hale gelmesine yol açabiliyordu).
    mode = db.theme
    theme.apply_theme(mode)
    app.setStyle("Fusion")
    app.setPalette(theme.build_palette(mode))

    window = MainWindow(db)
    window.show()

    exit_code = app.exec()
    db.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
