from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget

from ..db import Database
from .list_tab import ListTab
from .schedule_tab import ScheduleTab
from .teachers_tab import TeachersTab
from .students_tab import StudentsTab
from .classes_tab import ClassesTab
from .analysis_tab import AnalysisTab
from .payments_tab import PaymentsTab
from .settings_tab import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.setWindowTitle("Ders Programı")
        self.resize(1300, 800)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.schedule_tab = ScheduleTab(db)
        self.classes_tab = ClassesTab(db, on_change=self._on_reference_change)
        self.teachers_tab = TeachersTab(db, on_change=self._on_reference_change)
        self.students_tab = StudentsTab(db, on_change=self._on_reference_change)
        self.subjects_tab = ListTab(db, "subjects", "Ders/Branş", on_change=self._on_reference_change)
        self.rooms_tab = ListTab(db, "rooms", "Derslik", on_change=self._on_reference_change)
        self.analysis_tab = AnalysisTab(db)
        self.payments_tab = PaymentsTab(db)
        self.settings_tab = SettingsTab(db, on_change=self._on_settings_change)

        self.tabs.addTab(self.schedule_tab, "Ana Program")
        self.tabs.addTab(self.classes_tab, "Sınıflar")
        self.tabs.addTab(self.teachers_tab, "Öğretmenler")
        self.tabs.addTab(self.students_tab, "Öğrenciler")
        self.tabs.addTab(self.subjects_tab, "Dersler")
        self.tabs.addTab(self.rooms_tab, "Derslikler")
        self.tabs.addTab(self.analysis_tab, "Analiz")
        self.tabs.addTab(self.payments_tab, "Ödemeler")
        self.tabs.addTab(self.settings_tab, "Ayarlar")

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_reference_change(self) -> None:
        # Öğretmen/öğrenci/sınıf/ders/derslik listesi değiştiğinde, bu
        # kayıtlara bağlı diğer ekranların da tazelenmesi gerekir.
        self.schedule_tab.refresh()
        self.teachers_tab.refresh()
        self.students_tab.refresh()
        self.classes_tab.refresh()
        self.payments_tab.refresh_students()

    def _on_settings_change(self) -> None:
        self.schedule_tab.refresh()
        self.teachers_tab.refresh_detail()
        self.students_tab.refresh_detail()
        self.classes_tab.refresh_detail()

    def _on_tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is self.schedule_tab:
            self.schedule_tab.refresh()
        elif widget is self.analysis_tab:
            self.analysis_tab.refresh()
        elif widget is self.payments_tab:
            self.payments_tab.refresh_students()
        elif widget in (self.teachers_tab, self.students_tab, self.classes_tab):
            widget.refresh()
