from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..db import Database
from . import theme


class HolidaysDialog(QDialog):
    # Ana Program > "Resmî Tatil": tek tek tarihleri tatil olarak kapatır.
    def __init__(self, db: Database, initial_date: _dt.date, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Resmî Tatilleri Yönet")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        description = QLabel(
            "Eklediğiniz resmî tatil yalnızca seçilen tarihi kapatır; haftanın diğer günleri "
            "ve sonraki haftalar etkilenmez."
        )
        description.setWordWrap(True)
        description.setStyleSheet(f"color:{theme.INK_MUTED_52};")
        layout.addWidget(description)

        form = QFormLayout()
        self.date_edit = QDateEdit(QDate(initial_date.year, initial_date.month, initial_date.day))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Örn. Cumhuriyet Bayramı")
        form.addRow("Tarih:", self.date_edit)
        form.addRow("Tatil adı:", self.name_edit)
        layout.addLayout(form)

        self.holiday_list = QListWidget()
        layout.addWidget(self.holiday_list, 1)

        buttons = QHBoxLayout()
        self.add_button = QPushButton("Ekle")
        self.add_button.setObjectName("primaryButton")
        self.delete_button = QPushButton("Seçileni Kaldır")
        self.delete_button.setObjectName("dangerButton")
        close_button = QPushButton("Kapat")
        close_button.setObjectName("outlineButton")
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.add_button.clicked.connect(self._add_holiday)
        self.delete_button.clicked.connect(self._delete_holiday)
        close_button.clicked.connect(self.accept)
        self.holiday_list.itemSelectionChanged.connect(
            lambda: self.delete_button.setEnabled(self.holiday_list.currentItem() is not None)
        )
        self.delete_button.setEnabled(False)
        self._refresh_holidays()

    def _refresh_holidays(self) -> None:
        self.holiday_list.clear()
        for row in self.db.list_holidays():
            date = _dt.date.fromisoformat(row["holiday_date"])
            item = QListWidgetItem(f"{date.strftime('%d.%m.%Y')} — {row['name']}")
            item.setData(Qt.UserRole, row["holiday_date"])
            self.holiday_list.addItem(item)

    def _add_holiday(self) -> None:
        selected_date = self.date_edit.date().toString("yyyy-MM-dd")
        try:
            self.db.add_holiday(selected_date, self.name_edit.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Resmî Tatil Eklenemedi", str(exc))
            return
        self.name_edit.clear()
        self._refresh_holidays()

    def _delete_holiday(self) -> None:
        item = self.holiday_list.currentItem()
        if item is None:
            return
        holiday_date = item.data(Qt.UserRole)
        confirm = QMessageBox.question(self, "Resmî Tatili Kaldır", f"{item.text()} kaydı kaldırılsın mı?")
        if confirm != QMessageBox.Yes:
            return
        self.db.delete_holiday(holiday_date)
        self._refresh_holidays()
