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
    QLabel,
    QMessageBox,
    QHeaderView,
)
from PySide6.QtCore import Qt

from ..db import Database
from .. import scheduling
from .widgets import WeekNavigator, TeacherAvailabilityGrid, SummaryTable, ScopeDialog

NO_SUBJECT = "(Seçilmedi)"


class TeachersTab(QWidget):
    def __init__(self, db: Database, on_change=None):
        super().__init__()
        self.db = db
        self.on_change = on_change
        self.selected_id: int | None = None
        self._pending_availability: dict[tuple[int, int], str | None] = {}

        layout = QVBoxLayout(self)

        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Ad:"))
        self.name_edit = QLineEdit()
        form_row.addWidget(self.name_edit)
        form_row.addWidget(QLabel("Branş/Alan:"))
        self.subject_area_combo = QComboBox()
        form_row.addWidget(self.subject_area_combo)
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

        self.table_widget = QTableWidget(0, 2)
        self.table_widget.setHorizontalHeaderLabels(["Ad", "Branş/Alan"])
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

        availability_hint = QLabel(
            "Boş kutuya tıklayın: 1. tık müsait (yeşil), 2. tık müsait değil (kırmızı), 3. tık kaldırır. "
            "Gün/saat başlığına tıklarsanız o günün/saatin tamamı topluca değişir. "
            "Müsait değil işaretlenen saatlere Ana Program'da ders atanamaz."
        )
        availability_hint.setWordWrap(True)
        detail_layout.addWidget(availability_hint)

        bottom_row = QHBoxLayout()

        grid_col = QVBoxLayout()
        self.mini_grid = TeacherAvailabilityGrid()
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

    def _refresh_subject_choices(self, keep_text: str | None = None) -> None:
        self.subject_area_combo.blockSignals(True)
        self.subject_area_combo.clear()
        self.subject_area_combo.addItem(NO_SUBJECT, "")
        for row in self.db.list_rows("subjects"):
            self.subject_area_combo.addItem(row["name"], row["name"])
        if keep_text:
            idx = self.subject_area_combo.findData(keep_text)
            if idx < 0:
                # Dersler listesinde olmayan eski/serbest metin bir değer:
                # kaybolmasın diye listeye geçici olarak ekle.
                self.subject_area_combo.addItem(keep_text, keep_text)
                idx = self.subject_area_combo.count() - 1
            self.subject_area_combo.setCurrentIndex(idx)
        else:
            self.subject_area_combo.setCurrentIndex(0)
        self.subject_area_combo.blockSignals(False)

    def refresh(self) -> None:
        rows = self.db.list_teachers()
        self.table_widget.setRowCount(len(rows))
        for r, row in enumerate(rows):
            item_name = QTableWidgetItem(row["name"])
            item_name.setData(Qt.UserRole, row["id"])
            self.table_widget.setItem(r, 0, item_name)
            self.table_widget.setItem(r, 1, QTableWidgetItem(row["subject_area"] or ""))
        self._refresh_subject_choices(keep_text=self.subject_area_combo.currentData())
        self.refresh_detail()

    def refresh_detail(self) -> None:
        self._pending_availability = {}
        if self.selected_id is None:
            self.mini_grid.render(self.db, {}, {})
            self.summary_table.render({})
            return
        schedule, _pool = scheduling.get_week_view(self.db, self.navigator.week_start)
        filtered: dict[tuple[int, int], list] = {}
        for cell, blocks in schedule.items():
            matched = [b for b in blocks if b.teacher_id == self.selected_id]
            if matched:
                filtered[cell] = matched
        availability = scheduling.get_teacher_availability(self.db, self.selected_id, self.navigator.week_start)
        self.mini_grid.render(self.db, filtered, availability)
        totals = scheduling.summarize_hours(self.db, self.navigator.week_start, teacher_id=self.selected_id)
        self.summary_table.render(totals)

    def _handle_availability_changed(self, day: int, period: int, status) -> None:
        self._pending_availability[(day, period)] = status

    def handle_save_availability(self) -> None:
        if self.selected_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce listeden bir öğretmen seçin.")
            return
        if not self._pending_availability:
            QMessageBox.information(self, "Değişiklik yok", "Kaydedilecek bir müsaitlik değişikliği yok.")
            return
        dialog = ScopeDialog(self.db, self, "Müsaitlik değişikliklerini kaydetme")
        if dialog.exec() != ScopeDialog.Accepted:
            return
        scope = dialog.scope()
        for (day, period), status in self._pending_availability.items():
            scheduling.set_teacher_availability(self.db, self.navigator.week_start, self.selected_id, day, period, status, scope)
        self.refresh_detail()

    def handle_selection(self) -> None:
        items = self.table_widget.selectedItems()
        if not items:
            self.selected_id = None
            self._refresh_subject_choices()
            self.refresh_detail()
            return
        row = items[0].row()
        name_item = self.table_widget.item(row, 0)
        self.selected_id = name_item.data(Qt.UserRole)
        self.name_edit.setText(name_item.text())
        self._refresh_subject_choices(keep_text=self.table_widget.item(row, 1).text())
        self.refresh_detail()

    def clear_form(self) -> None:
        self.selected_id = None
        self.name_edit.clear()
        self._refresh_subject_choices()
        self.table_widget.clearSelection()
        self.refresh_detail()

    def handle_add(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik bilgi", "Öğretmen adı boş olamaz.")
            return
        new_id = self.db.add_teacher(name, self.subject_area_combo.currentData() or "")
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
            QMessageBox.warning(self, "Eksik bilgi", "Öğretmen adı boş olamaz.")
            return
        self.db.update_teacher(self.selected_id, name, self.subject_area_combo.currentData() or "")
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
