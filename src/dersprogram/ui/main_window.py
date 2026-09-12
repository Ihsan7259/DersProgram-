from __future__ import annotations

import shutil

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QStackedWidget, QMessageBox

from .. import backup, institutions
from ..db import Database
from .list_tab import ListTab
from .schedule_tab import ScheduleTab
from .subjects_tab import SubjectsTab
from .teachers_tab import TeachersTab
from .students_tab import StudentsTab
from .classes_tab import ClassesTab
from .analysis_tab import AnalysisTab
from .payments_tab import PaymentsTab
from .settings_tab import SettingsTab
from .sidebar import Sidebar
from .institution_dialog import InstitutionDialog
from . import theme


class MainWindow(QMainWindow):
    def __init__(self, db: Database, institution_entry: dict | None = None):
        super().__init__()
        self.setWindowTitle("Ders Programı")
        self._apply_initial_size()
        self.setStyleSheet(theme.stylesheet())

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        self.sidebar = Sidebar()
        root.addWidget(self.sidebar)
        self.sidebar.page_selected.connect(self.show_page)
        self.sidebar.switch_institution_requested.connect(self.handle_switch_institution)

        # Sekmelerin/programın kendisi ("içerik") kurum değiştirildiğinde
        # baştan kurulur; kenar çubuğu (Sidebar) ise kurumdan bağımsız
        # olduğu için hep aynı kalır, yeniden oluşturulmaz.
        self._content_host = QWidget()
        self._content_host_layout = QVBoxLayout(self._content_host)
        self._content_host_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._content_host, 1)

        self.current_institution = institution_entry or institutions.get_active_institution()
        self.sidebar.set_institution_name(self.current_institution["name"])
        self._build_content(db)

        # Sessiz otomatik yedek: program açık kaldığı sürece periyodik olarak
        # (kurum değiştirilse bile bu zamanlayıcı hep aynı kalır, her tikte
        # O AN aktif olan self.db/self.current_institution'ı yedekler).
        # Kapanırken/kurum değiştirilirken ayrıca yedek alınır (bkz. main.py,
        # handle_switch_institution).
        self._backup_timer = QTimer(self)
        self._backup_timer.timeout.connect(self._run_silent_backup)
        self._backup_timer.start(15 * 60 * 1000)

    def _apply_initial_size(self) -> None:
        """Sabit 1400x880 yerine ekranın kullanılabilir alanına göre boyut
        seçer - küçük/dizüstü ekranlarda pencere ekrandan taşıp kullanıcının
        elle büyütmesini/sürüklemesini gerektirmesin diye (bkz. main.py -
        pencere ayrıca doğrudan tam ekran/maksimize açılır, bu boyut sadece
        kullanıcı sonradan tam ekrandan çıkarsa geçerli olur)."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1400, 880)
            return
        available = screen.availableGeometry()
        # ÖNCE ekrana göre sınırla, SONRA 1400x880'i tavan olarak uygula -
        # tersi (küçük ekranlarda 900/600 gibi bir alt sınır dayatmak)
        # ekrandan daha büyük bir pencereye yol açabilir, ki asıl önlemeye
        # çalıştığımız sorun bu.
        width = min(1400, max(available.width() - 40, 1))
        height = min(880, max(available.height() - 40, 1))
        self.resize(width, height)

    def _run_silent_backup(self) -> None:
        backup.backup_now(self.db, self.current_institution["file"])

    def _build_content(self, db: Database) -> None:
        self.db = db

        content = QWidget()
        content.setObjectName("contentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 16, 22, 16)
        content_layout.setSpacing(10)

        header = QVBoxLayout()
        header.setSpacing(0)
        self.page_title = QLabel("Ana Program")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("Haftalık ders programını buradan düzenleyin")
        self.page_subtitle.setObjectName("pageSubtitle")
        header.addWidget(self.page_title)
        header.addWidget(self.page_subtitle)
        content_layout.addLayout(header)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)

        self.schedule_tab = ScheduleTab(db)
        self.classes_tab = ClassesTab(db, on_change=self._on_reference_change)
        self.teachers_tab = TeachersTab(db, on_change=self._on_reference_change)
        self.students_tab = StudentsTab(db, on_change=self._on_reference_change)
        self.subjects_tab = SubjectsTab(db, on_change=self._on_reference_change)
        self.rooms_tab = ListTab(db, "rooms", "Derslik", on_change=self._on_reference_change)
        self.analysis_tab = AnalysisTab(db)
        self.payments_tab = PaymentsTab(db)
        self.settings_tab = SettingsTab(db, on_change=self._on_settings_change, on_restore_requested=self.handle_restore_backup)

        self.pages = {
            "ana-program": (self.schedule_tab, "Ana Program", "Haftalık ders programını buradan düzenleyin"),
            "siniflar": (self.classes_tab, "Sınıflar", "Sınıf/şube tanımları ve haftalık programları"),
            "ogretmenler": (self.teachers_tab, "Öğretmenler", "Öğretmen tanımları ve haftalık programları"),
            "ogrenciler": (self.students_tab, "Öğrenciler", "Öğrenci tanımları, koç ataması ve haftalık programları"),
            "dersler": (self.subjects_tab, "Dersler", "Ders/branş tanımları, renkleri ve haftalık programları"),
            "derslikler": (self.rooms_tab, "Derslikler", "Derslik tanımları"),
            "analiz": (self.analysis_tab, "Analiz", "Tarih aralığına göre öğretmen/öğrenci saat toplamları"),
            "odemeler": (self.payments_tab, "Ödemeler", "Öğrenci ücretleri, ödemeler ve kalan borç"),
            "ayarlar": (self.settings_tab, "Ayarlar", "Gün ve ders saati sayısı ayarları"),
        }
        for widget, _title, _subtitle in self.pages.values():
            self.stack.addWidget(widget)

        # Ana Program, Öğretmenler, Öğrenciler ve Sınıflar sekmelerindeki
        # hafta gezinme çubukları birbirinden bağımsızdı; birinde "sonraki
        # hafta"ya geçip başka bir sekmede o haftaya özel bir değişiklik
        # yapmak, o sekme sessizce "bu hafta"da kalmaya devam ettiği için
        # kafa karıştırıyordu. Artık hepsi aynı haftayı gösterir.
        self._week_navigators = [
            self.schedule_tab.navigator,
            self.teachers_tab.navigator,
            self.students_tab.navigator,
            self.classes_tab.navigator,
            self.subjects_tab.navigator,
        ]
        for nav in self._week_navigators:
            nav.week_changed.connect(self._sync_week)

        self._content_host_layout.addWidget(content)
        self.show_page("ana-program")

    def handle_switch_institution(self) -> None:
        dialog = InstitutionDialog(self.current_institution["file"], self)
        if dialog.exec() != InstitutionDialog.Accepted or dialog.selected_entry is None:
            return
        entry = dialog.selected_entry
        if entry["file"] == self.current_institution["file"]:
            return

        confirm = QMessageBox.question(
            self,
            "Kurum Değiştir",
            f"'{entry['name']}' kurumuna geçilecek. Devam edilsin mi?",
        )
        if confirm != QMessageBox.Yes:
            return

        old_db = self.db
        # Ayrılınan kurumun son halini yedekle - kullanıcı hiçbir şey
        # görmeden, tam kurum değiştirmeden önceki bir güvenlik kopyası.
        backup.backup_now(old_db, self.current_institution["file"])
        new_db = Database(institutions.institution_db_path(entry))
        old_db.close()

        institutions.set_active_institution(entry)
        self.current_institution = entry
        self.sidebar.set_institution_name(entry["name"])
        self._replace_database(new_db)

    def handle_restore_backup(self, backup_path: str) -> None:
        """Ayarlar sekmesindeki 'Yedekten Geri Yükle' düğmesinden çağrılır -
        kullanıcı zaten dosyayı seçip onayladı (bkz. settings_tab.py); burada
        AKTİF kurumun veritabanı seçilen yedek dosyasıyla değiştirilir."""
        target_path = institutions.institution_db_path(self.current_institution)
        old_db = self.db
        # Geri yüklemeden hemen önce MEVCUT hali de yedekle - yanlış dosya
        # seçilirse bu son bir güvenlik ağı olur.
        backup.backup_now(old_db, self.current_institution["file"])
        old_db.close()
        shutil.copy2(backup_path, target_path)
        new_db = Database(target_path)
        self._replace_database(new_db)
        QMessageBox.information(self, "Tamamlandı", "Yedek başarıyla geri yüklendi.")

    def _replace_database(self, new_db: Database) -> None:
        """self.db'yi (ve ona bağlı tüm sekmeleri) yeni bir Database
        örneğiyle değiştirir - kurum değiştirmede (bkz. handle_switch_
        institution) ve yedekten geri yüklemede (bkz. handle_restore_backup)
        ortak kullanılır."""
        # Kurumun kendi tema tercihini uygula (aksi halde önceki verinin
        # açık/koyu tema seçimi yeni veride de görünmeye devam ederdi).
        theme.apply_theme(new_db.theme)
        # Renk seçimleri de kuruma özeldir (bkz. theme.load_color_overrides) -
        # yeni kurumun kendi ders tipi/ders renkleri yüklenmeli.
        theme.load_color_overrides(new_db)
        app = QApplication.instance()
        if app is not None:
            app.setPalette(theme.build_palette(new_db.theme))
        self.setStyleSheet(theme.stylesheet())

        old_content_item = self._content_host_layout.takeAt(0)
        if old_content_item is not None and old_content_item.widget() is not None:
            old_content_item.widget().deleteLater()

        self._build_content(new_db)

    def _sync_week(self, week_start) -> None:
        for nav in self._week_navigators:
            nav.set_week(week_start, emit=False)
        self.schedule_tab.refresh()
        self.teachers_tab.refresh_detail()
        self.students_tab.refresh_detail()
        self.classes_tab.refresh_detail()
        self.subjects_tab.refresh_detail()

    def show_page(self, page_id: str) -> None:
        widget, title, subtitle = self.pages[page_id]
        self.stack.setCurrentWidget(widget)
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)
        self.sidebar.set_active(page_id)

        if widget is self.schedule_tab:
            self.schedule_tab.refresh()
        elif widget is self.analysis_tab:
            self.analysis_tab.refresh()
        elif widget is self.payments_tab:
            self.payments_tab.refresh_students()
        elif widget in (self.teachers_tab, self.students_tab, self.classes_tab):
            widget.refresh()

    def _on_reference_change(self) -> None:
        # Öğretmen/öğrenci/sınıf/ders/derslik listesi değiştiğinde, bu
        # kayıtlara bağlı diğer ekranların da tazelenmesi gerekir.
        self.schedule_tab.refresh()
        self.teachers_tab.refresh()
        self.students_tab.refresh()
        self.classes_tab.refresh()
        self.subjects_tab.refresh()
        self.rooms_tab.refresh()
        self.payments_tab.refresh_students()

    def _on_settings_change(self) -> None:
        # Ayarlar sekmesi hem gün/saat değişikliklerinde hem de örnek veri
        # eklendiğinde bu geri çağırımı tetikler; ikinci durumda yeni
        # öğretmen/öğrenci/sınıf/ders/derslik kayıtları da olabileceğinden
        # kapsamlı tazeleme yapılır.
        self._on_reference_change()
