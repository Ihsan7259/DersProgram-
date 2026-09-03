from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QStackedWidget

from ..db import Database
from .list_tab import ListTab
from .schedule_tab import ScheduleTab
from .teachers_tab import TeachersTab
from .students_tab import StudentsTab
from .classes_tab import ClassesTab
from .analysis_tab import AnalysisTab
from .payments_tab import PaymentsTab
from .settings_tab import SettingsTab
from .sidebar import Sidebar
from . import theme


class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.setWindowTitle("Ders Programı")
        self.resize(1400, 880)
        self.setStyleSheet(theme.stylesheet())

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        self.sidebar = Sidebar()
        root.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("contentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 22, 26, 22)
        content_layout.setSpacing(14)

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
        root.addWidget(content, 1)

        self.schedule_tab = ScheduleTab(db)
        self.classes_tab = ClassesTab(db, on_change=self._on_reference_change)
        self.teachers_tab = TeachersTab(db, on_change=self._on_reference_change)
        self.students_tab = StudentsTab(db, on_change=self._on_reference_change)
        self.subjects_tab = ListTab(db, "subjects", "Ders/Branş", on_change=self._on_reference_change)
        self.rooms_tab = ListTab(db, "rooms", "Derslik", on_change=self._on_reference_change)
        self.analysis_tab = AnalysisTab(db)
        self.payments_tab = PaymentsTab(db)
        self.settings_tab = SettingsTab(db, on_change=self._on_settings_change)

        self.pages = {
            "ana-program": (self.schedule_tab, "Ana Program", "Haftalık ders programını buradan düzenleyin"),
            "siniflar": (self.classes_tab, "Sınıflar", "Sınıf/şube tanımları ve haftalık programları"),
            "ogretmenler": (self.teachers_tab, "Öğretmenler", "Öğretmen tanımları ve haftalık programları"),
            "ogrenciler": (self.students_tab, "Öğrenciler", "Öğrenci tanımları, koç ataması ve haftalık programları"),
            "dersler": (self.subjects_tab, "Dersler", "Ders/branş tanımları"),
            "derslikler": (self.rooms_tab, "Derslikler", "Derslik tanımları"),
            "analiz": (self.analysis_tab, "Analiz", "Tarih aralığına göre öğretmen/öğrenci saat toplamları"),
            "odemeler": (self.payments_tab, "Ödemeler", "Öğrenci ücretleri, ödemeler ve kalan borç"),
            "ayarlar": (self.settings_tab, "Ayarlar", "Gün ve ders saati sayısı ayarları"),
        }
        for widget, _title, _subtitle in self.pages.values():
            self.stack.addWidget(widget)

        self.sidebar.page_selected.connect(self.show_page)
        self.show_page("ana-program")

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
