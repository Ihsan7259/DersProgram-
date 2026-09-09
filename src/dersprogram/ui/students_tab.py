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
    QSpinBox,
    QCheckBox,
    QScrollArea,
    QLabel,
    QMessageBox,
    QHeaderView,
    QDialog,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtCore import Qt

from ..db import Database
from .. import scheduling
from .widgets import WeekNavigator, AvailabilityGrid, SummaryTable, ScopeDialog, section_title as _section_title, divider as _divider
from .import_students_dialog import ImportStudentsDialog
from . import theme


class StudentsTab(QWidget):
    def __init__(self, db: Database, on_change=None):
        super().__init__()
        self.db = db
        self.on_change = on_change
        self.selected_id: int | None = None
        self._pending_availability: dict[tuple[int, int], str | None] = {}
        self._all_rows: list = []
        self._checked_student_ids: set[int] = set()
        # None = "ana sıralama" (yukarı/aşağı oklarıyla elle belirlenen
        # kalıcı sıra); "name"/"class"/"title"/"coach" = başlığa
        # tıklanınca geçici alfabetik görünüm - aynı başlığa tekrar
        # tıklayınca ana sıraya döner (bkz. _handle_header_clicked).
        self._active_sort: str | None = None

        root_layout = QVBoxLayout(self)

        # İki sütunlu düzen: solda ekleme formu + haftalık program (büyük
        # alan), sağda arama kutulu öğrenci listesi + küçük haftalık özet
        # - bkz. kullanıcının elle çizdiği referans mockup.
        main_splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(_section_title("Öğrenci Ekleme"))

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
        left_layout.addLayout(form_row)

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
        left_layout.addLayout(fee_row)

        # Öğrenci hangi paketleri alıyor (sadece sınıf, sadece birebir,
        # sadece koçluk ya da birkaçı birden) - çoklu seçilebilir ünvan/
        # rozet listesi (Ayarlar'dan değil, öğretmen branşlarındaki gibi
        # checkbox listesiyle işaretlenir).
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Ünvan/Paket:"))
        self.title_checks: dict[int, QCheckBox] = {}
        self._title_container = QWidget()
        self._title_container_layout = QHBoxLayout(self._title_container)
        self._title_container_layout.setContentsMargins(4, 2, 4, 2)
        self._title_container_layout.setSpacing(10)
        self._title_scroll = QScrollArea()
        self._title_scroll.setWidgetResizable(True)
        self._title_scroll.setMaximumHeight(46)
        self._title_scroll.setWidget(self._title_container)
        title_row.addWidget(self._title_scroll, 1)
        left_layout.addLayout(title_row)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("Öğrenci Ekle")
        self.add_button.setObjectName("primaryButton")
        self.update_button = QPushButton("Güncelle")
        self.delete_button = QPushButton("Sil")
        self.delete_button.setObjectName("dangerButton")
        self.clear_button = QPushButton("Temizle")
        for b in (self.add_button, self.update_button, self.delete_button, self.clear_button):
            button_row.addWidget(b)
        left_layout.addLayout(button_row)

        left_layout.addWidget(_divider())

        left_layout.addWidget(QLabel("Bu haftaki program (kendi dersleri + sınıfının dersleri):"))
        self.navigator = WeekNavigator(lambda: len(self.db.day_names))
        left_layout.addWidget(self.navigator)

        availability_hint = QLabel(
            "Boş kutuya tıklayın: 1. tık müsait (yeşil), 2. tık müsait değil (kırmızı), 3. tık kaldırır. "
            "Gün/saat başlığına tıklarsanız o günün/saatin tamamı topluca değişir. "
            "Müsait değil işaretlenen saatlere Ana Program'da bu öğrenci için ders atanamaz."
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
        list_header_row.addWidget(_section_title("Öğrenci Listesi"))
        list_header_row.addStretch()
        self.import_excel_button = QPushButton("Excel'den İçe Aktar")
        self.import_excel_button.setObjectName("outlineButton")
        self.import_excel_button.clicked.connect(self.handle_import_excel)
        list_header_row.addWidget(self.import_excel_button)
        right_layout.addLayout(list_header_row)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Öğrenci ara...")
        self.search_edit.textChanged.connect(self._apply_search_filter)
        right_layout.addWidget(self.search_edit)

        sort_hint = QLabel(
            "Başlıklara (Ad/Sınıf/Ünvan/Koç) tıklayarak o alana göre sıralayabilirsiniz "
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

        self.table_widget = QTableWidget(0, 7)
        self.table_widget.setHorizontalHeaderLabels(["", "Ad", "Sınıf", "Ünvan", "Koç", "", ""])
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        for col in range(1, 5):
            header.setSectionResizeMode(col, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        self.table_widget.setColumnWidth(0, 26)
        self.table_widget.setColumnWidth(5, 30)
        self.table_widget.setColumnWidth(6, 30)
        header.setSortIndicatorShown(False)
        header.sectionClicked.connect(self._handle_header_clicked)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        right_layout.addWidget(self.table_widget, 1)

        right_layout.addWidget(_divider())

        # ---------- birebir ders hedefleri (Sınıflar sekmesindeki "Hedef
        # Ders Saatleri" ile aynı desen - kullanıcı isteği: "Birebir ders
        # saatlerinin de daha kolay takibi için sınıflar sekmesine
        # eklediğimiz hoca atama menüsünün aynısını öğrenciler sekmesine
        # birebir ders için ekleyelim") ----------
        right_layout.addWidget(_section_title("Hedef Birebir Ders Saatleri"))

        curriculum_form = QHBoxLayout()
        curriculum_form.addWidget(QLabel("Ders:"))
        self.curriculum_subject_combo = QComboBox()
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
        self.curriculum_hours_spin.setValue(1)
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

    def _reload_combos(self) -> None:
        self.class_combo.clear()
        self.class_combo.addItem("(Yok)", None)
        for c in self.db.list_class_groups():
            self.class_combo.addItem(c["name"], c["id"])

        self.coach_combo.clear()
        self.coach_combo.addItem("(Yok)", None)
        for t in self.db.list_teachers():
            self.coach_combo.addItem(t["name"], t["id"])

    def _refresh_title_choices(self, checked_ids: set[int] | None = None) -> None:
        checked_ids = checked_ids or set()
        while self._title_container_layout.count():
            item = self._title_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.title_checks = {}
        for row in self.db.list_rows("titles"):
            cb = QCheckBox(row["name"])
            cb.setChecked(row["id"] in checked_ids)
            self.title_checks[row["id"]] = cb
            self._title_container_layout.addWidget(cb)
        self._title_container_layout.addStretch()

    def _selected_title_ids(self) -> list[int]:
        return [tid for tid, cb in self.title_checks.items() if cb.isChecked()]

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

    def _set_cell_widget(self, row: int, col: int, widget) -> None:
        old_widget = self.table_widget.cellWidget(row, col)
        if old_widget is not None:
            self.table_widget.removeCellWidget(row, col)
            old_widget.setParent(None)
            old_widget.deleteLater()
        self.table_widget.setCellWidget(row, col, widget)

    # Ünvan hesaplanan bir özet olduğu için ayrı bir sorgu gerekiyor,
    # diğerleri doğrudan sütun - hepsi tek yerden erişilsin diye burada.
    def _sort_key_fns(self) -> dict[str, "callable"]:
        return {
            "name": lambda r: r["name"].lower(),
            "class": lambda r: (r["class_name"] or "").lower(),
            "title": lambda r: self.db.student_titles_summary(r["id"]).lower(),
            "coach": lambda r: (r["coach_name"] or "").lower(),
        }

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
            checkbox.setChecked(row["id"] in self._checked_student_ids)
            checkbox.toggled.connect(lambda checked, sid=row["id"]: self._handle_row_check_toggled(sid, checked))
            check_layout.addWidget(checkbox)
            self._set_cell_widget(r, 0, check_container)

            item_name = QTableWidgetItem(row["name"])
            item_name.setData(Qt.UserRole, row["id"])
            self.table_widget.setItem(r, 1, item_name)
            self.table_widget.setItem(r, 2, QTableWidgetItem(row["class_name"] or ""))
            titles_text = self.db.student_titles_summary(row["id"])
            titles_item = QTableWidgetItem(titles_text)
            titles_item.setToolTip(titles_text)
            self.table_widget.setItem(r, 3, titles_item)
            self.table_widget.setItem(r, 4, QTableWidgetItem(row["coach_name"] or ""))

            up_btn = self._move_button("up", enabled=not locked and r > 0, tooltip=tip)
            up_btn.clicked.connect(lambda _checked=False, sid=row["id"]: self.handle_move(sid, -1))
            self._set_cell_widget(r, 5, up_btn)

            down_btn = self._move_button("down", enabled=not locked and r < len(rows) - 1, tooltip=tip)
            down_btn.clicked.connect(lambda _checked=False, sid=row["id"]: self.handle_move(sid, 1))
            self._set_cell_widget(r, 6, down_btn)

        self._update_bulk_delete_state()

    def handle_move(self, student_id: int, direction: int) -> None:
        self.db.move_student(student_id, direction)
        selected = self.selected_id
        self.refresh()
        if selected is not None:
            self._select_row_by_id(selected)

    def _handle_header_clicked(self, column: int) -> None:
        target = {1: "name", 2: "class", 3: "title", 4: "coach"}.get(column)
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

    def _apply_search_filter(self, text: str = "") -> None:
        query = self.search_edit.text().strip().lower()
        rows = self._all_rows if not query else [r for r in self._all_rows if query in r["name"].lower()]
        if self._active_sort is not None:
            rows = sorted(rows, key=self._sort_key_fns()[self._active_sort])
        self._populate_table(rows)

    def refresh(self) -> None:
        self._reload_combos()
        self._reload_curriculum_subjects()
        current = set(self._selected_title_ids())
        self._refresh_title_choices(checked_ids=current)
        self._all_rows = self.db.list_students()
        self._apply_search_filter()
        self.refresh_detail()
        self.refresh_curriculum()

    def refresh_detail(self) -> None:
        self._pending_availability = {}
        if self.selected_id is None:
            self.mini_grid.render(self.db, {}, {})
            self.summary_table.render({})
            return
        student = self.db.get_student(self.selected_id)
        class_group_id = student["class_group_id"] if student else None
        filtered = scheduling.student_effective_blocks(
            self.db, self.navigator.week_start, self.selected_id, class_group_id
        )
        availability = scheduling.get_student_availability(self.db, self.selected_id, self.navigator.week_start)
        self.mini_grid.render(self.db, filtered, availability)
        totals = scheduling.summarize_student_hours(
            self.db, self.navigator.week_start, self.selected_id, class_group_id
        )
        self.summary_table.render(totals)

    def _handle_availability_changed(self, day: int, period: int, status) -> None:
        self._pending_availability[(day, period)] = status

    def handle_save_availability(self) -> None:
        if self.selected_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce listeden bir öğrenci seçin.")
            return
        if not self._pending_availability:
            QMessageBox.information(self, "Değişiklik yok", "Kaydedilecek bir müsaitlik değişikliği yok.")
            return
        dialog = ScopeDialog(self.db, self, "Müsaitlik değişikliklerini kaydetme")
        if dialog.exec() != ScopeDialog.Accepted:
            return
        scope = dialog.scope()
        for (day, period), status in self._pending_availability.items():
            scheduling.set_student_availability(self.db, self.navigator.week_start, self.selected_id, day, period, status, scope)
        self.refresh_detail()

    def handle_selection(self) -> None:
        items = self.table_widget.selectedItems()
        if not items:
            self.selected_id = None
            self._refresh_title_choices()
            self.refresh_detail()
            self.refresh_curriculum()
            return
        row = items[0].row()
        name_item = self.table_widget.item(row, 1)
        self.selected_id = name_item.data(Qt.UserRole)
        student = self.db.get_student(self.selected_id)
        self.name_edit.setText(student["name"])
        self._select_combo(self.class_combo, student["class_group_id"])
        self._select_combo(self.coach_combo, student["coach_teacher_id"])
        self.program_fee_spin.setValue(student["total_program_fee"])
        self.one_on_one_fee_spin.setValue(student["total_one_on_one_fee"])
        self._refresh_title_choices(checked_ids=set(self.db.get_student_title_ids(self.selected_id)))
        self.refresh_detail()
        self.refresh_curriculum()

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
        self._refresh_title_choices()
        self.table_widget.clearSelection()
        self.refresh_detail()
        self.refresh_curriculum()

    def handle_add(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik bilgi", "Öğrenci adı boş olamaz.")
            return
        new_id = self.db.add_student(
            name,
            self.class_combo.currentData(),
            self.coach_combo.currentData(),
            self.program_fee_spin.value(),
            self.one_on_one_fee_spin.value(),
        )
        self.db.set_student_titles(new_id, self._selected_title_ids())
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
        self.db.set_student_titles(self.selected_id, self._selected_title_ids())
        self.clear_form()
        self.refresh()
        if self.on_change:
            self.on_change()

    def handle_import_excel(self) -> None:
        dialog = ImportStudentsDialog(self.db, self)
        if dialog.exec() == QDialog.Accepted:
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

    # ---------- birebir ders hedefleri (Sınıflar sekmesindeki ders
    # hedefleri ile birebir aynı desen, bkz. classes_tab.py) ----------
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

    def _reload_curriculum_teachers(self) -> None:
        subject_name = self.curriculum_subject_combo.currentText()
        self.curriculum_teacher_combo.clear()
        teachers = self.db.list_teachers_by_subject_area(subject_name) if subject_name else []
        if not teachers:
            teachers = self.db.list_teachers()
        for teacher in teachers:
            self.curriculum_teacher_combo.addItem(teacher["name"], teacher["id"])

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

    def refresh_curriculum(self) -> None:
        self.curriculum_table.setRowCount(0)
        self.curriculum_status_label.setText("")
        if self.selected_id is None:
            return
        rows = self.db.list_student_curriculum(self.selected_id)
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

    def _selected_curriculum_id(self) -> int | None:
        items = self.curriculum_table.selectedItems()
        if not items:
            return None
        return self.curriculum_table.item(items[0].row(), 0).data(Qt.UserRole)

    def _handle_curriculum_selection(self) -> None:
        curriculum_id = self._selected_curriculum_id()
        if curriculum_id is None or self.selected_id is None:
            return
        row = next((r for r in self.db.list_student_curriculum(self.selected_id) if r["id"] == curriculum_id), None)
        if row is None:
            return

        idx_subject = self.curriculum_subject_combo.findData(row["subject_id"])
        if idx_subject >= 0:
            self.curriculum_subject_combo.setCurrentIndex(idx_subject)  # _reload_curriculum_teachers'i tetikler

        idx_teacher = self.curriculum_teacher_combo.findData(row["teacher_id"])
        if idx_teacher < 0 and row["teacher_id"] is not None and row["teacher_name"]:
            self.curriculum_teacher_combo.addItem(row["teacher_name"], row["teacher_id"])
            idx_teacher = self.curriculum_teacher_combo.count() - 1
        if idx_teacher >= 0:
            self.curriculum_teacher_combo.setCurrentIndex(idx_teacher)

        idx_room = self.curriculum_room_combo.findData(row["room_id"])
        self.curriculum_room_combo.setCurrentIndex(idx_room if idx_room >= 0 else 0)

        self.curriculum_hours_spin.setValue(row["weekly_hours"])

    def handle_add_curriculum(self) -> None:
        if self.selected_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce listeden bir öğrenci seçin.")
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
        self.db.add_student_curriculum(self.selected_id, subject_id, teacher_id, hours, room_id=room_id)
        self.refresh_curriculum()
        QMessageBox.information(
            self, "Eklendi",
            f"{hours} saat birebir ders 'Atanmamış Dersler' havuzuna eklendi. "
            "Ana Program'dan sürükleyerek ya da 'Oto Ata' ile yerleştirebilirsiniz.",
        )
        if self.on_change:
            self.on_change()

    def handle_update_curriculum(self) -> None:
        curriculum_id = self._selected_curriculum_id()
        if curriculum_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce tablodan güncellenecek hedefi seçin.")
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
        self.db.update_student_curriculum(curriculum_id, subject_id, teacher_id, hours, room_id=room_id)
        self.refresh_curriculum()
        QMessageBox.information(self, "Güncellendi", "Birebir ders hedefi güncellendi.")
        if self.on_change:
            self.on_change()

    def handle_delete_curriculum(self) -> None:
        curriculum_id = self._selected_curriculum_id()
        if curriculum_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce tablodan bir hedef seçin.")
            return
        confirm = QMessageBox.question(
            self, "Silme Onayı",
            "Bu birebir ders hedefi ve ona ait tüm ders saatleri (yerleştirilmiş olanlar dahil) silinecek. "
            "Devam edilsin mi?",
        )
        if confirm != QMessageBox.Yes:
            return
        self.db.delete_student_curriculum(curriculum_id)
        self.refresh_curriculum()
        if self.on_change:
            self.on_change()

    def handle_restore_curriculum(self) -> None:
        if self.selected_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce listeden bir öğrenci seçin.")
            return
        restored = 0
        for row in self.db.list_student_curriculum(self.selected_id):
            restored += self.db.restore_student_curriculum_blocks(row["id"])
        self.refresh_curriculum()
        if restored:
            QMessageBox.information(
                self, "Tamamlandı", f"{restored} saat havuza geri eklendi.",
            )
        else:
            QMessageBox.information(self, "Eksik yok", "Tüm hedef saatler zaten programda/havuzda mevcut.")
        if self.on_change:
            self.on_change()

    # ---------- toplu seçim / toplu silme ----------
    def _handle_row_check_toggled(self, student_id: int, checked: bool) -> None:
        if checked:
            self._checked_student_ids.add(student_id)
        else:
            self._checked_student_ids.discard(student_id)
        self._update_bulk_delete_state()

    def _update_bulk_delete_state(self) -> None:
        count = len(self._checked_student_ids)
        self.bulk_delete_button.setEnabled(count > 0)
        self.bulk_delete_button.setText(f"Seçilenleri Sil ({count})" if count else "Seçilenleri Sil")

    def _handle_select_all_toggled(self, checked: bool) -> None:
        # Sadece o an tabloda GÖRÜNEN (arama/filtre uygulanmış olabilir)
        # satırları toplu işaretler/kaldırır - her satırın kendi checkbox'ını
        # tetikleyerek yapar, böylece _checked_student_ids ile senkron kalır.
        for r in range(self.table_widget.rowCount()):
            container = self.table_widget.cellWidget(r, 0)
            if container is None:
                continue
            checkbox = container.findChild(QCheckBox)
            if checkbox is not None:
                checkbox.setChecked(checked)

    def handle_bulk_delete(self) -> None:
        ids = list(self._checked_student_ids)
        if not ids:
            return
        names = [r["name"] for r in self._all_rows if r["id"] in self._checked_student_ids]
        preview = "\n".join(f"- {n}" for n in names[:10])
        if len(names) > 10:
            preview += f"\n... ve {len(names) - 10} tane daha"
        confirm = QMessageBox.question(
            self, "Toplu Silme Onayı",
            f"{len(ids)} öğrenci silinsin mi?\nBu öğrencilere ait ders blokları ve ödeme kayıtları da silinir.\n\n"
            + preview,
        )
        if confirm != QMessageBox.Yes:
            return
        for student_id in ids:
            self.db.delete_student(student_id)
        self._checked_student_ids.clear()
        self.select_all_checkbox.setChecked(False)
        self.clear_form()
        self.refresh()
        if self.on_change:
            self.on_change()
