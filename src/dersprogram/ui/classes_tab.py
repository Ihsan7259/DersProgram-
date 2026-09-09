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
    QCheckBox,
    QLabel,
    QMessageBox,
    QHeaderView,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtCore import Qt

from ..db import Database
from .. import scheduling
from .widgets import WeekNavigator, AvailabilityGrid, SummaryTable, ScopeDialog, section_title as _section_title, divider as _divider
from . import theme


class ClassesTab(QWidget):
    def __init__(self, db: Database, on_change=None):
        super().__init__()
        self.db = db
        self.on_change = on_change
        self.selected_id: int | None = None
        self._pending_availability: dict[tuple[int, int], str | None] = {}
        self._all_rows: list = []
        self._checked_class_ids: set[int] = set()
        # None = "ana sıralama" (yukarı/aşağı oklarıyla elle belirlenen
        # kalıcı sıra); "name" = başlığa tıklanınca geçici alfabetik
        # görünüm - aynı başlığa tekrar tıklayınca ana sıraya döner.
        self._active_sort: str | None = None

        root_layout = QVBoxLayout(self)

        # İki sütunlu düzen: solda ekleme formu + haftalık program (büyük
        # alan), sağda sınıf listesi + ders hedefleri + küçük haftalık
        # özet - bkz. kullanıcının elle çizdiği referans mockup.
        main_splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(_section_title("Sınıf Ekle"))

        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Sınıf Adı:"))
        self.name_edit = QLineEdit()
        form_row.addWidget(self.name_edit)
        left_layout.addLayout(form_row)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("Sınıf Ekle")
        self.add_button.setObjectName("primaryButton")
        self.update_button = QPushButton("Güncelle")
        self.delete_button = QPushButton("Sil")
        self.delete_button.setObjectName("dangerButton")
        self.clear_button = QPushButton("Temizle")
        for b in (self.add_button, self.update_button, self.delete_button, self.clear_button):
            button_row.addWidget(b)
        left_layout.addLayout(button_row)

        left_layout.addWidget(_divider())

        left_layout.addWidget(QLabel("Bu haftaki program:"))
        self.navigator = WeekNavigator(lambda: len(self.db.day_names))
        left_layout.addWidget(self.navigator)

        availability_hint = QLabel(
            "Boş kutuya tıklayın: 1. tık müsait (yeşil), 2. tık müsait değil (kırmızı), 3. tık kaldırır. "
            "Gün/saat başlığına tıklarsanız o günün/saatin tamamı topluca değişir. "
            "Müsait değil işaretlenen saatlere Ana Program'da bu sınıf için ders atanamaz."
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
        list_header_row.addWidget(_section_title("Sınıf Listesi"))
        list_header_row.addStretch()
        right_layout.addLayout(list_header_row)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Sınıf ara...")
        self.search_edit.textChanged.connect(self._apply_search_filter)
        right_layout.addWidget(self.search_edit)

        sort_hint = QLabel(
            "Ad başlığına tıklayarak alfabetik sıralayabilirsiniz "
            "(tekrar tıklayınca elle belirlediğiniz ana sıraya döner)."
        )
        sort_hint.setWordWrap(True)
        right_layout.addWidget(sort_hint)

        bulk_row = QHBoxLayout()
        self.select_all_checkbox = QCheckBox("Tümünü Seç")
        self.select_all_checkbox.toggled.connect(self._handle_select_all_toggled)
        bulk_row.addWidget(self.select_all_checkbox)
        bulk_row.addStretch()
        self.bulk_delete_button = QPushButton("Seçilenleri Sil")
        self.bulk_delete_button.setObjectName("dangerButton")
        self.bulk_delete_button.setEnabled(False)
        self.bulk_delete_button.clicked.connect(self.handle_bulk_delete)
        bulk_row.addWidget(self.bulk_delete_button)
        right_layout.addLayout(bulk_row)

        self.table_widget = QTableWidget(0, 4)
        self.table_widget.setHorizontalHeaderLabels(["", "Ad", "", ""])
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table_widget.setColumnWidth(0, 26)
        self.table_widget.setColumnWidth(2, 30)
        self.table_widget.setColumnWidth(3, 30)
        header.setSortIndicatorShown(False)
        header.sectionClicked.connect(self._handle_header_clicked)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        right_layout.addWidget(self.table_widget, 1)

        right_layout.addWidget(_divider())

        # ---------- ders hedefleri (müfredat) ----------
        right_layout.addWidget(_section_title("Hedef Ders Saatleri"))

        curriculum_form = QHBoxLayout()
        curriculum_form.addWidget(QLabel("Ders:"))
        self.curriculum_subject_combo = QComboBox()
        self.curriculum_subject_combo.currentIndexChanged.connect(self._reload_curriculum_teachers)
        curriculum_form.addWidget(self.curriculum_subject_combo, 2)
        curriculum_form.addWidget(QLabel("Öğretmen:"))
        self.curriculum_teacher_combo = QComboBox()
        curriculum_form.addWidget(self.curriculum_teacher_combo, 2)
        curriculum_form.addWidget(QLabel("Derslik:"))
        self.curriculum_room_combo = QComboBox()
        curriculum_form.addWidget(self.curriculum_room_combo, 2)
        curriculum_form.addWidget(QLabel("Saat:"))
        self.curriculum_hours_spin = QSpinBox()
        self.curriculum_hours_spin.setRange(1, 40)
        self.curriculum_hours_spin.setValue(4)
        curriculum_form.addWidget(self.curriculum_hours_spin)
        self.curriculum_add_button = QPushButton("Ekle")
        self.curriculum_add_button.setObjectName("primaryButton")
        self.curriculum_add_button.clicked.connect(self.handle_add_curriculum)
        curriculum_form.addWidget(self.curriculum_add_button)
        self.curriculum_update_button = QPushButton("Güncelle")
        self.curriculum_update_button.setObjectName("outlineButton")
        self.curriculum_update_button.clicked.connect(self.handle_update_curriculum)
        curriculum_form.addWidget(self.curriculum_update_button)
        right_layout.addLayout(curriculum_form)

        self.curriculum_table = QTableWidget(0, 6)
        self.curriculum_table.setHorizontalHeaderLabels(
            ["Ders", "Öğretmen", "Derslik", "Hedef", "Programda", "Durum"]
        )
        curriculum_header = self.curriculum_table.horizontalHeader()
        curriculum_header.setSectionResizeMode(0, QHeaderView.Stretch)
        curriculum_header.setSectionResizeMode(1, QHeaderView.Stretch)
        curriculum_header.setSectionResizeMode(2, QHeaderView.Stretch)
        curriculum_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        curriculum_header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        curriculum_header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.curriculum_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.curriculum_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.curriculum_table.setMaximumHeight(150)
        right_layout.addWidget(self.curriculum_table)

        curriculum_buttons = QHBoxLayout()
        self.curriculum_restore_button = QPushButton("Eksikleri Geri Ekle")
        self.curriculum_restore_button.setObjectName("outlineButton")
        self.curriculum_restore_button.clicked.connect(self.handle_restore_curriculum)
        curriculum_buttons.addWidget(self.curriculum_restore_button)
        self.curriculum_delete_button = QPushButton("Seçili Hedefi Sil")
        self.curriculum_delete_button.setObjectName("dangerButton")
        self.curriculum_delete_button.clicked.connect(self.handle_delete_curriculum)
        curriculum_buttons.addWidget(self.curriculum_delete_button)
        right_layout.addLayout(curriculum_buttons)
        self.curriculum_status_label = QLabel()
        self.curriculum_status_label.setStyleSheet("font-weight:700;")
        self.curriculum_status_label.setWordWrap(True)
        right_layout.addWidget(self.curriculum_status_label)

        right_layout.addWidget(_divider())
        right_layout.addWidget(_section_title("Haftalık özet"))
        self.summary_table = SummaryTable()
        self.summary_table.setMaximumHeight(140)
        right_layout.addWidget(self.summary_table)

        main_splitter.addWidget(right)
        main_splitter.setSizes([650, 350])

        root_layout.addWidget(main_splitter, 1)

        self.add_button.clicked.connect(self.handle_add)
        self.update_button.clicked.connect(self.handle_update)
        self.delete_button.clicked.connect(self.handle_delete)
        self.clear_button.clicked.connect(self.clear_form)
        self.table_widget.itemSelectionChanged.connect(self.handle_selection)
        self.curriculum_table.itemSelectionChanged.connect(self._handle_curriculum_selection)
        self.navigator.week_changed.connect(lambda _w: self.refresh_detail())
        self.name_edit.returnPressed.connect(self._handle_return_pressed)

        self.refresh()

    def _handle_return_pressed(self) -> None:
        self.handle_update() if self.selected_id is not None else self.handle_add()

    def _select_row_by_id(self, row_id: int) -> None:
        for r in range(self.table_widget.rowCount()):
            item = self.table_widget.item(r, 1)
            if item is not None and item.data(Qt.UserRole) == row_id:
                self.table_widget.selectRow(r)
                self.table_widget.scrollToItem(item)
                break

    @staticmethod
    def _move_button(icon_name: str, enabled: bool, tooltip: str = "") -> QPushButton:
        btn = QPushButton()
        btn.setIcon(theme.icon(theme.NAV_ICONS[icon_name], theme.INK_MUTED_38, 11))
        btn.setFixedSize(24, 24)
        btn.setEnabled(enabled)
        if tooltip:
            btn.setToolTip(tooltip)
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
        self._reload_curriculum_rooms()

    def _reload_curriculum_rooms(self) -> None:
        previous = self.curriculum_room_combo.currentData()
        self.curriculum_room_combo.blockSignals(True)
        self.curriculum_room_combo.clear()
        self.curriculum_room_combo.addItem("—", None)
        for row in self.db.list_rows("rooms"):
            self.curriculum_room_combo.addItem(row["name"], row["id"])
        if previous is not None:
            idx = self.curriculum_room_combo.findData(previous)
            if idx >= 0:
                self.curriculum_room_combo.setCurrentIndex(idx)
        self.curriculum_room_combo.blockSignals(False)

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
                QTableWidgetItem(row["room_name"] or "-"),
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
        room_id = self.curriculum_room_combo.currentData()
        self.db.add_class_curriculum(self.selected_id, subject_id, teacher_id, hours, room_id=room_id)
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

    def _handle_curriculum_selection(self) -> None:
        """Tablodan bir ders hedefi seçilince formu o hedefin mevcut
        değerleriyle doldurur - 'Güncelle' düğmesi bu değerleri düzenleyip
        kaydetmek için kullanılır (bkz. handle_update_curriculum)."""
        curriculum_id = self._selected_curriculum_id()
        if curriculum_id is None or self.selected_id is None:
            return
        row = next((r for r in self.db.list_class_curriculum(self.selected_id) if r["id"] == curriculum_id), None)
        if row is None:
            return

        idx_subject = self.curriculum_subject_combo.findData(row["subject_id"])
        if idx_subject >= 0:
            self.curriculum_subject_combo.setCurrentIndex(idx_subject)  # _reload_curriculum_teachers'i tetikler

        idx_teacher = self.curriculum_teacher_combo.findData(row["teacher_id"])
        if idx_teacher < 0 and row["teacher_id"] is not None and row["teacher_name"]:
            # Seçili dersin branşında listelenmeyen bir öğretmen atanmış
            # olabilir (branş filtresi dışında) - yine de seçilebilmesi
            # için combo'ya ekleyelim, aksi halde güncellerken kaybolur.
            self.curriculum_teacher_combo.addItem(row["teacher_name"], row["teacher_id"])
            idx_teacher = self.curriculum_teacher_combo.count() - 1
        if idx_teacher >= 0:
            self.curriculum_teacher_combo.setCurrentIndex(idx_teacher)

        idx_room = self.curriculum_room_combo.findData(row["room_id"])
        self.curriculum_room_combo.setCurrentIndex(idx_room if idx_room >= 0 else 0)

        self.curriculum_hours_spin.setValue(row["weekly_hours"])

    def handle_update_curriculum(self) -> None:
        curriculum_id = self._selected_curriculum_id()
        if curriculum_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce tablodan güncellenecek ders hedefini seçin.")
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
        room_id = self.curriculum_room_combo.currentData()
        self.db.update_class_curriculum(curriculum_id, subject_id, teacher_id, hours, room_id=room_id)
        self.refresh_curriculum()
        QMessageBox.information(self, "Güncellendi", "Ders hedefi güncellendi.")
        if self.on_change:
            self.on_change()

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

    def _set_cell_widget(self, row: int, col: int, widget) -> None:
        """setCellWidget() eskisini yenisiyle değiştirdiğinde önceki
        widget'ı silmez - üst-alt ilişkisi kalır ama görünmez kalır ve
        zamanla birikir; eskisini elle koparıp siliyoruz."""
        old_widget = self.table_widget.cellWidget(row, col)
        if old_widget is not None:
            self.table_widget.removeCellWidget(row, col)
            old_widget.setParent(None)
            old_widget.deleteLater()
        self.table_widget.setCellWidget(row, col, widget)

    def _populate_table(self, rows: list) -> None:
        is_filtered = bool(self.search_edit.text().strip())
        is_sorted = self._active_sort is not None
        locked = is_filtered or is_sorted
        if is_filtered:
            tip = "Sıralamayı değiştirmek için önce aramayı temizleyin."
        elif is_sorted:
            tip = "Yeniden sıralamak için önce ana sıraya dönün (başlığa tekrar tıklayın)."
        else:
            tip = ""

        self.table_widget.setRowCount(len(rows))
        for r, row in enumerate(rows):
            check_container = QWidget()
            check_layout = QHBoxLayout(check_container)
            check_layout.setContentsMargins(0, 0, 0, 0)
            check_layout.setAlignment(Qt.AlignCenter)
            checkbox = QCheckBox()
            checkbox.setChecked(row["id"] in self._checked_class_ids)
            checkbox.toggled.connect(lambda checked, cid=row["id"]: self._handle_row_check_toggled(cid, checked))
            check_layout.addWidget(checkbox)
            self._set_cell_widget(r, 0, check_container)

            item_name = QTableWidgetItem(row["name"])
            item_name.setData(Qt.UserRole, row["id"])
            self.table_widget.setItem(r, 1, item_name)

            up_btn = self._move_button("up", enabled=not locked and r > 0, tooltip=tip)
            up_btn.clicked.connect(lambda _checked=False, cid=row["id"]: self.handle_move(cid, -1))
            self._set_cell_widget(r, 2, up_btn)

            down_btn = self._move_button("down", enabled=not locked and r < len(rows) - 1, tooltip=tip)
            down_btn.clicked.connect(lambda _checked=False, cid=row["id"]: self.handle_move(cid, 1))
            self._set_cell_widget(r, 3, down_btn)

        self._update_bulk_delete_state()

    def _apply_search_filter(self, text: str = "") -> None:
        query = self.search_edit.text().strip().lower()
        rows = self._all_rows if not query else [r for r in self._all_rows if query in r["name"].lower()]
        if self._active_sort == "name":
            rows = sorted(rows, key=lambda r: r["name"].lower())
        self._populate_table(rows)

    def refresh(self) -> None:
        self._reload_curriculum_subjects()
        self._all_rows = self.db.list_class_groups()
        self._apply_search_filter()
        self.refresh_detail()

    def handle_move(self, class_id: int, direction: int) -> None:
        self.db.move_class_group(class_id, direction)
        selected = self.selected_id
        self.refresh()
        if selected is not None:
            self._select_row_by_id(selected)

    def _handle_header_clicked(self, column: int) -> None:
        target = {1: "name"}.get(column)
        if target is None:
            return
        self._active_sort = None if self._active_sort == target else target
        header = self.table_widget.horizontalHeader()
        if self._active_sort is None:
            header.setSortIndicatorShown(False)
        else:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(column, Qt.AscendingOrder)
        selected = self.selected_id
        self._apply_search_filter()
        if selected is not None:
            self._select_row_by_id(selected)

    # ---------- toplu seçim / toplu silme ----------
    def _handle_row_check_toggled(self, class_id: int, checked: bool) -> None:
        if checked:
            self._checked_class_ids.add(class_id)
        else:
            self._checked_class_ids.discard(class_id)
        self._update_bulk_delete_state()

    def _update_bulk_delete_state(self) -> None:
        count = len(self._checked_class_ids)
        self.bulk_delete_button.setEnabled(count > 0)
        self.bulk_delete_button.setText(f"Seçilenleri Sil ({count})" if count else "Seçilenleri Sil")

    def _handle_select_all_toggled(self, checked: bool) -> None:
        for r in range(self.table_widget.rowCount()):
            container = self.table_widget.cellWidget(r, 0)
            if container is None:
                continue
            checkbox = container.findChild(QCheckBox)
            if checkbox is not None:
                checkbox.setChecked(checked)

    def handle_bulk_delete(self) -> None:
        ids = list(self._checked_class_ids)
        if not ids:
            return
        names = [r["name"] for r in self._all_rows if r["id"] in self._checked_class_ids]
        preview = "\n".join(f"- {n}" for n in names[:10])
        if len(names) > 10:
            preview += f"\n... ve {len(names) - 10} tane daha"
        confirm = QMessageBox.question(
            self, "Toplu Silme Onayı",
            f"{len(ids)} sınıf silinsin mi?\nBu sınıflara ait ders blokları da silinir.\n\n" + preview,
        )
        if confirm != QMessageBox.Yes:
            return
        for class_id in ids:
            self.db.delete_row("class_groups", class_id)
        self._checked_class_ids.clear()
        self.select_all_checkbox.setChecked(False)
        self.clear_form()
        self.refresh()
        if self.on_change:
            self.on_change()

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
        name_item = self.table_widget.item(row, 1)
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
