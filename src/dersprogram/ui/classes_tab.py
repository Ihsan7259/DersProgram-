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
from .widgets import WeekNavigator, AvailabilityGrid, SummaryTable, ScopeDialog
from . import theme


class ClassesTab(QWidget):
    def __init__(self, db: Database, on_change=None):
        super().__init__()
        self.db = db
        self.on_change = on_change
        self.selected_id: int | None = None
        self._pending_availability: dict[tuple[int, int], str | None] = {}

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

        self.table_widget = QTableWidget(0, 3)
        self.table_widget.setHorizontalHeaderLabels(["Ad", "", ""])
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table_widget.setColumnWidth(1, 30)
        self.table_widget.setColumnWidth(2, 30)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        splitter.addWidget(self.table_widget)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(QLabel("Bu haftaki program:"))
        self.navigator = WeekNavigator(lambda: len(self.db.day_names))
        detail_layout.addWidget(self.navigator)

        availability_hint = QLabel(
            "Boş kutuya tıklayın: 1. tık müsait (yeşil), 2. tık müsait değil (kırmızı), 3. tık kaldırır. "
            "Gün/saat başlığına tıklarsanız o günün/saatin tamamı topluca değişir. "
            "Müsait değil işaretlenen saatlere Ana Program'da bu sınıf için ders atanamaz."
        )
        availability_hint.setWordWrap(True)
        detail_layout.addWidget(availability_hint)

        bottom_row = QHBoxLayout()
        grid_col = QVBoxLayout()
        self.mini_grid = AvailabilityGrid()
        self.mini_grid.changed.connect(self._handle_availability_changed)
        grid_col.addWidget(self.mini_grid, 1)
        self.save_availability_button = QPushButton("Müsaitliği Kaydet")
        self.save_availability_button.clicked.connect(self.handle_save_availability)
        grid_col.addWidget(self.save_availability_button)
        bottom_row.addLayout(grid_col, 3)

        summary_col = QVBoxLayout()
        summary_col.addWidget(QLabel("Haftalık özet:"))
        self.summary_table = SummaryTable()
        summary_col.addWidget(self.summary_table, 1)
        bottom_row.addLayout(summary_col, 1)

        detail_layout.addLayout(bottom_row, 1)
        splitter.addWidget(detail)
        splitter.setSizes([220, 480])

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

    @staticmethod
    def _move_button(icon_name: str, enabled: bool) -> QPushButton:
        btn = QPushButton()
        btn.setIcon(theme.icon(theme.NAV_ICONS[icon_name], theme.INK_MUTED_38, 11))
        btn.setFixedSize(24, 24)
        btn.setEnabled(enabled)
        btn.setStyleSheet(
            f"QPushButton {{ border:1px solid {theme.BORDER_INPUT}; border-radius:6px; background:{theme.SURFACE}; }}"
            f"QPushButton:hover {{ background:{theme.APP_BG}; }}"
            f"QPushButton:disabled {{ border-color:transparent; background:transparent; }}"
        )
        return btn

    def refresh(self) -> None:
        rows = self.db.list_class_groups()
        self.table_widget.setRowCount(len(rows))
        for r, row in enumerate(rows):
            item_name = QTableWidgetItem(row["name"])
            item_name.setData(Qt.UserRole, row["id"])
            self.table_widget.setItem(r, 0, item_name)

            up_btn = self._move_button("up", enabled=r > 0)
            up_btn.clicked.connect(lambda _checked=False, cid=row["id"]: self.handle_move(cid, -1))
            self.table_widget.setCellWidget(r, 1, up_btn)

            down_btn = self._move_button("down", enabled=r < len(rows) - 1)
            down_btn.clicked.connect(lambda _checked=False, cid=row["id"]: self.handle_move(cid, 1))
            self.table_widget.setCellWidget(r, 2, down_btn)
        self.refresh_detail()

    def handle_move(self, class_id: int, direction: int) -> None:
        self.db.move_class_group(class_id, direction)
        selected = self.selected_id
        self.refresh()
        if selected is not None:
            self._select_row_by_id(selected)

    def refresh_detail(self) -> None:
        self._pending_availability = {}
        if self.selected_id is None:
            self.mini_grid.render(self.db, {}, {})
            self.summary_table.render({})
            return
        schedule, _pool = scheduling.get_week_view(self.db, self.navigator.week_start)
        filtered: dict[tuple[int, int], list] = {}
        for cell, blocks in schedule.items():
            matched = [b for b in blocks if b.class_group_id == self.selected_id]
            if matched:
                filtered[cell] = matched
        availability = scheduling.get_class_availability(self.db, self.selected_id, self.navigator.week_start)
        self.mini_grid.render(self.db, filtered, availability)
        totals = scheduling.summarize_hours(self.db, self.navigator.week_start, class_group_id=self.selected_id)
        self.summary_table.render(totals)

    def _handle_availability_changed(self, day: int, period: int, status) -> None:
        self._pending_availability[(day, period)] = status

    def handle_save_availability(self) -> None:
        if self.selected_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce listeden bir sınıf seçin.")
            return
        if not self._pending_availability:
            QMessageBox.information(self, "Değişiklik yok", "Kaydedilecek bir müsaitlik değişikliği yok.")
            return
        dialog = ScopeDialog(self.db, self, "Müsaitlik değişikliklerini kaydetme")
        if dialog.exec() != ScopeDialog.Accepted:
            return
        scope = dialog.scope()
        for (day, period), status in self._pending_availability.items():
            scheduling.set_class_availability(self.db, self.navigator.week_start, self.selected_id, day, period, status, scope)
        self.refresh_detail()

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
        new_id = self.db.add_class_group(name)
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
