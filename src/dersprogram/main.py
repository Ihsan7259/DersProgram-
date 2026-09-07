from __future__ import annotations

import datetime
import sys
import traceback
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from .db import Database, default_db_path
from . import backup, institutions, seed
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
    app.setWindowIcon(theme.app_icon())
    theme.load_fonts()
    app.setFont(QFont(theme.FONT_BODY))

    active_institution = institutions.get_active_institution()
    db = Database(institutions.institution_db_path(active_institution))
    # Örnek veri, sadece hiç kurum ayrımı yokken kullanılan asıl (varsayılan)
    # kurum ilk kez boşken eklenir - sonradan eklenen yeni kurumlar bomboş
    # başlar, kullanıcıyı yanıltacak hazır veriyle karışmaz.
    is_default_institution = active_institution["file"] == default_db_path().name
    if is_default_institution and seed.is_empty(db):
        seed.seed_demo_data(db)

    # Sessiz otomatik yedek: açılışta (bu oturumda yapılacak değişikliklerden
    # ÖNCEKİ hali yakalamak için), sonra MainWindow periyodik olarak ve kurum
    # değiştirilirken/kapanırken de yedek alır (bkz. ui/main_window.py).
    backup.backup_now(db, active_institution["file"])

    # Fusion stili + kendi paletimiz: Windows'un açık/koyu sistem temasından
    # bağımsız, her zaman tutarlı ve okunaklı bir görünüm sağlar (aksi halde
    # onay kutusu/menü gibi bazı bileşenler sistem temasını miras alıp
    # metinlerin okunmaz hale gelmesine yol açabiliyordu).
    mode = db.theme
    theme.apply_theme(mode)
    app.setStyle("Fusion")
    app.setPalette(theme.build_palette(mode))

    window = MainWindow(db, institution_entry=active_institution)
    # Pencere her zaman ekrana tam sığacak şekilde (maksimize) açılır -
    # aksi halde küçük/dizüstü ekranlarda pencere ekrandan taşıp kullanıcının
    # elle büyütmesi/sürüklemesi gerekiyordu (bkz. MainWindow._apply_initial_size
    # - kullanıcı sonradan tam ekrandan çıkarsa o boyut geçerli olur).
    window.showMaximized()

    exit_code = app.exec()
    # window.db/current_institution (self, oturum sırasında kurum
    # değiştirilmiş olabileceğinden başlangıçtaki db/active_institution
    # yerine ANLIK olanı kullanıyoruz) kapanmadan önce son bir kez yedeklenir.
    backup.backup_now(window.db, window.current_institution["file"])
    window.db.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
