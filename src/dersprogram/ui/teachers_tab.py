from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLineEdit,
    QLabel,
    QMessageBox,
    QHeaderView,
)
from PySide6.QtCore import Qt

from ..db import Database
from .. import scheduling
from .widgets import WeekNavigator, MiniScheduleGrid, SummaryTable


class TeachersTab(QWidget):
    def __init__(self, db: Database, on_change=None):
        super().__init__()
        self.db = db
        self.on_change = on_change
        self.selected_id: int | None = None

        layout = QVBoxLayout(self)

        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Ad:"))
        self.name_edit = QLineEdit()
        form_row.addWidget(self.name_edit)
        form_row.addWidget(QLabel("Branş/Alan:"))
        self.subject_area_edit = QLineEdit()
        form_row.addWidget(self.subject_area_edit)
        form_row.addWidget(QLabel("Not:"))
        self.note_edit = QLineEdit()
        form_row.addWidget(self.note_edit)
        layout.addLayout(form_row)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("Öğretmen Ekle")
        self.update_button = QPushButton("Güncelle")
        self.delete_button = QPushButton("Sil")
        self.clear_button = QPushButton("Temizle")
        for b in (self.add_button, self.update_button, self.delete_button, self.clear_button):
            button_row.addWidget(b)
        layout.addLayout(button_row)

        splitter = QSplitter(Qt.Vertical)

        self.table_widget = QTableWidget(0, 3)
        self.table_widget.setHorizontalHeaderLabels(["Ad", "Branş/Alan", "Not"])
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        splitter.addWidget(self.table_widget)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_label = QLabel("Bu haftaki program:")
        detail_layout.addWidget(self.detail_label)
        self.navigator = WeekNavigator(lambda: len(self.db.day_names))
        detail_layout.addWidget(self.navigator)
        self.mini_grid = MiniScheduleGrid()
        detail_layout.addWidget(self.mini_grid, 2)
        detail_layout.addWidget(QLabel("Haftalık özet:"))
        self.summary_table = SummaryTable()
        detail_layout.addWidget(self.summary_table, 1)
        splitter.addWidget(detail)
        splitter.setSizes([250, 400])

        layout.addWidget(splitter, 1)

        self.add_button.clicked.connect(self.handle_add)
        self.update_button.clicked.connect(self.handle_update)
        self.delete_button.clicked.connect(self.handle_delete)
        self.clear_button.clicked.connect(self.clear_form)
        self.table_widget.itemSelectionChanged.connect(self.handle_selection)
        self.navigator.week_changed.connect(lambda _w: self.refresh_detail())

        self.refresh()

    def refresh(self) -> None:
        rows = self.db.list_teachers()
        self.table_widget.setRowCount(len(rows))
        for r, row in enumerate(rows):
            item_name = QTableWidgetItem(row["name"])
            item_name.setData(Qt.UserRole, row["id"])
            self.table_widget.setItem(r, 0, item_name)
            self.table_widget.setItem(r, 1, QTableWidgetItem(row["subject_area"] or ""))
            self.table_widget.setItem(r, 2, QTableWidgetItem(row["note"] or ""))
        self.refresh_detail()

    def refresh_detail(self) -> None:
        if self.selected_id is None:
            self.mini_grid.render(self.db, {})
            self.summary_table.render({})
            return
        schedule, _pool = scheduling.get_week_view(self.db, self.navigator.week_start)
        filtered: dict[tuple[int, int], list] = {}
        for cell, blocks in schedule.items():
            matched = [b for b in blocks if b.teacher_id == self.selected_id]
            if matched:
                filtered[cell] = matched
        self.mini_grid.render(self.db, filtered)
        totals = scheduling.summarize_hours(self.db, self.navigator.week_start, teacher_id=self.selected_id)
        self.summary_table.render(totals)

    def handle_selection(self) -> None:
        items = self.table_widget.selectedItems()
        if not items:
            self.selected_id = None
            self.refresh_detail()
            return
        row = items[0].row()
        name_item = self.table_widget.item(row, 0)
        self.selected_id = name_item.data(Qt.UserRole)
        self.name_edit.setText(name_item.text())
        self.subject_area_edit.setText(self.table_widget.item(row, 1).text())
        self.note_edit.setText(self.table_widget.item(row, 2).text())
        self.refresh_detail()

    def clear_form(self) -> None:
        self.selected_id = None
        self.name_edit.clear()
        self.subject_area_edit.clear()
        self.note_edit.clear()
        self.table_widget.clearSelection()
        self.refresh_detail()

    def handle_add(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik bilgi", "Öğretmen adı boş olamaz.")
            return
        self.db.add_teacher(name, self.subject_area_edit.text().strip(), self.note_edit.text().strip())
        self.clear_form()
        self.refresh()
        if self.on_change:
            self.on_change()

    def handle_update(self) -> None:
        if self.selected_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce listeden bir kayıt seçin.")
            return
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik bilgi", "Öğretmen adı boş olamaz.")
            return
        self.db.update_teacher(
            self.selected_id, name, self.subject_area_edit.text().strip(), self.note_edit.text().strip()
        )
        self.clear_form()
        self.refresh()
        if self.on_change:
            self.on_change()

    def handle_delete(self) -> None:
        if self.selected_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce listeden bir kayıt seçin.")
            return
        confirm = QMessageBox.question(
            self, "Silme Onayı",
            "Bu öğretmeni silmek istediğinize emin misiniz?\nBu öğretmene ait ders blokları da silinir.",
        )
        if confirm != QMessageBox.Yes:
            return
        self.db.delete_teacher(self.selected_id)
        self.clear_form()
        self.refresh()
        if self.on_change:
            self.on_change()
