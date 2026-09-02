"""Gün sayısı / ders saati sayısı gibi genel ayarlar."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QMessageBox,
    QLabel,
)

from ..db import Database

ALL_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


class SettingsTab(QWidget):
    def __init__(self, db: Database, on_change=None):
        super().__init__()
        self.db = db
        self.on_change = on_change

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Not: Ders saati sayısını sonradan azaltırsanız, silinen saatlerdeki "
            "atamalar programdan kalkar (veritabanından silinmez, sadece görünmez olabilir)."
        ))

        form = QFormLayout()
        self.day_checks: dict[str, QCheckBox] = {}
        current_days = set(self.db.day_names)
        for day in ALL_DAYS:
            cb = QCheckBox(day)
            cb.setChecked(day in current_days)
            self.day_checks[day] = cb
            form.addRow(cb)

        self.period_spin = QSpinBox()
        self.period_spin.setRange(1, 15)
        self.period_spin.setValue(self.db.period_count)
        form.addRow("Günlük ders saati sayısı:", self.period_spin)

        layout.addLayout(form)

        save_button = QPushButton("Ayarları Kaydet")
        save_button.clicked.connect(self.save)
        layout.addWidget(save_button)
        layout.addStretch()

    def save(self) -> None:
        selected_days = [day for day in ALL_DAYS if self.day_checks[day].isChecked()]
        if not selected_days:
            QMessageBox.warning(self, "Eksik bilgi", "En az bir gün seçmelisiniz.")
            return
        self.db.set_setting("day_names", selected_days)
        self.db.set_setting("period_count", self.period_spin.value())
        QMessageBox.information(self, "Kaydedildi", "Ayarlar kaydedildi.")
        if self.on_change:
            self.on_change()
