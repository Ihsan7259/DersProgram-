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


class ClassesTab(QWidget):
    def __init__(self, db: Database, on_change=None):
        super().__init__()
        self.db = db
        self.on_change = on_change
        self.selected_id: int | None = None

        layout = QVBoxLayout(self)

        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Sınıf Adı:"))
        self.name_edit = QLineEdit()
        form_row.addWidget(self.name_edit)
        layout.addLayout(form_row)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("Sınıf Ekle")
        self.update_button = QPushButton("Güncelle")
        self.delete_button = QPushButton("Sil")
        self.clear_button = QPushButton("Temizle")
        for b in (self.add_button, self.update_button, self.delete_button, self.clear_button):
            button_row.addWidget(b)
        layout.addLayout(button_row)

        splitter = QSplitter(Qt.Vertical)

        self.table_widget = QTableWidget(0, 1)
        self.table_widget.setHorizontalHeaderLabels(["Ad"])
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
        self.name_edit.returnPressed.connect(self._handle_return_pressed)

        self.refresh()

    def _handle_return_pressed(self) -> None:
        self.handle_update() if self.selected_id is not None else self.handle_add()

    def _select_row_by_id(self, row_id: int) -> None:
        for r in range(self.table_widget.rowCount()):
            item = self.table_widget.item(r, 0)
            if item is not None and item.data(Qt.UserRole) == row_id:
                self.table_widget.selectRow(r)
                self.table_widget.scrollToItem(item)
                break

    def refresh(self) -> None:
        rows = self.db.list_rows("class_groups")
        self.table_widget.setRowCount(len(rows))
        for r, row in enumerate(rows):
            item_name = QTableWidgetItem(row["name"])
            item_name.setData(Qt.UserRole, row["id"])
            self.table_widget.setItem(r, 0, item_name)
        self.refresh_detail()

    def refresh_detail(self) -> None:
        if self.selected_id is None:
            self.mini_grid.render(self.db, {})
            self.summary_table.render({})
            return
        schedule, _pool = scheduling.get_week_view(self.db, self.navigator.week_start)
        filtered: dict[tuple[int, int], list] = {}
        for cell, blocks in schedule.items():
            matched = [b for b in blocks if b.class_group_id == self.selected_id]
            if matched:
                filtered[cell] = matched
        self.mini_grid.render(self.db, filtered)
        totals = scheduling.summarize_hours(self.db, self.navigator.week_start, class_group_id=self.selected_id)
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
        self.refresh_detail()

    def clear_form(self) -> None:
        self.selected_id = None
        self.name_edit.clear()
        self.table_widget.clearSelection()
        self.refresh_detail()

    def handle_add(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik bilgi", "Sınıf adı boş olamaz.")
            return
        new_id = self.db.add_row("class_groups", name)
        self.clear_form()
        self.refresh()
        self._select_row_by_id(new_id)
        if self.on_change:
            self.on_change()

    def handle_update(self) -> None:
        if self.selected_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce listeden bir kayıt seçin.")
            return
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik bilgi", "Sınıf adı boş olamaz.")
            return
        self.db.update_row("class_groups", self.selected_id, name)
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
            "Bu sınıfı silmek istediğinize emin misiniz?\nBu sınıfa ait ders blokları da silinir.",
        )
        if confirm != QMessageBox.Yes:
            return
        self.db.delete_row("class_groups", self.selected_id)
        self.clear_form()
        self.refresh()
        if self.on_change:
            self.on_change()
