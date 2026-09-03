"""Gün sayısı / ders saati sayısı, görünüm (tema) ve dönem tarihleri gibi
genel ayarlar."""
from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QPushButton,
    QMessageBox,
    QLabel,
    QFrame,
)

from ..db import Database

ALL_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    font.setPointSize(font.pointSize() + 1)
    label.setFont(font)
    return label


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


class SettingsTab(QWidget):
    def __init__(self, db: Database, on_change=None):
        super().__init__()
        self.db = db
        self.on_change = on_change

        layout = QVBoxLayout(self)

        # ---------- görünüm ----------
        layout.addWidget(_section_label("Görünüm"))
        appearance_form = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Açık", "light")
        self.theme_combo.addItem("Koyu", "dark")
        idx = self.theme_combo.findData(self.db.theme)
        self.theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        appearance_form.addRow("Tema:", self.theme_combo)
        layout.addLayout(appearance_form)

        layout.addWidget(_divider())

        # ---------- program günleri ----------
        layout.addWidget(_section_label("Program Günleri ve Saatleri"))
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

        layout.addWidget(_divider())

        # ---------- dönem tarihleri ----------
        layout.addWidget(_section_label("Dönem Tarihleri"))
        layout.addWidget(QLabel(
            "Bu tarihler bilgilendirme amaçlıdır; program yerleştirmelerinde "
            "'kalıcı' seçeneği bu dönem boyunca geçerli olur şeklinde gösterilir."
        ))
        term_form = QFormLayout()
        self.term_start_edit = QDateEdit()
        self.term_start_edit.setCalendarPopup(True)
        self.term_start_edit.setDisplayFormat("dd.MM.yyyy")
        self.term_start_edit.setDate(self._parse_date(self.db.term_start) or QDate.currentDate())
        term_form.addRow("Dönem Başlangıcı:", self.term_start_edit)

        self.term_end_edit = QDateEdit()
        self.term_end_edit.setCalendarPopup(True)
        self.term_end_edit.setDisplayFormat("dd.MM.yyyy")
        default_end = self._parse_date(self.db.term_end) or QDate.currentDate().addMonths(4)
        self.term_end_edit.setDate(default_end)
        term_form.addRow("Dönem Bitişi:", self.term_end_edit)
        layout.addLayout(term_form)

        save_button = QPushButton("Ayarları Kaydet")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self.save)
        layout.addWidget(save_button)
        layout.addStretch()

    @staticmethod
    def _parse_date(value: str | None) -> QDate | None:
        if not value:
            return None
        try:
            d = _dt.date.fromisoformat(value)
        except ValueError:
            return None
        return QDate(d.year, d.month, d.day)

    def save(self) -> None:
        selected_days = [day for day in ALL_DAYS if self.day_checks[day].isChecked()]
        if not selected_days:
            QMessageBox.warning(self, "Eksik bilgi", "En az bir gün seçmelisiniz.")
            return
        if self.term_start_edit.date() > self.term_end_edit.date():
            QMessageBox.warning(self, "Eksik bilgi", "Dönem başlangıcı, bitişinden sonra olamaz.")
            return

        self.db.set_setting("day_names", selected_days)
        self.db.set_setting("period_count", self.period_spin.value())
        self.db.set_setting("term_start", self.term_start_edit.date().toString("yyyy-MM-dd"))
        self.db.set_setting("term_end", self.term_end_edit.date().toString("yyyy-MM-dd"))

        new_theme = self.theme_combo.currentData()
        theme_changed = new_theme != self.db.get_setting("theme")
        self.db.set_setting("theme", new_theme)

        message = "Ayarlar kaydedildi."
        if theme_changed:
            message += "\n\nTema değişikliğinin uygulanması için programı kapatıp yeniden açın."
        QMessageBox.information(self, "Kaydedildi", message)
        if self.on_change:
            self.on_change()
