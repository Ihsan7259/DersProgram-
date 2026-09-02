"""Ana Program: kurum genelindeki büyük, düzenlenebilir haftalık ızgara.

Altta 'Atanmamış Dersler' havuzu vardır; oradan bir dersi sürükleyip
ızgaraya bırakabilirsiniz. Sürüklerken uygun hücreler yeşil, çakışan
hücreler kırmızı görünür. Bırakınca değişikliğin sadece bu hafta mı
yoksa kalıcı mı olacağı sorulur.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QMessageBox,
    QInputDialog,
    QSplitter,
)

from ..db import Database
from .. import scheduling
from .widgets import WeekNavigator, ScopeDialog
from .add_lesson_dialog import AddLessonDialog

COLOR_EMPTY = QBrush(QColor("#f5f5f5"))
COLOR_FILLED = QBrush(QColor("#ffffff"))
COLOR_VALID_DROP = QBrush(QColor("#bff2c8"))
COLOR_INVALID_DROP = QBrush(QColor("#f8b4b4"))

MIME_PREFIX = "lesson-block:"


class PoolList(QListWidget):
    """Atanmamış dersler havuzu; buradan ızgaraya sürüklenebilir."""

    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def mimeData(self, items):
        md = super().mimeData(items)
        if items:
            block_id = items[0].data(Qt.UserRole)
            md.setText(f"{MIME_PREFIX}{block_id}")
        return md


class MainGrid(QTableWidget):
    def __init__(self, get_block_by_id, validate_drop, on_drop, on_remove_request):
        super().__init__()
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self._get_block_by_id = get_block_by_id
        self._validate_drop = validate_drop
        self._on_drop = on_drop
        self._on_remove_request = on_remove_request
        self._hover_cell = None
        self.cellDoubleClicked.connect(self._handle_double_click)

    def _cell_of(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return None
        return item.row(), item.column()

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
            block_id = int(event.mimeData().text()[len(MIME_PREFIX):])
            block = self._get_block_by_id(block_id)
            row, col = cell
            day, period = col, row + 1
            valid = block is not None and self._validate_drop(block, day, period)
            item = self.item(row, col)
            if item is not None:
                item.setBackground(COLOR_VALID_DROP if valid else COLOR_INVALID_DROP)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._restore_hover()
        super().dragLeaveEvent(event)

    def _restore_hover(self) -> None:
        if self._hover_cell is not None:
            row, col = self._hover_cell
            item = self.item(row, col)
            if item is not None:
                item.setBackground(COLOR_FILLED if item.text() else COLOR_EMPTY)
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

        self.navigator = WeekNavigator(lambda: len(self.db.day_names))
        layout.addWidget(self.navigator)

        top_row = QHBoxLayout()
        self.add_lesson_button = QPushButton("Ders Ekle")
        self.auto_assign_button = QPushButton("Oto Ata")
        top_row.addWidget(self.add_lesson_button)
        top_row.addWidget(self.auto_assign_button)
        top_row.addStretch()
        layout.addLayout(top_row)

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
        pool_layout.addWidget(QLabel(
            "Atanmamış Dersler (sürükleyip yukarıdaki tabloya bırakın; "
            "yerleştirilmiş bir dersi kaldırmak için üstündeki hücreye çift tıklayın):"
        ))
        self.pool_list = PoolList()
        pool_layout.addWidget(self.pool_list)
        splitter.addWidget(pool_container)
        splitter.setSizes([500, 200])

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
            for day in range(len(day_names)):
                blocks = self._schedule.get((day, period), [])
                text = "\n───\n".join(b.short_label() for b in blocks)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(COLOR_FILLED if blocks else COLOR_EMPTY)
                self.grid.setItem(period - 1, day, item)
        self.grid.resizeRowsToContents()

    def _render_pool(self) -> None:
        self.pool_list.clear()
        for block in sorted(self._pool, key=lambda b: b.pool_label()):
            item = QListWidgetItem(block.pool_label())
            item.setData(Qt.UserRole, block.id)
            self.pool_list.addItem(item)

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
