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

from PySide6.QtCore import Qt, Signal
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
    QDialog,
)

from ..db import Database, LESSON_TYPES, TYPE_CLASS
from .. import scheduling
from .widgets import WeekNavigator, ScopeDialog, MiniScheduleGrid
from .add_lesson_dialog import AddLessonDialog
from . import theme

MIME_PREFIX = "lesson-block:"

VALID_STYLE = f"#cellFrame {{ border:2px dashed {theme.VALID_BORDER}; border-radius:5px; background:{theme.VALID_BG}; }}"
INVALID_STYLE = f"#cellFrame {{ border:2px solid {theme.CONFLICT_BORDER}; border-radius:5px; background:{theme.CONFLICT_BG}; }}"

MODE_CLASS = "class"
MODE_TEACHER = "teacher"


class PoolList(QListWidget):
    """Atanmamış dersler havuzu; buradan ızgaraya sürüklenebilir."""

    delete_requested = Signal()

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

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_requested.emit()
            return
        super().keyPressEvent(event)


def _group_pool_labels(rep_block, members: list) -> tuple[str, str]:
    """Bir zümre grubu (birden fazla öğretmenin aynı buluşması) için
    (kısa, tam) etiket döner; tek üyeli gruplarda normal etiketlere
    düşer."""
    if len(members) <= 1:
        return rep_block.pool_label_short(), rep_block.pool_label()
    names = sorted(m.teacher_name or "" for m in members)
    short = f"Züm · {len(members)} hoca"
    if rep_block.subject_name:
        short = f"Züm · {rep_block.subject_name[:4]} · {len(members)} hoca"
    full = "Zümre" + (f" · {rep_block.subject_name}" if rep_block.subject_name else "") + " · " + ", ".join(names)
    return short, full


def _pool_chip(rep_block, members: list) -> QWidget:
    _bg, dot = theme.LESSON_TYPE_COLORS.get(rep_block.type, (theme.SURFACE, theme.INK_MUTED_58))
    short_text, full_text = _group_pool_labels(rep_block, members)
    chip = QWidget()
    layout = QHBoxLayout(chip)
    layout.setContentsMargins(11, 8, 12, 9)
    layout.setSpacing(7)
    dot_label = QLabel()
    dot_label.setFixedSize(7, 7)
    dot_label.setStyleSheet(f"background:{dot}; border-radius:3.5px;")
    layout.addWidget(dot_label)
    text = QLabel(short_text)
    text.setToolTip(full_text)
    text.setStyleSheet(f"font-size:8.5pt; font-weight:600; color:{theme.INK_MUTED_30}; background:transparent;")
    layout.addWidget(text)
    chip.setToolTip(full_text)
    chip.setStyleSheet(
        f"background:{theme.SURFACE}; border:1px solid {theme.BORDER_SUBTLE}; border-radius:12px;"
    )
    chip.setMinimumHeight(26)
    return chip


class MainGrid(QTableWidget):
    """Satır = sınıf ya da öğretmen; sütun = gün+saat bileşiği (günler
    en üstte yan yana). Sütunlar pencereye sığacak şekilde otomatik
    daralır, yatay kaydırma kapalıdır - sadece aşağı kaydırılır."""

    row_header_double_clicked = Signal(int)  # entity_id

    def __init__(self, get_block_by_id, validate_drop, on_drop, on_remove_request):
        super().__init__()
        self.setObjectName("mainGrid")
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setShowGrid(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setMinimumSectionSize(8)
        header.setMinimumHeight(36)
        header.setDefaultAlignment(Qt.AlignCenter)
        self.verticalHeader().sectionDoubleClicked.connect(self._handle_row_header_double_click)
        self._get_block_by_id = get_block_by_id
        self._validate_drop = validate_drop
        self._on_drop = on_drop
        self._on_remove_request = on_remove_request
        self._hover_cell = None
        self._hover_original = ""
        self._row_entity_ids: list[int] = []
        self._day_names: list[str] = []
        self._day_count = 1
        self._period_count = 1
        self._zoom = 1.0
        self.cellDoubleClicked.connect(self._handle_double_click)
        self._apply_column_sizing()

    # ---------- yakınlaştırma / sütun sıkıştırma ----------
    def set_grid_shape(self, day_names: list[str], period_count: int) -> None:
        self._day_names = list(day_names)
        self._day_count = max(len(day_names), 1)
        self._period_count = max(period_count, 1)
        self._apply_column_sizing()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = zoom
        self._apply_column_sizing()

    def row_height(self) -> int:
        return max(22, int(38 * self._zoom))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_column_sizing()

    def _apply_column_sizing(self) -> None:
        """Varsayılan yakınlaştırmada (%100) sütunlar pencereye TAM sığar,
        yatay kaydırma hiç gerekmez. Kullanıcı yakınlaştırırsa (zoom>1)
        sütunlar sabit genişlikte büyür ve yatay kaydırma açılır - detay
        görmek isteyince kaydırma kabul edilebilir, varsayılanda değil."""
        total_columns = self._day_count * self._period_count
        available = self.viewport().width()
        fit_per_column = 34 if available <= 0 else max(8, available // total_columns)
        per_column = max(8, int(fit_per_column * self._zoom))
        header = self.horizontalHeader()

        if self._zoom <= 1.0:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            header.setSectionResizeMode(QHeaderView.Stretch)
            header.setMinimumSectionSize(min(per_column, 34))
        else:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            header.setSectionResizeMode(QHeaderView.Fixed)
            header.setMinimumSectionSize(per_column)
            for col in range(self.columnCount()):
                self.setColumnWidth(col, per_column)

        if per_column >= 30:
            font_pt, padding = 7.6, 2
        elif per_column >= 22:
            font_pt, padding = 6.6, 1
        elif per_column >= 16:
            font_pt, padding = 5.8, 1
        else:
            font_pt, padding = 5.0, 0
        font_pt *= max(1.0, self._zoom)
        self.setStyleSheet(
            f"#mainGrid QHeaderView::section {{ font-size: {font_pt:.1f}pt; padding: {padding}px 0; }}"
        )
        self._apply_header_labels(per_column)
        for row in range(self.rowCount()):
            self.setRowHeight(row, self.row_height())

    def _apply_header_labels(self, per_column: int) -> None:
        """Sütunlar iyice daraldığında gün kısaltması sadece o günün ilk
        saatinde yazılır, kalan sütunlarda yalnızca saat numarası kalır -
        böylece dar sütunlarda da yazılar kırpılmaz."""
        if not self._day_names or self.columnCount() != self._day_count * self._period_count:
            return
        compact = per_column < 26
        headers = []
        for day_name in self._day_names:
            abbrev = scheduling.day_abbrev(day_name)
            for period in range(1, self._period_count + 1):
                if compact and period != 1:
                    headers.append(str(period))
                else:
                    headers.append(f"{abbrev}\n{period}")
        self.setHorizontalHeaderLabels(headers)

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

    def _handle_row_header_double_click(self, row: int) -> None:
        entity_id = self.row_to_entity(row)
        if entity_id is not None:
            self.row_header_double_clicked.emit(entity_id)


class RowPreviewDialog(QDialog):
    """Ana Program'da bir sınıf/öğretmen adının üstüne çift tıklanınca
    açılan, sadece o satırın haftalık programını gösteren salt-okunur
    önizleme penceresi."""

    def __init__(self, db: Database, week_start, mode: str, entity_id: int, entity_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{entity_name} - Haftalık Program (Önizleme)")
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        title = QLabel(entity_name)
        title.setStyleSheet(f"font-family:'{theme.FONT_HEADING}'; font-weight:700; font-size:13pt;")
        layout.addWidget(title)
        subtitle = QLabel(scheduling.week_label(week_start, len(db.day_names)))
        subtitle.setStyleSheet(f"font-size:9pt; color:{theme.INK_MUTED_58};")
        layout.addWidget(subtitle)

        schedule, _pool = scheduling.get_week_view(db, week_start)
        filtered: dict[tuple[int, int], list] = {}
        for cell, blocks in schedule.items():
            if mode == MODE_CLASS:
                matched = [b for b in blocks if b.type == TYPE_CLASS and b.class_group_id == entity_id]
            else:
                matched = [b for b in blocks if b.teacher_id == entity_id]
            if matched:
                filtered[cell] = matched

        grid = MiniScheduleGrid()
        grid.render(db, filtered, row_mode="class" if mode == MODE_CLASS else None)
        layout.addWidget(grid, 1)

        close_button = QPushButton("Kapat")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)


class ScheduleTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.mode = MODE_CLASS
        self._schedule: dict[tuple[int, int], list] = {}
        self._pool: list = []
        self._blocks_by_id: dict[int, object] = {}
        self._row_entities: list[tuple[int, str]] = []
        self._unavailable = scheduling.UnavailableSlots()

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
        self.zoom_out_button = QPushButton("−")
        self.zoom_out_button.setObjectName("iconButton")
        self.zoom_out_button.setFixedSize(28, 28)
        self.zoom_out_button.setToolTip("Uzaklaştır")
        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(38)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setStyleSheet(f"font-size:9pt; color:{theme.INK_MUTED_42};")
        self.zoom_in_button = QPushButton("+")
        self.zoom_in_button.setObjectName("iconButton")
        self.zoom_in_button.setFixedSize(28, 28)
        self.zoom_in_button.setToolTip("Yakınlaştır (detaylı görünüm)")
        toolbar.addWidget(self.zoom_out_button)
        toolbar.addWidget(self.zoom_label)
        toolbar.addWidget(self.zoom_in_button)
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
        pool_header = QHBoxLayout()
        self.pool_label = QLabel("Atanmamış Dersler")
        self.pool_label.setStyleSheet(
            f"font-family:'{theme.FONT_HEADING}'; font-weight:700; font-size:10pt; color:{theme.INK_MUTED_30};"
        )
        pool_header.addWidget(self.pool_label)
        pool_header.addStretch()
        self.pool_delete_button = QPushButton("Seçili Dersi Sil")
        self.pool_delete_button.setObjectName("outlineButton")
        self.pool_delete_button.clicked.connect(self.handle_delete_pool_lesson)
        pool_header.addWidget(self.pool_delete_button)
        pool_layout.addLayout(pool_header)
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
        self.pool_list.delete_requested.connect(self.handle_delete_pool_lesson)
        self.navigator.week_changed.connect(lambda _w: self.refresh())
        self.class_mode_button.toggled.connect(self._handle_mode_change)
        self.zoom_in_button.clicked.connect(lambda: self._change_zoom(0.15))
        self.zoom_out_button.clicked.connect(lambda: self._change_zoom(-0.15))
        self.grid.row_header_double_clicked.connect(self._show_row_preview)

        self._update_hint()
        self.refresh()

    # ---------- yakınlaştırma ----------
    def _change_zoom(self, delta: float) -> None:
        zoom = round(min(2.2, max(0.7, self.grid._zoom + delta)), 2)
        self.grid.set_zoom(zoom)
        self.zoom_label.setText(f"{round(zoom * 100)}%")
        # Hücre kartlarını (sabit boyutlu widget'lar) yeni satır/sütun
        # ölçüsüne göre baştan oluştur - sadece boyut değiştirmek eski
        # widget'lardan görsel kalıntı bırakabiliyor.
        self._render_grid()

    def _show_row_preview(self, entity_id: int) -> None:
        name = next((n for i, n in self._row_entities if i == entity_id), "")
        dialog = RowPreviewDialog(self.db, self.navigator.week_start, self.mode, entity_id, name, self)
        dialog.exec()

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
        self._unavailable = scheduling.UnavailableSlots.compute(self.db, self.navigator.week_start)
        self._blocks_by_id = {b.id: b for b in self._pool}
        for blocks in self._schedule.values():
            for b in blocks:
                self._blocks_by_id[b.id] = b

        if self.mode == MODE_CLASS:
            # Sınıflar elle sıralanabilir (bkz. ClassesTab yukarı/aşağı
            # okları); Ana Program satırları da bu sırayı yansıtır.
            self._row_entities = [(r["id"], r["name"]) for r in self.db.list_class_groups()]
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
        self.grid._row_entity_ids = [entity_id for entity_id, _name in self._row_entities]

        self.grid.setColumnCount(len(day_names) * period_count)
        # Sütun sayısı belli olduktan sonra: başlıklar + gün/saat sayısına
        # göre otomatik sıkıştırma (yatay kaydırma hiçbir zaman gerekmez).
        self.grid.set_grid_shape(day_names, period_count)

        self.grid.setRowCount(len(self._row_entities))
        self.grid.setVerticalHeaderLabels([name for _id, name in self._row_entities])

        for row, (entity_id, _name) in enumerate(self._row_entities):
            self.grid.setRowHeight(row, self.grid.row_height())
            for day in range(len(day_names)):
                for period in range(1, period_count + 1):
                    col = day * period_count + (period - 1)
                    blocks = self._cell_blocks(entity_id, day, period)
                    if not blocks:
                        if self.mode == MODE_TEACHER and (entity_id, day, period) in self._unavailable.teacher:
                            widget = theme.make_dense_unavailable()
                        elif self.mode == MODE_CLASS and (entity_id, day, period) in self._unavailable.class_:
                            widget = theme.make_dense_unavailable()
                        else:
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
        seen_groups: set[int] = set()
        pool_items: list[tuple] = []  # (rep_block, members)
        for block in self._pool:
            if block.zumre_group_id is not None:
                if block.zumre_group_id in seen_groups:
                    continue
                seen_groups.add(block.zumre_group_id)
                members = self._group_members(block.zumre_group_id)
                rep = min(members, key=lambda b: b.id)
                pool_items.append((rep, members))
            else:
                pool_items.append((block, [block]))
        for rep, members in sorted(pool_items, key=lambda pair: pair[0].pool_label()):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, rep.id)
            chip = _pool_chip(rep, members)
            self.pool_list.addItem(item)
            self.pool_list.setItemWidget(item, chip)
            item.setSizeHint(chip.sizeHint())

    # ---------- zümre grupları ----------
    def _group_members(self, zumre_group_id: int) -> list:
        return [b for b in self._blocks_by_id.values() if b.zumre_group_id == zumre_group_id]

    def _block_group(self, block) -> list:
        """block'un ait olduğu tüm üyeler (zümre grubu değilse sadece kendisi)."""
        if block.zumre_group_id is not None:
            return self._group_members(block.zumre_group_id)
        return [block]

    @staticmethod
    def _group_label(members: list) -> str:
        if len(members) <= 1:
            return members[0].pool_label()
        names = sorted(m.teacher_name or "" for m in members)
        return "Zümre (" + ", ".join(names) + ")"

    # ---------- yerleştirme / kaldırma ----------
    MAX_STACKED_PER_CELL = 2

    def _row_matches_block(self, block, entity_id) -> bool:
        if self.mode == MODE_CLASS:
            return block.type == TYPE_CLASS and block.class_group_id == entity_id
        return any(m.teacher_id == entity_id for m in self._block_group(block))

    def _stack_overflow(self, members: list, day: int, period: int) -> str | None:
        """Bir hücrede (aynı sınıf/öğretmen satırında) hiçbir zaman
        MAX_STACKED_PER_CELL'den fazla ders üst üste binmesin diye sert bir
        sınır - çakışma uyarısının aksine, 'yine de yerleştir' ile
        aşılamaz."""
        for member in members:
            row_entity_id = member.class_group_id if self.mode == MODE_CLASS else member.teacher_id
            if row_entity_id is None:
                continue
            existing = [b for b in self._cell_blocks(row_entity_id, day, period) if b.id != member.id]
            if len(existing) + 1 > self.MAX_STACKED_PER_CELL:
                who = member.class_name if self.mode == MODE_CLASS else member.teacher_name
                return (
                    f"{who} bu saatte zaten {len(existing)} ders içeriyor - bir hücrede en fazla "
                    f"{self.MAX_STACKED_PER_CELL} ders üst üste olabilir."
                )
        return None

    def _validate_drop(self, block, entity_id, day: int, period: int) -> bool:
        if not self._row_matches_block(block, entity_id):
            return False
        members = self._block_group(block)
        if self._stack_overflow(members, day, period):
            return False
        return not scheduling.find_group_conflicts(self._schedule, day, period, members, self._unavailable)

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
        members = self._block_group(block)
        label = self._group_label(members)
        overflow = self._stack_overflow(members, day, period)
        if overflow:
            QMessageBox.warning(self, "Hücre dolu", overflow)
            return
        conflicts = scheduling.find_group_conflicts(self._schedule, day, period, members, self._unavailable)
        if conflicts:
            proceed = QMessageBox.question(
                self,
                "Çakışma bulundu",
                f"'{label}' dersini bu hücreye yerleştirmek şu çakışmalara yol açar:\n- " + "\n- ".join(conflicts) +
                "\n\nYine de yerleştirmek istiyor musunuz?",
            )
            if proceed != QMessageBox.Yes:
                return

        dialog = ScopeDialog(self.db, self, f"'{label}' dersini yerleştirme")
        if dialog.exec() != ScopeDialog.Accepted:
            return
        scope = dialog.scope()
        for member in members:
            scheduling.place_block(self.db, self.navigator.week_start, member.id, day, period, scope)
        self.refresh()

    def _handle_remove_request(self, entity_id, day: int, period: int) -> None:
        blocks = self._cell_blocks(entity_id, day, period)
        if not blocks:
            return
        chosen = blocks[0]
        members = self._block_group(chosen)
        label = self._group_label(members)
        dialog = ScopeDialog(self.db, self, f"'{label}' dersini kaldırma")
        if dialog.exec() != ScopeDialog.Accepted:
            return
        scope = dialog.scope()
        for member in members:
            scheduling.clear_block(self.db, self.navigator.week_start, member.id, scope)
        self.refresh()

    def handle_delete_pool_lesson(self) -> None:
        """Havuzdaki seçili dersi tamamen siler (zümre ise tüm grubu).
        Silinen ders bir sınıf hedefine bağlıysa, Sınıflar sekmesindeki
        'Ders Hedefleri' tablosunda 'eksik' uyarısı olarak görünür."""
        items = self.pool_list.selectedItems()
        if not items:
            QMessageBox.information(
                self, "Seçim yok",
                "Önce aşağıdaki 'Atanmamış Dersler' listesinden silmek istediğiniz derse tıklayın.",
            )
            return
        block = self._blocks_by_id.get(items[0].data(Qt.UserRole))
        if block is None:
            return
        members = self._block_group(block)
        label = self._group_label(members)
        hours_note = f"\n\n({len(members)} ders saati silinecek.)" if len(members) > 1 else ""
        confirm = QMessageBox.question(
            self, "Silme Onayı",
            f"'{label}' dersi tamamen silinsin mi?{hours_note}",
        )
        if confirm != QMessageBox.Yes:
            return
        for member in members:
            self.db.delete_lesson_block(member.id)
        self.refresh()

    # ---------- ders ekle / oto ata ----------
    def handle_add_lesson(self) -> None:
        dialog = AddLessonDialog(self.db, self)
        if dialog.exec() == AddLessonDialog.Accepted:
            self.refresh()

    def handle_auto_assign(self) -> None:
        result = scheduling.auto_assign(self.db, self.navigator.week_start)
        self.refresh()
        message = f"{result.placed} ders otomatik olarak yerleştirildi."
        if result.warnings:
            message += (
                "\n\nUyarı: Bazı dersler kalıcı olarak yerleştirildi ama başka haftalarda "
                "öğretmenin müsait değil işaretiyle çelişiyor:\n- " + "\n- ".join(result.warnings)
            )
            QMessageBox.warning(self, "Oto Ata", message)
        else:
            QMessageBox.information(self, "Oto Ata", message)
