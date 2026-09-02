from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget

from ..db import Database
from .list_tab import ListTab
from .schedule_tab import ScheduleTab
from .settings_tab import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.setWindowTitle("Ders Programı")
        self.resize(1100, 700)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.schedule_tab = ScheduleTab(db)

        self.teachers_tab = ListTab(db, "teachers", "Öğretmen", on_change=self._on_reference_change)
        self.subjects_tab = ListTab(db, "subjects", "Ders", on_change=self._on_reference_change)
        self.classes_tab = ListTab(db, "class_groups", "Sınıf", on_change=self._on_class_change)
        self.rooms_tab = ListTab(db, "rooms", "Derslik", on_change=self._on_reference_change)
        self.settings_tab = SettingsTab(db, on_change=self.schedule_tab.refresh_grid)

        self.tabs.addTab(self.schedule_tab, "Program")
        self.tabs.addTab(self.classes_tab, "Sınıflar")
        self.tabs.addTab(self.teachers_tab, "Öğretmenler")
        self.tabs.addTab(self.subjects_tab, "Dersler")
        self.tabs.addTab(self.rooms_tab, "Derslikler")
        self.tabs.addTab(self.settings_tab, "Ayarlar")

    def _on_reference_change(self) -> None:
        # Öğretmen/ders/derslik listesi değiştiğinde program ızgarasındaki
        # açılır listeler bir sonraki hücre düzenlemesinde otomatik tazelenir;
        # burada sadece görünümü (etiketleri) tazeliyoruz.
        self.schedule_tab.refresh_grid()

    def _on_class_change(self) -> None:
        self.schedule_tab.reload_classes()
