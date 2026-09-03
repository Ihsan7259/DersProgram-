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
    QSpinBox,
    QFrame,
    QLabel,
    QMessageBox,
    QHeaderView,
)
from PySide6.QtGui import QBrush, QColor
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

        # ---------- ders hedefleri (müfredat) ----------
        curriculum_title = QLabel("Ders Hedefleri (haftalık saat)")
        curriculum_title.setStyleSheet("font-weight:700;")
        detail_layout.addWidget(curriculum_title)

        curriculum_form = QHBoxLayout()
        curriculum_form.addWidget(QLabel("Ders:"))
        self.curriculum_subject_combo = QComboBox()
        self.curriculum_subject_combo.currentIndexChanged.connect(self._reload_curriculum_teachers)
        curriculum_form.addWidget(self.curriculum_subject_combo, 2)
        curriculum_form.addWidget(QLabel("Öğretmen:"))
        self.curriculum_teacher_combo = QComboBox()
        curriculum_form.addWidget(self.curriculum_teacher_combo, 2)
        curriculum_form.addWidget(QLabel("Haftalık saat:"))
        self.curriculum_hours_spin = QSpinBox()
        self.curriculum_hours_spin.setRange(1, 40)
        self.curriculum_hours_spin.setValue(4)
        curriculum_form.addWidget(self.curriculum_hours_spin)
        self.curriculum_add_button = QPushButton("Dersi Ekle")
        self.curriculum_add_button.setObjectName("primaryButton")
        self.curriculum_add_button.clicked.connect(self.handle_add_curriculum)
        curriculum_form.addWidget(self.curriculum_add_button)
        detail_layout.addLayout(curriculum_form)

        self.curriculum_table = QTableWidget(0, 5)
        self.curriculum_table.setHorizontalHeaderLabels(
            ["Ders", "Öğretmen", "Hedef", "Programda", "Durum"]
        )
        curriculum_header = self.curriculum_table.horizontalHeader()
        curriculum_header.setSectionResizeMode(0, QHeaderView.Stretch)
        curriculum_header.setSectionResizeMode(1, QHeaderView.Stretch)
        curriculum_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        curriculum_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        curriculum_header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.curriculum_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.curriculum_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.curriculum_table.setMaximumHeight(118)
        detail_layout.addWidget(self.curriculum_table)

        curriculum_buttons = QHBoxLayout()
        self.curriculum_restore_button = QPushButton("Eksik Dersleri Geri Ekle")
        self.curriculum_restore_button.clicked.connect(self.handle_restore_curriculum)
        curriculum_buttons.addWidget(self.curriculum_restore_button)
        self.curriculum_delete_button = QPushButton("Seçili Hedefi Sil")
        self.curriculum_delete_button.clicked.connect(self.handle_delete_curriculum)
        curriculum_buttons.addWidget(self.curriculum_delete_button)
        curriculum_buttons.addStretch()
        self.curriculum_status_label = QLabel()
        self.curriculum_status_label.setStyleSheet("font-weight:700;")
        curriculum_buttons.addWidget(self.curriculum_status_label)
        detail_layout.addLayout(curriculum_buttons)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        detail_layout.addWidget(divider)

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
        # Sınıf listesi kısa tutulur; ders hedefleri + haftalık program
        # aşağıda birlikte sığsın diye alan detay bölümüne bırakılır.
        self.table_widget.setMaximumHeight(150)
        splitter.setSizes([150, 720])

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

    # ---------- ders hedefleri ----------
    def _reload_curriculum_subjects(self) -> None:
        previous = self.curriculum_subject_combo.currentData()
        self.curriculum_subject_combo.blockSignals(True)
        self.curriculum_subject_combo.clear()
        for row in self.db.list_rows("subjects"):
            self.curriculum_subject_combo.addItem(row["name"], row["id"])
        if previous is not None:
            idx = self.curriculum_subject_combo.findData(previous)
            if idx >= 0:
                self.curriculum_subject_combo.setCurrentIndex(idx)
        self.curriculum_subject_combo.blockSignals(False)
        self._reload_curriculum_teachers()

    def _reload_curriculum_teachers(self) -> None:
        """Seçilen dersin branşına sahip öğretmenleri listeler; o branşta
        kimse yoksa (kimseye branş atanmamışsa) tüm öğretmenler gösterilir."""
        subject_name = self.curriculum_subject_combo.currentText()
        self.curriculum_teacher_combo.clear()
        teachers = self.db.list_teachers_by_subject_area(subject_name) if subject_name else []
        if not teachers:
            teachers = self.db.list_teachers()
        for teacher in teachers:
            self.curriculum_teacher_combo.addItem(teacher["name"], teacher["id"])

    def refresh_curriculum(self) -> None:
        self.curriculum_table.setRowCount(0)
        self.curriculum_status_label.setText("")
        if self.selected_id is None:
            return
        rows = self.db.list_class_curriculum(self.selected_id)
        self.curriculum_table.setRowCount(len(rows))
        total_target = 0
        total_planned = 0
        for r, row in enumerate(rows):
            target = row["weekly_hours"]
            planned = row["planned_hours"]
            placed = row["placed_hours"]
            total_target += target
            total_planned += planned
            if planned < target:
                status = f"⚠ {target - planned} saat eksik (havuzdan silinmiş)"
            elif placed < planned:
                status = f"{planned - placed} saat henüz yerleştirilmedi"
            else:
                status = "✓ tamam"

            item_subject = QTableWidgetItem(row["subject_name"] or "-")
            item_subject.setData(Qt.UserRole, row["id"])
            cells = [
                item_subject,
                QTableWidgetItem(row["teacher_name"] or "-"),
                QTableWidgetItem(str(target)),
                QTableWidgetItem(f"{planned} ({placed} yerleşti)"),
                QTableWidgetItem(status),
            ]
            for column, item in enumerate(cells):
                if planned < target:
                    item.setForeground(QBrush(QColor(theme.CONFLICT_BORDER)))
                self.curriculum_table.setItem(r, column, item)

        if total_target and total_planned < total_target:
            self.curriculum_status_label.setText(
                f"Toplam hedef {total_target} saat, programda {total_planned} saat "
                f"({total_target - total_planned} saat eksik)"
            )
            self.curriculum_status_label.setStyleSheet(f"font-weight:700; color:{theme.CONFLICT_BORDER};")
        elif total_target:
            self.curriculum_status_label.setText(f"Toplam hedef {total_target} saat - tamam")
            self.curriculum_status_label.setStyleSheet(f"font-weight:700; color:{theme.VALID_BORDER};")

    def handle_add_curriculum(self) -> None:
        if self.selected_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce listeden bir sınıf seçin.")
            return
        subject_id = self.curriculum_subject_combo.currentData()
        teacher_id = self.curriculum_teacher_combo.currentData()
        if subject_id is None:
            QMessageBox.warning(self, "Eksik bilgi", "Önce Dersler sekmesinden en az bir ders tanımlayın.")
            return
        if teacher_id is None:
            QMessageBox.warning(self, "Eksik bilgi", "Önce Öğretmenler sekmesinden en az bir öğretmen ekleyin.")
            return
        hours = self.curriculum_hours_spin.value()
        self.db.add_class_curriculum(self.selected_id, subject_id, teacher_id, hours)
        self.refresh_curriculum()
        QMessageBox.information(
            self, "Eklendi",
            f"{hours} saat ders 'Atanmamış Dersler' havuzuna eklendi. "
            "Ana Program'dan sürükleyerek ya da 'Oto Ata' ile yerleştirebilirsiniz.",
        )
        if self.on_change:
            self.on_change()

    def _selected_curriculum_id(self) -> int | None:
        items = self.curriculum_table.selectedItems()
        if not items:
            return None
        return self.curriculum_table.item(items[0].row(), 0).data(Qt.UserRole)

    def handle_delete_curriculum(self) -> None:
        curriculum_id = self._selected_curriculum_id()
        if curriculum_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce tablodan bir ders hedefi seçin.")
            return
        confirm = QMessageBox.question(
            self, "Silme Onayı",
            "Bu ders hedefi ve ona ait tüm ders saatleri (yerleştirilmiş olanlar dahil) silinecek. "
            "Devam edilsin mi?",
        )
        if confirm != QMessageBox.Yes:
            return
        self.db.delete_class_curriculum(curriculum_id)
        self.refresh_curriculum()
        self.refresh_detail()
        if self.on_change:
            self.on_change()

    def handle_restore_curriculum(self) -> None:
        if self.selected_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce listeden bir sınıf seçin.")
            return
        restored = 0
        for row in self.db.list_class_curriculum(self.selected_id):
            restored += self.db.restore_curriculum_blocks(row["id"])
        self.refresh_curriculum()
        if restored:
            QMessageBox.information(
                self, "Tamamlandı",
                f"{restored} saat ders yeniden oluşturuldu ve 'Atanmamış Dersler' havuzuna eklendi.",
            )
        else:
            QMessageBox.information(self, "Eksik yok", "Hedeflerin tamamı programda mevcut.")
        if self.on_change:
            self.on_change()

    def refresh(self) -> None:
        self._reload_curriculum_subjects()
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
        self.refresh_curriculum()
        if self.selected_id is None:
            self.mini_grid.render(self.db, {}, {}, row_mode="class")
            self.summary_table.render({})
            return
        schedule, _pool = scheduling.get_week_view(self.db, self.navigator.week_start)
        filtered: dict[tuple[int, int], list] = {}
        for cell, blocks in schedule.items():
            matched = [b for b in blocks if b.class_group_id == self.selected_id]
            if matched:
                filtered[cell] = matched
        availability = scheduling.get_class_availability(self.db, self.selected_id, self.navigator.week_start)
        self.mini_grid.render(self.db, filtered, availability, row_mode="class")
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
