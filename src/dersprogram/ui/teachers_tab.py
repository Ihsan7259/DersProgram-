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
    QCheckBox,
    QScrollArea,
    QLabel,
    QMessageBox,
    QHeaderView,
)
from PySide6.QtCore import Qt

from ..db import Database
from .. import scheduling
from .widgets import WeekNavigator, AvailabilityGrid, SummaryTable, ScopeDialog, section_title as _section_title, divider as _divider
from . import theme


class TeachersTab(QWidget):
    def __init__(self, db: Database, on_change=None):
        super().__init__()
        self.db = db
        self.on_change = on_change
        self.selected_id: int | None = None
        self._pending_availability: dict[tuple[int, int], str | None] = {}

        root_layout = QVBoxLayout(self)

        # İki sütunlu düzen: solda ekleme formu + haftalık program (büyük
        # alan), sağda öğretmen listesi (kaydırılabilir) + küçük haftalık
        # özet - bkz. kullanıcının elle çizdiği referans mockup.
        main_splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(_section_title("Öğretmen Ekleme"))

        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Ad:"))
        self.name_edit = QLineEdit()
        form_row.addWidget(self.name_edit)
        left_layout.addLayout(form_row)

        # Bir öğretmen birden fazla branşa kayıtlı olabilir (ör. hem
        # Matematik hem Fizik) - checkbox listesiyle hepsi işaretlenebilir.
        subject_row = QHBoxLayout()
        subject_row.addWidget(QLabel("Branş/Alan:"))
        self.subject_checks: dict[int, QCheckBox] = {}
        self._subject_container = QWidget()
        self._subject_container_layout = QHBoxLayout(self._subject_container)
        self._subject_container_layout.setContentsMargins(4, 2, 4, 2)
        self._subject_container_layout.setSpacing(10)
        self._subject_scroll = QScrollArea()
        self._subject_scroll.setWidgetResizable(True)
        self._subject_scroll.setMaximumHeight(46)
        self._subject_scroll.setWidget(self._subject_container)
        subject_row.addWidget(self._subject_scroll, 1)
        left_layout.addLayout(subject_row)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("Öğretmen Ekle")
        self.update_button = QPushButton("Güncelle")
        self.delete_button = QPushButton("Sil")
        self.clear_button = QPushButton("Temizle")
        for b in (self.add_button, self.update_button, self.delete_button, self.clear_button):
            button_row.addWidget(b)
        left_layout.addLayout(button_row)

        left_layout.addWidget(_divider())

        self.detail_label = QLabel("Bu haftaki program:")
        left_layout.addWidget(self.detail_label)
        self.navigator = WeekNavigator(lambda: len(self.db.day_names))
        left_layout.addWidget(self.navigator)

        availability_hint = QLabel(
            "Boş kutuya tıklayın: 1. tık müsait (yeşil), 2. tık müsait değil (kırmızı), 3. tık kaldırır. "
            "Gün/saat başlığına tıklarsanız o günün/saatin tamamı topluca değişir. "
            "Müsait değil işaretlenen saatlere Ana Program'da ders atanamaz."
        )
        availability_hint.setWordWrap(True)
        left_layout.addWidget(availability_hint)

        self.mini_grid = AvailabilityGrid()
        self.mini_grid.changed.connect(self._handle_availability_changed)
        left_layout.addWidget(self.mini_grid, 1)
        self.save_availability_button = QPushButton("Müsaitliği Kaydet")
        self.save_availability_button.clicked.connect(self.handle_save_availability)
        left_layout.addWidget(self.save_availability_button)

        main_splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        list_header_row = QHBoxLayout()
        list_header_row.addWidget(_section_title("Öğretmen Listesi"))
        list_header_row.addStretch()
        list_header_row.addWidget(QLabel("İsim ya da Branşlar başlığına tıklayarak alfabetik sıralayabilirsiniz."))
        right_layout.addLayout(list_header_row)

        self.table_widget = QTableWidget(0, 4)
        self.table_widget.setHorizontalHeaderLabels(["İsim", "Branşlar", "", ""])
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table_widget.setColumnWidth(2, 30)
        self.table_widget.setColumnWidth(3, 30)
        header.sectionClicked.connect(self._handle_header_clicked)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        right_layout.addWidget(self.table_widget, 1)

        right_layout.addWidget(_divider())
        right_layout.addWidget(_section_title("Haftalık özet"))
        self.summary_table = SummaryTable()
        self.summary_table.setMaximumHeight(160)
        right_layout.addWidget(self.summary_table)

        main_splitter.addWidget(right)
        main_splitter.setSizes([650, 350])

        root_layout.addWidget(main_splitter, 1)

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

    def _refresh_subject_choices(self, checked_ids: set[int] | None = None) -> None:
        checked_ids = checked_ids or set()
        while self._subject_container_layout.count():
            item = self._subject_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.subject_checks = {}
        for row in self.db.list_rows("subjects"):
            cb = QCheckBox(row["name"])
            cb.setChecked(row["id"] in checked_ids)
            self.subject_checks[row["id"]] = cb
            self._subject_container_layout.addWidget(cb)
        self._subject_container_layout.addStretch()

    def _selected_subject_ids(self) -> list[int]:
        return [sid for sid, cb in self.subject_checks.items() if cb.isChecked()]

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

    def _set_cell_widget(self, row: int, col: int, widget) -> None:
        old_widget = self.table_widget.cellWidget(row, col)
        if old_widget is not None:
            self.table_widget.removeCellWidget(row, col)
            old_widget.setParent(None)
            old_widget.deleteLater()
        self.table_widget.setCellWidget(row, col, widget)

    def refresh(self) -> None:
        rows = self.db.list_teachers()
        self.table_widget.setRowCount(len(rows))
        for r, row in enumerate(rows):
            item_name = QTableWidgetItem(row["name"])
            item_name.setData(Qt.UserRole, row["id"])
            self.table_widget.setItem(r, 0, item_name)
            self.table_widget.setItem(r, 1, QTableWidgetItem(row["subject_area"] or ""))

            up_btn = self._move_button("up", enabled=r > 0)
            up_btn.clicked.connect(lambda _checked=False, tid=row["id"]: self.handle_move(tid, -1))
            self._set_cell_widget(r, 2, up_btn)

            down_btn = self._move_button("down", enabled=r < len(rows) - 1)
            down_btn.clicked.connect(lambda _checked=False, tid=row["id"]: self.handle_move(tid, 1))
            self._set_cell_widget(r, 3, down_btn)
        current = set(self._selected_subject_ids())
        self._refresh_subject_choices(checked_ids=current)
        self.refresh_detail()

    def handle_move(self, teacher_id: int, direction: int) -> None:
        self.db.move_teacher(teacher_id, direction)
        selected = self.selected_id
        self.refresh()
        if selected is not None:
            self._select_row_by_id(selected)

    def _handle_header_clicked(self, column: int) -> None:
        if column == 0:
            self.db.sort_teachers_by_name()
        elif column == 1:
            self.db.sort_teachers_by_subject()
        else:
            return
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
            matched = [b for b in blocks if b.teacher_id == self.selected_id]
            if matched:
                filtered[cell] = matched
        availability = scheduling.get_teacher_availability(self.db, self.selected_id, self.navigator.week_start)
        self.mini_grid.render(self.db, filtered, availability, row_mode="teacher")
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
        self._refresh_subject_choices(checked_ids=set(self.db.get_teacher_subject_ids(self.selected_id)))
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
        new_id = self.db.add_teacher(name, "")
        self.db.set_teacher_subjects(new_id, self._selected_subject_ids())
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
        self.db.update_teacher(self.selected_id, name, "")
        self.db.set_teacher_subjects(self.selected_id, self._selected_subject_ids())
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
