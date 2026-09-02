"""Ana Program: kurum genelindeki büyük, düzenlenebilir haftalık ızgara.

Altta 'Atanmamış Dersler' havuzu vardır; oradan bir dersi sürükleyip
ızgaraya bırakabilirsiniz. Sürüklerken uygun hücreler yeşil, çakışan
hücreler kırmızı görünür. Bırakınca değişikliğin sadece bu hafta mı
yoksa kalıcı mı olacağı sorulur.
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
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QMessageBox,
    QInputDialog,
    QSplitter,
)

from ..db import Database, LESSON_TYPES
from .. import scheduling
from .widgets import WeekNavigator, ScopeDialog
from .add_lesson_dialog import AddLessonDialog
from . import theme

MIME_PREFIX = "lesson-block:"

VALID_STYLE = f"#cellFrame {{ border:2px dashed {theme.VALID_BORDER}; border-radius:8px; background:{theme.VALID_BG}; }}"
INVALID_STYLE = f"#cellFrame {{ border:2px solid {theme.CONFLICT_BORDER}; border-radius:8px; background:{theme.CONFLICT_BG}; }}"


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
    text = QLabel(block.pool_label())
    text.setStyleSheet(f"font-size:9pt; font-weight:600; color:{theme.INK_MUTED_30}; background:transparent;")
    layout.addWidget(text)
    chip.setStyleSheet(
        f"background:{theme.SURFACE}; border:1px solid {theme.BORDER_SUBTLE}; border-radius:14px;"
    )
    chip.setMinimumHeight(32)
    return chip


class MainGrid(QTableWidget):
    def __init__(self, get_block_by_id, validate_drop, on_drop, on_remove_request):
        super().__init__()
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setShowGrid(False)
        self._get_block_by_id = get_block_by_id
        self._validate_drop = validate_drop
        self._on_drop = on_drop
        self._on_remove_request = on_remove_request
        self._hover_cell = None
        self._hover_original = ""
        self.cellDoubleClicked.connect(self._handle_double_click)

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
                day, period = col, row + 1
                valid = block is not None and self._validate_drop(block, day, period)
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
        day, period = col, row + 1
        event.acceptProposedAction()
        self._on_drop(block_id, day, period)

    def _handle_double_click(self, row: int, col: int) -> None:
        self._on_remove_request(col, row + 1)


class ScheduleTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self._schedule: dict[tuple[int, int], list] = {}
        self._pool: list = []
        self._blocks_by_id: dict[int, object] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self.navigator = WeekNavigator(lambda: len(self.db.day_names))
        layout.addWidget(self.navigator)

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
        hint = QLabel("Sürükleyip yukarıya bırakın. Yerleştirilmiş bir dersi kaldırmak için üstündeki hücreye çift tıklayın.")
        hint.setStyleSheet(f"font-size:8.3pt; color:{theme.INK_MUTED_58};")
        pool_layout.addWidget(hint)
        self.pool_list = PoolList()
        pool_layout.addWidget(self.pool_list)
        splitter.addWidget(pool_container)
        splitter.setSizes([520, 190])

        layout.addWidget(splitter, 1)

        self.add_lesson_button.clicked.connect(self.handle_add_lesson)
        self.auto_assign_button.clicked.connect(self.handle_auto_assign)
        self.navigator.week_changed.connect(lambda _w: self.refresh())

        self.refresh()

    # ---------- veri yenileme ----------
    def refresh(self) -> None:
        self._schedule, self._pool = scheduling.get_week_view(self.db, self.navigator.week_start)
        self._blocks_by_id = {b.id: b for b in self._pool}
        for blocks in self._schedule.values():
            for b in blocks:
                self._blocks_by_id[b.id] = b
        self._render_grid()
        self._render_pool()

    def _render_grid(self) -> None:
        day_names = self.db.day_names
        period_count = self.db.period_count
        self.grid.setRowCount(period_count)
        self.grid.setColumnCount(len(day_names))
        self.grid.setHorizontalHeaderLabels(day_names)
        self.grid.setVerticalHeaderLabels([f"{p}. Ders" for p in range(1, period_count + 1)])

        for period in range(1, period_count + 1):
            self.grid.setRowHeight(period - 1, 88)
            for day in range(len(day_names)):
                blocks = self._schedule.get((day, period), [])
                self.grid.setCellWidget(period - 1, day, theme.make_multi_cell(blocks))

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
    def _validate_drop(self, block, day: int, period: int) -> bool:
        return not scheduling.find_conflicts(self._schedule, day, period, block)

    def _handle_drop(self, block_id: int, day: int, period: int) -> None:
        block = self._blocks_by_id.get(block_id)
        if block is None:
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

    def _handle_remove_request(self, day: int, period: int) -> None:
        blocks = self._schedule.get((day, period), [])
        if not blocks:
            return
        if len(blocks) == 1:
            chosen = blocks[0]
        else:
            labels = [b.short_label().replace("\n", " - ") for b in blocks]
            label, ok = QInputDialog.getItem(
                self, "Hangi ders kaldırılsın?", "Ders:", labels, editable=False
            )
            if not ok:
                return
            chosen = blocks[labels.index(label)]

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
