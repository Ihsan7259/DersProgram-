from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QLabel, QMessageBox

from .. import scheduling


class CopyWeekDialog(QDialog):
    # Ana Program > "Haftayı Kopyala": kaynak haftanın yerleşimlerini hedef
    # haftadan itibaren uygular.
    def __init__(
        self,
        source_week: _dt.date,
        target_week: _dt.date,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Haftalık Programı Kopyala")
        layout = QFormLayout(self)
        layout.addRow(QLabel(
            "Seçilen haftanın yerleşimleri hedef haftadan itibaren devam eder. Hedef haftadan önceki "
            "haftalar değişmez. Mevcut haftayı sonraki haftalara uygulamak için kaynak ve hedef olarak "
            "aynı haftayı seçin."
        ))
        self.source_edit = self._date_edit(source_week)
        self.target_edit = self._date_edit(target_week)
        layout.addRow("Kaynak hafta (Pazartesi):", self.source_edit)
        layout.addRow("Hedef hafta (Pazartesi):", self.target_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @staticmethod
    def _date_edit(value: _dt.date) -> QDateEdit:
        edit = QDateEdit(QDate(value.year, value.month, value.day))
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd.MM.yyyy")
        return edit

    def _accept_if_valid(self) -> None:
        source = self.source_week()
        target = self.target_week()
        if target < source:
            QMessageBox.warning(self, "Geçersiz Haftalar", "Hedef hafta kaynak haftadan önce olamaz.")
            return
        if target < scheduling.monday_of(_dt.date.today()):
            QMessageBox.warning(self, "Geçmiş Hafta", "Hedef hafta geçmişte olamaz.")
            return
        self.accept()

    def source_week(self) -> _dt.date:
        value = self.source_edit.date()
        return scheduling.monday_of(_dt.date(value.year(), value.month(), value.day()))

    def target_week(self) -> _dt.date:
        value = self.target_edit.date()
        return scheduling.monday_of(_dt.date(value.year(), value.month(), value.day()))
