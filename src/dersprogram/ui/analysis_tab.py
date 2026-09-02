"""Analiz: seçilen tarih aralığında öğretmen/öğrenci bazında ders
tipine göre toplam saatleri gösterir."""
from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QDateEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)

from ..db import Database, LESSON_TYPE_LABELS
from .. import scheduling


class AnalysisTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db

        layout = QVBoxLayout(self)

        date_row = QHBoxLayout()
        today = QDate.currentDate()
        date_row.addWidget(QLabel("Başlangıç:"))
        self.start_edit = QDateEdit(today.addDays(-27))
        self.start_edit.setCalendarPopup(True)
        date_row.addWidget(self.start_edit)
        date_row.addWidget(QLabel("Bitiş:"))
        self.end_edit = QDateEdit(today)
        self.end_edit.setCalendarPopup(True)
        date_row.addWidget(self.end_edit)
        self.refresh_button = QPushButton("Hesapla")
        date_row.addWidget(self.refresh_button)
        date_row.addStretch()
        layout.addLayout(date_row)

        self.tabs = QTabWidget()
        self.teacher_table = self._make_table()
        self.student_table = self._make_table()
        self.tabs.addTab(self.teacher_table, "Öğretmenler")
        self.tabs.addTab(self.student_table, "Öğrenciler")
        layout.addWidget(self.tabs, 1)

        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

    def _make_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        columns = ["Ad"] + list(LESSON_TYPE_LABELS.values())
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        return table

    def refresh(self) -> None:
        start = self.start_edit.date().toPython()
        end = self.end_edit.date().toPython()
        if start > end:
            start, end = end, start

        self._fill_table(self.teacher_table, self.db.list_teachers(), start, end, "teacher_id")
        self._fill_table(self.student_table, self.db.list_students(), start, end, "student_id")

    def _fill_table(self, table: QTableWidget, entities, start: _dt.date, end: _dt.date, key: str) -> None:
        types = list(LESSON_TYPE_LABELS.keys())
        table.setRowCount(len(entities))
        for r, entity in enumerate(entities):
            name_item = QTableWidgetItem(entity["name"])
            table.setItem(r, 0, name_item)
            kwargs = {key: entity["id"]}
            totals = scheduling.summarize_hours_range(self.db, start, end, **kwargs)
            for c, t in enumerate(types, start=1):
                item = QTableWidgetItem(str(totals.get(t, 0)))
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(r, c, item)
