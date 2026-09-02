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
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QMessageBox,
    QHeaderView,
)
from PySide6.QtCore import Qt

from ..db import Database
from .. import scheduling
from .widgets import WeekNavigator, MiniScheduleGrid, SummaryTable


class StudentsTab(QWidget):
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
        form_row.addWidget(QLabel("Sınıf:"))
        self.class_combo = QComboBox()
        form_row.addWidget(self.class_combo)
        form_row.addWidget(QLabel("Koç:"))
        self.coach_combo = QComboBox()
        form_row.addWidget(self.coach_combo)
        layout.addLayout(form_row)

        fee_row = QHBoxLayout()
        fee_row.addWidget(QLabel("Program Ücreti:"))
        self.program_fee_spin = QDoubleSpinBox()
        self.program_fee_spin.setRange(0, 10_000_000)
        self.program_fee_spin.setSuffix(" TL")
        fee_row.addWidget(self.program_fee_spin)
        fee_row.addWidget(QLabel("Birebir Ücreti:"))
        self.one_on_one_fee_spin = QDoubleSpinBox()
        self.one_on_one_fee_spin.setRange(0, 10_000_000)
        self.one_on_one_fee_spin.setSuffix(" TL")
        fee_row.addWidget(self.one_on_one_fee_spin)
        layout.addLayout(fee_row)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("Öğrenci Ekle")
        self.update_button = QPushButton("Güncelle")
        self.delete_button = QPushButton("Sil")
        self.clear_button = QPushButton("Temizle")
        for b in (self.add_button, self.update_button, self.delete_button, self.clear_button):
            button_row.addWidget(b)
        layout.addLayout(button_row)

        splitter = QSplitter(Qt.Vertical)

        self.table_widget = QTableWidget(0, 3)
        self.table_widget.setHorizontalHeaderLabels(["Ad", "Sınıf", "Koç"])
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        splitter.addWidget(self.table_widget)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(QLabel("Bu haftaki program:"))
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

    def _reload_combos(self) -> None:
        self.class_combo.clear()
        self.class_combo.addItem("(Yok)", None)
        for c in self.db.list_rows("class_groups"):
            self.class_combo.addItem(c["name"], c["id"])

        self.coach_combo.clear()
        self.coach_combo.addItem("(Yok)", None)
        for t in self.db.list_teachers():
            self.coach_combo.addItem(t["name"], t["id"])

    def refresh(self) -> None:
        self._reload_combos()
        rows = self.db.list_students()
        self.table_widget.setRowCount(len(rows))
        for r, row in enumerate(rows):
            item_name = QTableWidgetItem(row["name"])
            item_name.setData(Qt.UserRole, row["id"])
            self.table_widget.setItem(r, 0, item_name)
            self.table_widget.setItem(r, 1, QTableWidgetItem(row["class_name"] or ""))
            self.table_widget.setItem(r, 2, QTableWidgetItem(row["coach_name"] or ""))
        self.refresh_detail()

    def refresh_detail(self) -> None:
        if self.selected_id is None:
            self.mini_grid.render(self.db, {})
            self.summary_table.render({})
            return
        schedule, _pool = scheduling.get_week_view(self.db, self.navigator.week_start)
        filtered: dict[tuple[int, int], list] = {}
        for cell, blocks in schedule.items():
            matched = [b for b in blocks if b.student_id == self.selected_id]
            if matched:
                filtered[cell] = matched
        self.mini_grid.render(self.db, filtered)
        totals = scheduling.summarize_hours(self.db, self.navigator.week_start, student_id=self.selected_id)
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
        student = self.db.get_student(self.selected_id)
        self.name_edit.setText(student["name"])
        self._select_combo(self.class_combo, student["class_group_id"])
        self._select_combo(self.coach_combo, student["coach_teacher_id"])
        self.program_fee_spin.setValue(student["total_program_fee"])
        self.one_on_one_fee_spin.setValue(student["total_one_on_one_fee"])
        self.refresh_detail()

    def _select_combo(self, combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def clear_form(self) -> None:
        self.selected_id = None
        self.name_edit.clear()
        self.class_combo.setCurrentIndex(0)
        self.coach_combo.setCurrentIndex(0)
        self.program_fee_spin.setValue(0)
        self.one_on_one_fee_spin.setValue(0)
        self.table_widget.clearSelection()
        self.refresh_detail()

    def handle_add(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik bilgi", "Öğrenci adı boş olamaz.")
            return
        self.db.add_student(
            name,
            self.class_combo.currentData(),
            self.coach_combo.currentData(),
            self.program_fee_spin.value(),
            self.one_on_one_fee_spin.value(),
        )
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
            QMessageBox.warning(self, "Eksik bilgi", "Öğrenci adı boş olamaz.")
            return
        self.db.update_student(
            self.selected_id,
            name,
            self.class_combo.currentData(),
            self.coach_combo.currentData(),
            self.program_fee_spin.value(),
            self.one_on_one_fee_spin.value(),
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
            "Bu öğrenciyi silmek istediğinize emin misiniz?\nBu öğrenciye ait ders blokları ve ödeme kayıtları da silinir.",
        )
        if confirm != QMessageBox.Yes:
            return
        self.db.delete_student(self.selected_id)
        self.clear_form()
        self.refresh()
        if self.on_change:
            self.on_change()
