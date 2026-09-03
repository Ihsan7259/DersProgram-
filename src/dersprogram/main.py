from __future__ import annotations

import datetime
import sys
import traceback
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from .db import Database
from . import seed
from .ui import theme
from .ui.main_window import MainWindow


def _install_crash_handler() -> None:
    """--windowed (konsolsuz) exe'de yakalanmayan bir hata normalde hiçbir iz
    bırakmadan sessizce yutulur (kullanıcı "hiçbir şey olmuyor" görür).
    Bunun yerine hatayı bir log dosyasına yazıp kullanıcıya görünür bir
    pencerede gösteriyoruz ki asıl sorun teşhis edilebilsin."""

    def handle_exception(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            log_dir = Path.home() / "DersProgrami"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "hata.log"
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.datetime.now().isoformat()} ---\n{text}\n")
        except Exception:
            log_path = None

        try:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setWindowTitle("Beklenmeyen Hata")
            note = f"\n\n(Ayrıntılar şuraya kaydedildi: {log_path})" if log_path else ""
            box.setText("Bir işlem sırasında beklenmeyen bir hata oluştu." + note)
            box.setDetailedText(text)
            box.exec()
        except Exception:
            pass

    sys.excepthook = handle_exception


def main() -> int:
    _install_crash_handler()
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
