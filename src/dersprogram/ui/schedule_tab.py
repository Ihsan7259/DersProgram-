"""Ana Program: kurum genelindeki tek büyük tablo.

Günler en üstte yan yana (her günün altında kendi ders saati sütunları),
satırlarda sınıf ya da öğretmen (üstteki geçişle seçilir) alt alta
sıralanır - klasik okul programı yazılımlarındaki gibi. Sütunlar pencere
genişliğine sığacak şekilde otomatik daralır (yatay kaydırma yok, sadece
dikey). Altta 'Atanmamış Dersler' havuzu vardır; oradan bir dersi
sürükleyip kendi satırındaki (kendi sınıfı/öğretmeni) uygun bir
hücreye bırakabilirsiniz. Sürüklerken uygun hücreler yeşil, çakışan
ya da yanlış satırdaki hücreler kırmızı görünür.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QHeaderView,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QMessageBox,
    QSplitter,
    QButtonGroup,
)

from ..db import Database, LESSON_TYPES, TYPE_CLASS
from .. import scheduling
from .widgets import WeekNavigator, ScopeDialog
from .add_lesson_dialog import AddLessonDialog
from . import theme

MIME_PREFIX = "lesson-block:"

VALID_STYLE = f"#cellFrame {{ border:2px dashed {theme.VALID_BORDER}; border-radius:5px; background:{theme.VALID_BG}; }}"
INVALID_STYLE = f"#cellFrame {{ border:2px solid {theme.CONFLICT_BORDER}; border-radius:5px; background:{theme.CONFLICT_BG}; }}"

MODE_CLASS = "class"
MODE_TEACHER = "teacher"


class PoolList(QListWidget):
    """Atanmamış dersler havuzu; buradan ızgaraya sürüklenebilir."""

    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListWidget.Adjust)
        self.setSpacing(6)
        self.setStyleSheet(f"QListWidget {{ background:{theme.APP_BG}; border:none; }}")

    def mimeData(self, items):
        md = super().mimeData(items)
        if items:
            block_id = items[0].data(Qt.UserRole)
            md.setText(f"{MIME_PREFIX}{block_id}")
        return md


def _pool_chip(block) -> QWidget:
    _bg, dot = theme.LESSON_TYPE_COLORS.get(block.type, (theme.SURFACE, theme.INK_MUTED_58))
    chip = QWidget()
    layout = QHBoxLayout(chip)
    layout.setContentsMargins(11, 8, 12, 9)
    layout.setSpacing(7)
    dot_label = QLabel()
    dot_label.setFixedSize(7, 7)
    dot_label.setStyleSheet(f"background:{dot}; border-radius:3.5px;")
    layout.addWidget(dot_label)
    text = QLabel(block.pool_label_short())
    text.setToolTip(block.pool_label())
    text.setStyleSheet(f"font-size:8.5pt; font-weight:600; color:{theme.INK_MUTED_30}; background:transparent;")
    layout.addWidget(text)
    chip.setToolTip(block.pool_label())
    chip.setStyleSheet(
        f"background:{theme.SURFACE}; border:1px solid {theme.BORDER_SUBTLE}; border-radius:12px;"
    )
    chip.setMinimumHeight(26)
    return chip


class MainGrid(QTableWidget):
    """Satır = sınıf ya da öğretmen; sütun = gün+saat bileşiği (günler
    en üstte yan yana). Sütunlar pencereye sığacak şekilde otomatik
    daralır, yatay kaydırma kapalıdır - sadece aşağı kaydırılır."""

    def __init__(self, get_block_by_id, validate_drop, on_drop, on_remove_request):
        super().__init__()
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setShowGrid(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.horizontalHeader().setMinimumSectionSize(30)
        self._get_block_by_id = get_block_by_id
        self._validate_drop = validate_drop
        self._on_drop = on_drop
        self._on_remove_request = on_remove_request
        self._hover_cell = None
        self._hover_original = ""
        self._row_entity_ids: list[int] = []
        self._period_count = 1
        self.cellDoubleClicked.connect(self._handle_double_click)

    def col_to_day_period(self, col: int) -> tuple[int, int]:
        return col // self._period_count, (col % self._period_count) + 1

    def row_to_entity(self, row: int):
        if 0 <= row < len(self._row_entity_ids):
            return self._row_entity_ids[row]
        return None

    def _cell_of(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return None
        return index.row(), index.column()

    def dragEnterEvent(self, event):
        text = event.mimeData().text()
        if text.startswith(MIME_PREFIX):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        cell = self._cell_of(pos)
        if cell is None:
            event.ignore()
            return
        if cell != self._hover_cell:
            self._restore_hover()
            self._hover_cell = cell
            row, col = cell
            widget = self.cellWidget(row, col)
            if widget is not None:
                self._hover_original = widget.styleSheet()
                block_id = int(event.mimeData().text()[len(MIME_PREFIX):])
                block = self._get_block_by_id(block_id)
                entity_id = self.row_to_entity(row)
                day, period = self.col_to_day_period(col)
                valid = block is not None and self._validate_drop(block, entity_id, day, period)
                widget.setStyleSheet(VALID_STYLE if valid else INVALID_STYLE)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._restore_hover()
        super().dragLeaveEvent(event)

    def _restore_hover(self) -> None:
        if self._hover_cell is not None:
            row, col = self._hover_cell
            widget = self.cellWidget(row, col)
            if widget is not None:
                widget.setStyleSheet(self._hover_original)
        self._hover_cell = None

    def dropEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        cell = self._cell_of(pos)
        self._restore_hover()
        if cell is None:
            event.ignore()
            return
        block_id = int(event.mimeData().text()[len(MIME_PREFIX):])
        row, col = cell
        entity_id = self.row_to_entity(row)
        day, period = self.col_to_day_period(col)
        event.acceptProposedAction()
        self._on_drop(block_id, entity_id, day, period)

    def _handle_double_click(self, row: int, col: int) -> None:
        entity_id = self.row_to_entity(row)
        day, period = self.col_to_day_period(col)
        self._on_remove_request(entity_id, day, period)


class ScheduleTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.mode = MODE_CLASS
        self._schedule: dict[tuple[int, int], list] = {}
        self._pool: list = []
        self._blocks_by_id: dict[int, object] = {}
        self._row_entities: list[tuple[int, str]] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        self.navigator = WeekNavigator(lambda: len(self.db.day_names))
        top_row.addWidget(self.navigator, 1)

        self.class_mode_button = QPushButton("Sınıflara Göre")
        self.teacher_mode_button = QPushButton("Öğretmenlere Göre")
        for b in (self.class_mode_button, self.teacher_mode_button):
            b.setCheckable(True)
            b.setObjectName("modeButton")
        self.class_mode_button.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.class_mode_button)
        self.mode_group.addButton(self.teacher_mode_button)
        top_row.addWidget(self.class_mode_button)
        top_row.addWidget(self.teacher_mode_button)
        layout.addLayout(top_row)

        toolbar = QHBoxLayout()
        self.add_lesson_button = QPushButton("  Ders Ekle")
        self.add_lesson_button.setObjectName("outlineButton")
        self.add_lesson_button.setIcon(theme.icon(theme.NAV_ICONS["plus"], theme.ACCENT_HOVER))
        self.auto_assign_button = QPushButton("  Oto Ata")
        self.auto_assign_button.setObjectName("primaryButton")
        self.auto_assign_button.setIcon(theme.icon(theme.NAV_ICONS["bolt"], theme.AMBER_TEXT))
        toolbar.addStretch()
        toolbar.addWidget(self.add_lesson_button)
        toolbar.addWidget(self.auto_assign_button)
        layout.addLayout(toolbar)

        legend = QHBoxLayout()
        legend.setSpacing(18)
        for lesson_type in LESSON_TYPES:
            bg, dot = theme.LESSON_TYPE_COLORS[lesson_type]
            item = QHBoxLayout()
            item.setSpacing(6)
            dot_label = QLabel()
            dot_label.setFixedSize(8, 8)
            dot_label.setStyleSheet(f"background:{dot}; border-radius:4px;")
            item.addWidget(dot_label)
            text = QLabel(theme.lesson_type_label(lesson_type))
            text.setStyleSheet(f"font-size:9pt; color:{theme.INK_MUTED_42};")
            item.addWidget(text)
            legend.addLayout(item)
        legend.addStretch()
        layout.addLayout(legend)

        splitter = QSplitter(Qt.Vertical)

        self.grid = MainGrid(
            get_block_by_id=lambda bid: self._blocks_by_id.get(bid),
            validate_drop=self._validate_drop,
            on_drop=self._handle_drop,
            on_remove_request=self._handle_remove_request,
        )
        splitter.addWidget(self.grid)

        pool_container = QWidget()
        pool_layout = QVBoxLayout(pool_container)
        pool_layout.setContentsMargins(0, 0, 0, 0)
        self.pool_label = QLabel("Atanmamış Dersler")
        self.pool_label.setStyleSheet(
            f"font-family:'{theme.FONT_HEADING}'; font-weight:700; font-size:10pt; color:{theme.INK_MUTED_30};"
        )
        pool_layout.addWidget(self.pool_label)
        self.hint_label = QLabel()
        self.hint_label.setStyleSheet(f"font-size:8.3pt; color:{theme.INK_MUTED_58};")
        pool_layout.addWidget(self.hint_label)
        self.pool_list = PoolList()
        pool_layout.addWidget(self.pool_list)
        splitter.addWidget(pool_container)
        splitter.setSizes([520, 190])

        layout.addWidget(splitter, 1)

        self.add_lesson_button.clicked.connect(self.handle_add_lesson)
        self.auto_assign_button.clicked.connect(self.handle_auto_assign)
        self.navigator.week_changed.connect(lambda _w: self.refresh())
        self.class_mode_button.toggled.connect(self._handle_mode_change)

        self._update_hint()
        self.refresh()

    def _handle_mode_change(self, checked: bool) -> None:
        self.mode = MODE_CLASS if checked else MODE_TEACHER
        self._update_hint()
        self.refresh()

    def _update_hint(self) -> None:
        if self.mode == MODE_CLASS:
            self.hint_label.setText(
                "Sürükleyip yukarıya bırakın (sadece kendi sınıfının satırına). "
                "Birebir/koçluk/zümre/soru çözümü dersleri için 'Öğretmenlere Göre' görünümüne geçin. "
                "Kaldırmak için hücreye çift tıklayın."
            )
        else:
            self.hint_label.setText(
                "Sürükleyip yukarıya bırakın (sadece kendi öğretmeninin satırına). "
                "Kaldırmak için hücreye çift tıklayın."
            )

    # ---------- veri yenileme ----------
    def refresh(self) -> None:
        self._schedule, self._pool = scheduling.get_week_view(self.db, self.navigator.week_start)
        self._blocks_by_id = {b.id: b for b in self._pool}
        for blocks in self._schedule.values():
            for b in blocks:
                self._blocks_by_id[b.id] = b

        if self.mode == MODE_CLASS:
            rows = self.db.list_rows("class_groups")
        else:
            rows = self.db.list_teachers()
        self._row_entities = sorted(
            ((r["id"], r["name"]) for r in rows), key=lambda pair: scheduling.natural_sort_key(pair[1])
        )

        self._render_grid()
        self._render_pool()

    def _cell_blocks(self, entity_id: int, day: int, period: int) -> list:
        blocks = self._schedule.get((day, period), [])
        if self.mode == MODE_CLASS:
            return [b for b in blocks if b.type == TYPE_CLASS and b.class_group_id == entity_id]
        return [b for b in blocks if b.teacher_id == entity_id]

    def _render_grid(self) -> None:
        day_names = self.db.day_names
        period_count = self.db.period_count
        self.grid._period_count = period_count
        self.grid._row_entity_ids = [entity_id for entity_id, _name in self._row_entities]

        self.grid.setColumnCount(len(day_names) * period_count)
        headers = []
        for day_name in day_names:
            for period in range(1, period_count + 1):
                headers.append(f"{scheduling.day_abbrev(day_name)}\n{period}")
        self.grid.setHorizontalHeaderLabels(headers)

        self.grid.setRowCount(len(self._row_entities))
        self.grid.setVerticalHeaderLabels([name for _id, name in self._row_entities])

        for row, (entity_id, _name) in enumerate(self._row_entities):
            self.grid.setRowHeight(row, 38)
            for day in range(len(day_names)):
                for period in range(1, period_count + 1):
                    col = day * period_count + (period - 1)
                    blocks = self._cell_blocks(entity_id, day, period)
                    if not blocks:
                        widget = theme.make_dense_empty()
                    elif len(blocks) == 1:
                        line1, line2 = blocks[0].dense_lines(self.mode)
                        bg, _dot = theme.LESSON_TYPE_COLORS.get(blocks[0].type, (theme.SURFACE, theme.INK_MUTED_58))
                        widget = theme.make_dense_chip(line1, line2, bg)
                    else:
                        line1, line2 = blocks[0].dense_lines(self.mode)
                        bg, _dot = theme.LESSON_TYPE_COLORS.get(blocks[0].type, (theme.SURFACE, theme.INK_MUTED_58))
                        widget = theme.make_dense_chip(f"{line1} (+{len(blocks) - 1})", line2, bg)
                    self.grid.setCellWidget(row, col, widget)

    def _render_pool(self) -> None:
        self.pool_label.setText(f"Atanmamış Dersler ({len(self._pool)})")
        self.pool_list.clear()
        for block in sorted(self._pool, key=lambda b: b.pool_label()):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, block.id)
            chip = _pool_chip(block)
            self.pool_list.addItem(item)
            self.pool_list.setItemWidget(item, chip)
            item.setSizeHint(chip.sizeHint())

    # ---------- yerleştirme / kaldırma ----------
    def _row_matches_block(self, block, entity_id) -> bool:
        if self.mode == MODE_CLASS:
            return block.type == TYPE_CLASS and block.class_group_id == entity_id
        return block.teacher_id == entity_id

    def _validate_drop(self, block, entity_id, day: int, period: int) -> bool:
        if not self._row_matches_block(block, entity_id):
            return False
        return not scheduling.find_conflicts(self._schedule, day, period, block)

    def _handle_drop(self, block_id: int, entity_id, day: int, period: int) -> None:
        block = self._blocks_by_id.get(block_id)
        if block is None:
            return
        if not self._row_matches_block(block, entity_id):
            row_word = "sınıfa" if self.mode == MODE_CLASS else "öğretmene"
            QMessageBox.warning(
                self, "Yanlış satır",
                f"'{block.pool_label()}' dersi bu {row_word} ait değil. "
                "Lütfen kendi satırına bırakın (ya da uygun görünüme geçin).",
            )
            return
        conflicts = scheduling.find_conflicts(self._schedule, day, period, block)
        if conflicts:
            proceed = QMessageBox.question(
                self,
                "Çakışma bulundu",
                "Bu hücreye yerleştirmek şu çakışmalara yol açar:\n- " + "\n- ".join(conflicts) +
                "\n\nYine de yerleştirmek istiyor musunuz?",
            )
            if proceed != QMessageBox.Yes:
                return

        dialog = ScopeDialog(self, f"'{block.pool_label()}' dersini yerleştirme")
        if dialog.exec() != ScopeDialog.Accepted:
            return
        scheduling.place_block(self.db, self.navigator.week_start, block_id, day, period, dialog.scope())
        self.refresh()

    def _handle_remove_request(self, entity_id, day: int, period: int) -> None:
        blocks = self._cell_blocks(entity_id, day, period)
        if not blocks:
            return
        chosen = blocks[0]
        dialog = ScopeDialog(self, f"'{chosen.pool_label()}' dersini kaldırma")
        if dialog.exec() != ScopeDialog.Accepted:
            return
        scheduling.clear_block(self.db, self.navigator.week_start, chosen.id, dialog.scope())
        self.refresh()

    # ---------- ders ekle / oto ata ----------
    def handle_add_lesson(self) -> None:
        dialog = AddLessonDialog(self.db, self)
        if dialog.exec() == AddLessonDialog.Accepted:
            self.refresh()

    def handle_auto_assign(self) -> None:
        count = scheduling.auto_assign(self.db, self.navigator.week_start)
        self.refresh()
        QMessageBox.information(self, "Oto Ata", f"{count} ders otomatik olarak yerleştirildi.")
