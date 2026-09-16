"""Analiz: seçilen tarih aralığında öğretmen/öğrenci/derslik bazında ders
tipine göre toplam saatleri gösterir.

Her tablonun EN SON sütunu "Toplam Ders"tir (kullanıcı isteği: "analiz
kısmında da toplam ders seçeneği olsun") - o kişinin/dersliğin aralıktaki
tüm ders tiplerinin toplamı. Tablo bu sütuna göre (çoktan aza) sıralı
gelir, böylece en yoğun öğretmen/öğrenci/derslik en üstte görünür.
Derslikler sekmesi, kullanıcı isteği "hangi dersliğin ne kadar
kullanıldığını takip etmek istiyoruz" için eklendi."""
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

from ..db import Database, LESSON_TYPE_LABELS, TEACHERLESS_TYPES
from .. import scheduling

TOTAL_COLUMN_LABEL = "Toplam Ders"

# Öğretmen tablosunda gösterilmeyen ders tipleri. Deneme ve Etüt zaten
# öğretmensiz atanabilen tiplerdir (bkz. db.TEACHERLESS_TYPES); öğretmen
# analizinde bu iki sütun yer kaplamaktan başka bir şey yapmıyordu -
# kullanıcı isteği: "deneme ve etüt sekmesini de kaldıralım analiz
# partında hocalar için". Öğrenci ve derslik tablolarında duruyorlar.
TEACHER_HIDDEN_TYPES = set(TEACHERLESS_TYPES)


class AnalysisTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db

        layout = QVBoxLayout(self)

        date_row = QHBoxLayout()
        today = QDate.currentDate()
        date_row.addWidget(QLabel("Başlangıç (dahil):"))
        self.start_edit = QDateEdit(today.addDays(-27))
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setToolTip("Bu tarih hesaba DAHİL edilir.")
        date_row.addWidget(self.start_edit)
        date_row.addWidget(QLabel("Bitiş (dahil):"))
        self.end_edit = QDateEdit(today)
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setToolTip("Bu tarih hesaba DAHİL edilir.")
        date_row.addWidget(self.end_edit)
        self.refresh_button = QPushButton("Hesapla")
        self.refresh_button.setObjectName("primaryButton")
        date_row.addWidget(self.refresh_button)
        date_row.addStretch()
        layout.addLayout(date_row)

        self.tabs = QTabWidget()
        self.teacher_table = self._make_table(hidden_types=TEACHER_HIDDEN_TYPES)
        self.student_table = self._make_table()
        self.room_table = self._make_table()
        self.tabs.addTab(self.teacher_table, "Öğretmenler")
        self.tabs.addTab(self.student_table, "Öğrenciler")
        self.tabs.addTab(self.room_table, "Derslikler")
        layout.addWidget(self.tabs, 1)

        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

    def _make_table(self, hidden_types: set[str] | None = None) -> QTableWidget:
        table = QTableWidget()
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        types = [t for t in LESSON_TYPE_LABELS if t not in (hidden_types or set())]
        # Hangi tiplerin gösterildiği tabloyla birlikte taşınır - _fill_table
        # hem sütunları hem TOPLAM'ı bu listeye göre doldurur, böylece
        # "Toplam Ders" her zaman görünen sütunların toplamına eşit kalır.
        table.lesson_types = types
        columns = ["Ad"] + [LESSON_TYPE_LABELS[t] for t in types] + [TOTAL_COLUMN_LABEL]
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        # Sütun başlıkları ("Öğrenci Koçluk", "Soru Çözümü") varsayılan
        # genişlikte kırpılıyordu. ResizeToContents KULLANILMAZ - o mod
        # satır sayısı büyüdükçe (400 öğrenci) tüm hücreleri yeniden
        # ölçtüğü için ekranı yavaşlatıyor; başlık metni bir kez ölçülüp
        # sabit genişlik veriliyor.
        metrics = table.fontMetrics()
        for col, text in enumerate(columns):
            if col == 0:
                continue
            table.setColumnWidth(col, metrics.horizontalAdvance(text) + 26)
        table.setToolTip(
            "Son sütun (Toplam Ders), seçilen tarih aralığındaki tüm ders "
            "tiplerinin toplamıdır. Tablo bu sütuna göre sıralıdır."
        )
        return table

    def refresh(self) -> None:
        start = self.start_edit.date().toPython()
        end = self.end_edit.date().toPython()
        if start > end:
            start, end = end, start

        for table, entities, key in (
            (self.teacher_table, self.db.list_teachers(), "teacher_id"),
            (self.student_table, self.db.list_students(), "student_id"),
            (self.room_table, self.db.list_rows("rooms"), "room_id"),
        ):
            self._fill_table(table, entities, start, end, key)

    def _fill_table(self, table: QTableWidget, entities, start: _dt.date, end: _dt.date, key: str) -> None:
        types = table.lesson_types
        # Tüm satırların toplamı TEK geçişte hesaplanır (eskiden satır
        # başına bir kez aralığın tamamı yeniden kuruluyordu), sonra TOPLAM
        # DERS'e göre (çoktan aza) sıralanır - en yoğun olan en üstte.
        by_id = scheduling.summarize_hours_range_by(self.db, start, end, key)
        empty = {t: 0 for t in types}
        rows = []
        for entity in entities:
            totals = by_id.get(entity["id"], empty)
            rows.append((entity["name"], totals, sum(totals.get(t, 0) for t in types)))
        rows.sort(key=lambda row: (-row[2], row[0]))

        table.setRowCount(len(rows))
        total_col = len(types) + 1
        for r, (name, totals, grand_total) in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem(name))
            for c, t in enumerate(types, start=1):
                item = QTableWidgetItem(str(totals.get(t, 0)))
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(r, c, item)
            total_item = QTableWidgetItem(str(grand_total))
            total_item.setTextAlignment(Qt.AlignCenter)
            font = total_item.font()
            font.setBold(True)
            total_item.setFont(font)
            table.setItem(r, total_col, total_item)
