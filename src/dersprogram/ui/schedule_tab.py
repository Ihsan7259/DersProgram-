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

from PySide6.QtCore import Qt, QMimeData, QRect, QSize, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QDrag, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QStyledItemDelegate,
    QHeaderView,
    QFrame,
    QCheckBox,
    QScrollArea,
    QLayout,
    QAbstractItemView,
    QMessageBox,
    QSplitter,
    QButtonGroup,
    QDialog,
    QMenu,
    QProgressDialog,
)

from ..db import (
    Database,
    LESSON_TYPES,
    TYPE_CLASS,
    TYPE_ONE_ON_ONE,
    TYPE_COACHING,
    TYPE_DEPARTMENT,
    TYPE_PROBLEM_SOLVING,
)
from .. import scheduling
from .widgets import WeekNavigator, ScopeDialog, MiniScheduleGrid
from .add_lesson_dialog import AddLessonDialog
from . import theme

MIME_PREFIX = "lesson-block:"

MODE_CLASS = "class"
MODE_TEACHER = "teacher"


class _CellDelegate(QStyledItemDelegate):
    """MainGrid'in her hücresini (sınıf/öğretmen × gün/saat) çizer.

    Önceden her hücre için ayrı bir QWidget kuruluyordu (setCellWidget) -
    büyük kurumlarda (çok sayıda sınıf/öğretmen × gün×saat) bu, binlerce
    widget'ın her yenilemede sıfırdan oluşturulup silinmesi anlamına
    geliyordu ve Ana Program'ı açarken/yenilerken gözle görülür bir
    takılmaya yol açıyordu. Bunun yerine hücre verisi (payload: bkz.
    ScheduleTab._render_grid) hafif bir QTableWidgetItem'da tutulur, bu
    delegate ise sadece GÖRÜNEN hücreleri QPainter ile çizer - Qt'nin
    item tabanlı tablo render mimarisi widget tabanlıdan çok daha hafiftir.
    """

    def paint(self, painter, option, index) -> None:
        payload = index.data(Qt.UserRole)
        if not payload:
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)
        rect = option.rect

        border_state = payload.get("border_state", "normal")
        if border_state == "valid":
            painter.fillRect(rect, QColor(theme.VALID_BG))
        elif border_state == "invalid":
            painter.fillRect(rect, QColor(theme.CONFLICT_BG))
        else:
            painter.fillRect(rect, QColor(payload.get("bg", theme.APP_BG)))

        if border_state in ("valid", "invalid"):
            pen = QPen(QColor(theme.VALID_BORDER if border_state == "valid" else theme.CONFLICT_BORDER))
            pen.setWidth(2)
            pen.setStyle(Qt.DashLine if border_state == "valid" else Qt.SolidLine)
            painter.setPen(pen)
            painter.drawRect(rect.adjusted(1, 1, -2, -2))

        kind = payload.get("kind")
        if kind == "unavailable":
            font = QFont(painter.font())
            font.setBold(True)
            font.setPointSizeF(10)
            painter.setFont(font)
            painter.setPen(QColor(theme.CONFLICT_BORDER))
            painter.drawText(rect, Qt.AlignCenter, "×")
        elif kind == "chip":
            line1 = payload.get("line1", "")
            line2 = payload.get("line2", "")
            inner = rect.adjusted(2, 1, -2, -1)
            if line2:
                top = QRect(inner.x(), inner.y(), inner.width(), inner.height() // 2)
                bottom = QRect(inner.x(), inner.y() + inner.height() // 2, inner.width(), inner.height() - inner.height() // 2)
            else:
                top, bottom = inner, None

            font1 = QFont(painter.font())
            font1.setBold(True)
            font1.setPointSizeF(6.9)
            painter.setFont(font1)
            painter.setPen(QColor(theme.LESSON_TYPE_TEXT))
            elided1 = QFontMetrics(font1).elidedText(line1, Qt.ElideRight, top.width())
            painter.drawText(top, Qt.AlignHCenter | (Qt.AlignBottom if bottom else Qt.AlignVCenter), elided1)

            if bottom is not None:
                font2 = QFont(painter.font())
                font2.setPointSizeF(6.3)
                painter.setFont(font2)
                painter.setPen(QColor(theme.LESSON_TYPE_TEXT_MUTED))
                elided2 = QFontMetrics(font2).elidedText(line2, Qt.ElideRight, bottom.width())
                painter.drawText(bottom, Qt.AlignHCenter | Qt.AlignTop, elided2)
        painter.restore()


class FlowLayout(QLayout):
    """Öğeleri soldan sağa dizip pencere genişliğine sığmayınca alt satıra
    saran basit bir yerleşim (Qt'nin QHBoxLayout'u sarma desteklemiyor).
    Atanmamış dersler havuzunda her kategorinin kartlarını (bkz. PoolChip)
    genişliğe göre sarıp gruplamak için kullanılır."""

    def __init__(self, parent=None, margin: int = 0, h_spacing: int = 6, v_spacing: int = 6):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items: list = []
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x, y = effective.x(), effective.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_spacing
            if next_x - self._h_spacing > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + self._v_spacing
                next_x = x + hint.width() + self._h_spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + bottom


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


def _pool_dense_lines(rep_block, members: list) -> tuple[str, str]:
    """Havuzdaki bir kart için Ana Program hücreleriyle AYNI iki satırlı
    yoğun etiket (bkz. theme.make_dense_chip) - tür + kiminle olduğu
    bilgisini en kısa şekilde verir, tam bilgi tooltip'te kalır (bkz.
    _group_pool_labels)."""
    teacher_short = scheduling.short_teacher_name(rep_block.teacher_name)
    if rep_block.type == TYPE_DEPARTMENT:
        line1 = rep_block.subject_name or "Zümre"
        line2 = f"{len(members)} hoca" if len(members) > 1 else teacher_short
    elif rep_block.type == TYPE_CLASS:
        line1 = rep_block.subject_name or "Sınıf Dersi"
        line2 = f"{rep_block.class_name} · {teacher_short}" if rep_block.class_name else teacher_short
    elif rep_block.type == TYPE_ONE_ON_ONE:
        line1 = rep_block.subject_name or "Birebir"
        line2 = f"{rep_block.student_name} · {teacher_short}" if rep_block.student_name else teacher_short
    elif rep_block.type == TYPE_COACHING:
        line1 = "Öğrenci Koçluk"
        line2 = f"{rep_block.student_name} · {teacher_short}" if rep_block.student_name else teacher_short
    else:  # TYPE_PROBLEM_SOLVING
        line1 = rep_block.subject_name or "Soru Çözümü"
        line2 = teacher_short
    return line1, line2


class PoolChip(QFrame):
    """Havuzdaki bir dersi, Ana Program ızgarasındaki hücre kartlarıyla
    AYNI görünümde (küçük, renkli, iki satırlı) gösteren, sürüklenip
    ızgaraya bırakılabilen kart. Önceden tek satırlık soluk bir 'hap'
    (pill) görünümündeydi - havuz kalabalıklaşınca ana tablodaki dersle
    aynı derse ait kartı göz ile eşleştirmek zorlaşıyordu."""

    clicked = Signal(int)  # block_id
    delete_requested = Signal()

    _DRAG_THRESHOLD = 6

    def __init__(self, block_id: int, line1: str, line2: str, bg: str, tooltip: str, drag_pixmap_provider, parent=None):
        super().__init__(parent)
        self.block_id = block_id
        self._drag_pixmap_provider = drag_pixmap_provider
        self._drag_start_pos = None
        self._selected = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setToolTip(tooltip)
        self.setFixedSize(66, 40)
        chip_layout = QVBoxLayout(self)
        chip_layout.setContentsMargins(0, 0, 0, 0)
        chip_layout.addWidget(theme.make_dense_chip(line1, line2, bg))
        self._apply_frame_style()

    def _apply_frame_style(self) -> None:
        border = f"2px solid {theme.ACCENT}" if self._selected else "2px solid transparent"
        self.setStyleSheet(f"PoolChip {{ border-radius:5px; border:{border}; }}")

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_frame_style()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self.setFocus()
            self.clicked.emit(self.block_id)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start_pos is None or not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if (pos - self._drag_start_pos).manhattanLength() < self._DRAG_THRESHOLD:
            return
        self._drag_start_pos = None
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(f"{MIME_PREFIX}{self.block_id}")
        drag.setMimeData(mime)
        pixmap = self._drag_pixmap_provider(self.block_id) if self._drag_pixmap_provider else None
        if pixmap is not None and not pixmap.isNull():
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())
        drag.exec(Qt.CopyAction)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_requested.emit()
            return
        super().keyPressEvent(event)


class MainGrid(QTableWidget):
    """Satır = sınıf ya da öğretmen; sütun = gün+saat bileşiği (günler
    en üstte yan yana). Sütunlar pencereye sığacak şekilde otomatik
    daralır, yatay kaydırma kapalıdır - sadece aşağı kaydırılır."""

    row_header_double_clicked = Signal(int)  # entity_id
    row_header_clicked = Signal(int)  # entity_id
    row_header_context_menu_requested = Signal(int, object)  # entity_id, QPoint (global)

    def __init__(self, get_block_by_id, validate_drop, on_drop, on_remove_request, period_time_label=None):
        super().__init__()
        self.setObjectName("mainGrid")
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        # Hücreler arasındaki çizgi artık her hücrenin kendi kenarlığı
        # yerine ızgaranın tek gridline'ı ile çiziliyor - çift kenarlıktan
        # doğan görünür boşluk kalmıyor, hücreler tam bitişik görünüyor.
        self.setShowGrid(True)
        self.setItemDelegate(_CellDelegate(self))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        header = self.horizontalHeader()
        header.setObjectName("mainGridHHeader")
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setMinimumSectionSize(8)
        header.setMinimumHeight(36)
        header.setDefaultAlignment(Qt.AlignCenter)
        # Satır başlıkları (sınıf/öğretmen adları) sütun sıkışmasından
        # bağımsız, hep okunaklı kalsın diye ayrı bir isimle stillenir
        # (bkz. _apply_column_sizing - iki başlığa farklı font boyutu verir).
        self.verticalHeader().setObjectName("mainGridVHeader")
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.verticalHeader().setMinimumWidth(64)
        self.verticalHeader().setDefaultAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.verticalHeader().setSectionsClickable(True)
        self.verticalHeader().sectionDoubleClicked.connect(self._handle_row_header_double_click)
        self.verticalHeader().sectionClicked.connect(self._handle_row_header_click)
        self.verticalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.verticalHeader().customContextMenuRequested.connect(self._handle_row_header_context_menu)
        self._get_block_by_id = get_block_by_id
        self._validate_drop = validate_drop
        self._on_drop = on_drop
        self._on_remove_request = on_remove_request
        self._period_time_label = period_time_label
        self._hover_cell = None
        self._hover_original_state = "normal"
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

        # Gün/saat başlığı (yatay) sütun sıkışmasına göre küçülebilir, ama
        # satır başlığı (sınıf/öğretmen adları - dikey) bundan etkilenmez;
        # okunaklı kalması için hep büyük ve sabit bir fontla gösterilir
        # (ayrı ayrı isimlendirilmiş iki QHeaderView, bkz. __init__).
        if per_column >= 30:
            font_pt, padding = 8.4, 2
        elif per_column >= 22:
            font_pt, padding = 7.6, 1
        elif per_column >= 16:
            font_pt, padding = 6.8, 1
        else:
            font_pt, padding = 6.2, 0
        font_pt *= max(1.0, self._zoom)
        row_font_pt = min(12.5, 9.2 * max(1.0, self._zoom))
        self.setStyleSheet(
            f"#mainGridHHeader::section {{ font-size: {font_pt:.1f}pt; font-weight:700; padding: {padding}px 0; }}"
            f"#mainGridVHeader::section {{ font-size: {row_font_pt:.1f}pt; font-weight:700; padding: 4px 10px; }}"
            f"#mainGrid {{ gridline-color: {theme.INK}; border:none; }}"
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
        if self._period_time_label:
            for col in range(self.columnCount()):
                _day, period = self.col_to_day_period(col)
                time_label = self._period_time_label(period)
                item = self.horizontalHeaderItem(col)
                if item is not None:
                    item.setToolTip(f"{period}. Ders ({time_label})" if time_label else f"{period}. Ders")

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
            item = self.item(row, col)
            if item is not None:
                payload = dict(item.data(Qt.UserRole) or {})
                self._hover_original_state = payload.get("border_state", "normal")
                block_id = int(event.mimeData().text()[len(MIME_PREFIX):])
                block = self._get_block_by_id(block_id)
                entity_id = self.row_to_entity(row)
                day, period = self.col_to_day_period(col)
                valid = block is not None and self._validate_drop(block, entity_id, day, period)
                payload["border_state"] = "valid" if valid else "invalid"
                item.setData(Qt.UserRole, payload)
                self.viewport().update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._restore_hover()
        super().dragLeaveEvent(event)

    def _restore_hover(self) -> None:
        if self._hover_cell is not None:
            row, col = self._hover_cell
            item = self.item(row, col)
            if item is not None:
                payload = dict(item.data(Qt.UserRole) or {})
                payload["border_state"] = self._hover_original_state
                item.setData(Qt.UserRole, payload)
                self.viewport().update()
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

    def _handle_row_header_click(self, row: int) -> None:
        entity_id = self.row_to_entity(row)
        if entity_id is not None:
            self.row_header_clicked.emit(entity_id)

    def _handle_row_header_context_menu(self, pos) -> None:
        row = self.verticalHeader().logicalIndexAt(pos)
        entity_id = self.row_to_entity(row)
        if entity_id is not None:
            global_pos = self.verticalHeader().mapToGlobal(pos)
            self.row_header_context_menu_requested.emit(entity_id, global_pos)


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
        grid.render(db, filtered, row_mode=mode)
        layout.addWidget(grid, 1)

        close_button = QPushButton("Kapat")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)


class _AutoAssignWorker(QThread):
    """Oto Ata'yı (kısıt çözücü, birkaç saniye ila onlarca saniye sürebilir)
    ayrı bir iş parçacığında çalıştırır ki arayüz o sırada donmuş görünmesin
    ve ilerleme yüzdesi canlı güncellenebilsin. ScheduleTab.handle_auto_assign
    bu süre boyunca pencereyi uygulama-geneli modal tutar - bu yüzden ana
    iş parçacığı ile bu iş parçacığı hiçbir zaman aynı anda veritabanına
    yazmaz (bkz. db.py'deki check_same_thread=False notu)."""

    progress = Signal(int, str)
    finished_with_result = Signal(object)  # AutoAssignResult ya da Exception

    def __init__(self, db: Database, week_start, include_types: set[str] | None, parent=None):
        super().__init__(parent)
        self.db = db
        self.week_start = week_start
        self.include_types = include_types

    def run(self) -> None:
        try:
            result = scheduling.auto_assign(
                self.db, self.week_start, include_types=self.include_types,
                progress_callback=lambda pct, msg: self.progress.emit(pct, msg),
            )
        except Exception as exc:  # pragma: no cover - beklenmedik hata
            self.finished_with_result.emit(exc)
            return
        self.finished_with_result.emit(result)


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
        self._selected_row_entity_id: int | None = None
        self._preview_highlighted: list[tuple[int, int]] = []
        self._preview_header_rows: list[int] = []
        self._selected_pool_block_id: int | None = None
        self._pool_chips: dict[int, PoolChip] = {}
        self._last_auto_assign_block_ids: list[int] = []
        self._auto_assign_worker: "_AutoAssignWorker | None" = None
        self._auto_assign_progress_dialog: QProgressDialog | None = None

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
        self.undo_auto_assign_button = QPushButton("  Son Oto Atamayı Geri Al")
        self.undo_auto_assign_button.setObjectName("outlineButton")
        self.undo_auto_assign_button.setVisible(False)
        toolbar.addStretch()
        toolbar.addWidget(self.add_lesson_button)
        toolbar.addWidget(self.auto_assign_button)
        toolbar.addWidget(self.undo_auto_assign_button)
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
            period_time_label=self.db.period_time_label,
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
        self.pool_filter_label = QLabel()
        self.pool_filter_label.setStyleSheet(f"font-size:8.6pt; color:{theme.ACCENT_HOVER}; font-weight:600;")
        pool_header.addWidget(self.pool_filter_label)
        self.pool_filter_clear_button = QPushButton("Filtreyi Temizle")
        self.pool_filter_clear_button.setObjectName("outlineButton")
        self.pool_filter_clear_button.setVisible(False)
        self.pool_filter_clear_button.clicked.connect(self._clear_row_filter)
        pool_header.addWidget(self.pool_filter_clear_button)
        pool_header.addStretch()
        self.pool_delete_button = QPushButton("Seçili Dersi Sil")
        self.pool_delete_button.setObjectName("outlineButton")
        self.pool_delete_button.clicked.connect(self.handle_delete_pool_lesson)
        pool_header.addWidget(self.pool_delete_button)
        pool_layout.addLayout(pool_header)
        self.hint_label = QLabel()
        self.hint_label.setStyleSheet(f"font-size:8.3pt; color:{theme.INK_MUTED_58};")
        pool_layout.addWidget(self.hint_label)

        # Oto Ata'nın hangi ders kategorilerini işleyeceğini seçmek için -
        # havuzdaki kartların kendisi hep tüm kategorileri gösterir, bu
        # onay kutuları sadece "Oto Ata" tıklanınca neyin işleneceğini
        # daraltır (bkz. handle_auto_assign).
        category_row = QHBoxLayout()
        category_row.setSpacing(14)
        category_label = QLabel("Oto Ata kategorileri:")
        category_label.setStyleSheet(f"font-size:8.3pt; color:{theme.INK_MUTED_52}; font-weight:600;")
        category_row.addWidget(category_label)
        self.category_checks: dict[str, QCheckBox] = {}
        for lesson_type in LESSON_TYPES:
            checkbox = QCheckBox(theme.lesson_type_label(lesson_type))
            checkbox.setChecked(True)
            self.category_checks[lesson_type] = checkbox
            category_row.addWidget(checkbox)
        category_row.addStretch()
        pool_layout.addLayout(category_row)

        self.pool_scroll = QScrollArea()
        self.pool_scroll.setWidgetResizable(True)
        self.pool_scroll.setFrameShape(QFrame.NoFrame)
        self.pool_scroll.setStyleSheet(f"QScrollArea {{ background:{theme.APP_BG}; border:none; }}")
        self._pool_content = QWidget()
        self._pool_content.setStyleSheet(f"background:{theme.APP_BG};")
        self._pool_content_layout = QVBoxLayout(self._pool_content)
        self._pool_content_layout.setContentsMargins(2, 2, 2, 2)
        self._pool_content_layout.setSpacing(10)
        self.pool_scroll.setWidget(self._pool_content)
        pool_layout.addWidget(self.pool_scroll)
        splitter.addWidget(pool_container)
        splitter.setSizes([470, 240])

        layout.addWidget(splitter, 1)

        self.add_lesson_button.clicked.connect(self.handle_add_lesson)
        self.auto_assign_button.clicked.connect(self.handle_auto_assign)
        self.undo_auto_assign_button.clicked.connect(self.handle_undo_auto_assign)
        self.navigator.week_changed.connect(lambda _w: self.refresh())
        self.class_mode_button.toggled.connect(self._handle_mode_change)
        self.zoom_in_button.clicked.connect(lambda: self._change_zoom(0.15))
        self.zoom_out_button.clicked.connect(lambda: self._change_zoom(-0.15))
        self.grid.row_header_double_clicked.connect(self._show_row_preview)
        self.grid.row_header_clicked.connect(self._handle_row_header_click)
        self.grid.row_header_context_menu_requested.connect(self._show_row_context_menu)

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
        self._reapply_pool_preview()  # aktif önizleme varsa yeniden uygula

    def _render_drag_pixmap(self, block_id: int):
        """Havuzdan bir ders sürüklenirken imleçle birlikte gösterilecek
        küçük önizleme görüntüsünü üretir - Ana Program'daki hücre kartıyla
        aynı boyut ve görünümde olsun diye (Qt varsayılanı, havuzdaki
        listedeki öğenin tam boyutunda kocaman bir kutu sürüklüyordu)."""
        block = self._blocks_by_id.get(block_id)
        if block is None:
            return None
        members = self._block_group(block)
        rep = min(members, key=lambda b: b.id)
        line1, line2 = rep.dense_lines(self.mode)
        if len(members) > 1:
            line1 = f"{line1} (+{len(members) - 1})"
        bg, _dot = theme.lesson_colors_for(rep, tinted=self.mode == MODE_TEACHER)
        width = self.grid.columnWidth(0) if self.grid.columnCount() else 40
        height = self.grid.row_height()
        chip = theme.make_dense_chip(line1, line2, bg)
        chip.setFixedSize(max(28, width), max(20, height))
        return chip.grab()

    def _show_row_preview(self, entity_id: int) -> None:
        name = next((n for i, n in self._row_entities if i == entity_id), "")
        dialog = RowPreviewDialog(self.db, self.navigator.week_start, self.mode, entity_id, name, self)
        dialog.exec()

    def _show_row_context_menu(self, entity_id: int, global_pos) -> None:
        """Bir sınıf/öğretmen adına sağ tıklanınca: önizleme ya da o
        satırın yerleştirilmiş TÜM derslerini tek seferde 'Atanmamış
        Dersler' havuzuna düşürme seçeneği (müsaitlik ayarlarına dokunmaz,
        sadece ders yerleşimlerini kaldırır)."""
        name = next((n for i, n in self._row_entities if i == entity_id), "")
        menu = QMenu(self)
        preview_action = menu.addAction("Önizleme")
        menu.addSeparator()
        clear_action = menu.addAction("Yerleştirilmiş Dersleri Havuza Düşür")
        chosen = menu.exec(global_pos)
        if chosen == preview_action:
            self._show_row_preview(entity_id)
        elif chosen == clear_action:
            self._clear_row_assignments(entity_id, name)

    def _clear_row_assignments(self, entity_id: int, name: str) -> None:
        matching_blocks = [
            b for blocks in self._schedule.values() for b in blocks if self._row_matches_block(b, entity_id)
        ]
        if not matching_blocks:
            QMessageBox.information(self, "Ders yok", f"{name} için şu anda yerleştirilmiş ders yok.")
            return
        all_members = {}
        for b in matching_blocks:
            for m in self._block_group(b):
                all_members[m.id] = m
        confirm = QMessageBox.question(
            self, "Onay",
            f"{name} için yerleştirilmiş {len(all_members)} ders saatinin tamamı 'Atanmamış Dersler' "
            "havuzuna düşürülsün mü?\n\n(Müsaitlik ayarlarına dokunulmaz, sadece ders yerleşimleri kaldırılır.)",
        )
        if confirm != QMessageBox.Yes:
            return
        dialog = ScopeDialog(self.db, self, f"{name} derslerini kaldırma")
        if dialog.exec() != ScopeDialog.Accepted:
            return
        scope = dialog.scope()
        for block_id in all_members:
            scheduling.clear_block(self.db, self.navigator.week_start, block_id, scope)
        self.refresh()

    def _handle_mode_change(self, checked: bool) -> None:
        self.mode = MODE_CLASS if checked else MODE_TEACHER
        self._selected_row_entity_id = None
        self._update_hint()
        self.refresh()

    # ---------- satır seçimi <-> havuz filtresi / önizleme ----------
    def _handle_row_header_click(self, entity_id: int) -> None:
        self._selected_row_entity_id = None if self._selected_row_entity_id == entity_id else entity_id
        self._render_pool()

    def _clear_row_filter(self) -> None:
        self._selected_row_entity_id = None
        self._render_pool()

    def _handle_pool_chip_clicked(self, block_id: int) -> None:
        if self._selected_pool_block_id == block_id:
            return
        previous = self._pool_chips.get(self._selected_pool_block_id)
        if previous is not None:
            previous.set_selected(False)
        self._selected_pool_block_id = block_id
        chip = self._pool_chips.get(block_id)
        if chip is not None:
            chip.set_selected(True)
        self._clear_row_preview()
        block = self._blocks_by_id.get(block_id)
        if block is not None:
            self._apply_row_preview(block)

    def _reapply_pool_preview(self) -> None:
        if self._selected_pool_block_id is None:
            return
        block = self._blocks_by_id.get(self._selected_pool_block_id)
        if block is not None:
            self._apply_row_preview(block)

    def _apply_row_preview(self, block) -> None:
        """Havuzdan bir ders seçilince, sürüklemeden önce o dersin ait
        olduğu satırı vurgular: uygun hücreler yeşil, uygun olmayanlar
        kırmızı görünür (bkz. MainGrid.dragMoveEvent - aynı mantık).
        Izgarayı baştan kurmadan, sadece ilgili hücrelerin durumunu
        değiştirir - büyük programlarda her seçimde yüzlerce hücreyi
        yeniden oluşturmak takılmalara yol açıyordu (bkz. _clear_row_preview)."""
        for row_index, (entity_id, _name) in enumerate(self._row_entities):
            if not self._row_matches_block(block, entity_id):
                continue
            header_item = self.grid.verticalHeaderItem(row_index)
            if header_item is not None:
                header_item.setBackground(QColor(theme.ACCENT_SOFT_BG))
                self._preview_header_rows.append(row_index)
            for col in range(self.grid.columnCount()):
                item = self.grid.item(row_index, col)
                if item is None:
                    continue
                day, period = self.grid.col_to_day_period(col)
                valid = self._validate_drop(block, entity_id, day, period)
                payload = dict(item.data(Qt.UserRole) or {})
                payload["border_state"] = "valid" if valid else "invalid"
                item.setData(Qt.UserRole, payload)
                self._preview_highlighted.append((row_index, col))
        self.grid.viewport().update()

    def _clear_row_preview(self) -> None:
        """_apply_row_preview ile boyanan hücreleri/satır başlığını,
        ızgarayı yeniden kurmadan gerçek (normal) görünümüne döndürür."""
        for row_index, col in self._preview_highlighted:
            item = self.grid.item(row_index, col)
            if item is not None:
                payload = dict(item.data(Qt.UserRole) or {})
                payload["border_state"] = "normal"
                item.setData(Qt.UserRole, payload)
        self._preview_highlighted = []
        for row_index in self._preview_header_rows:
            header_item = self.grid.verticalHeaderItem(row_index)
            if header_item is not None:
                header_item.setBackground(QBrush())
        self._preview_header_rows = []
        self.grid.viewport().update()

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

        # Havuzdan seçilen bir dersin önizleme vurgusu (bkz. _apply_row_preview)
        # bu hücreleri geçici olarak boyar; ızgara sıfırdan kurulduğunda o
        # vurgu artık geçersiz - takip listesini de sıfırlıyoruz.
        self._preview_highlighted = []
        self._preview_header_rows = []

        for row, (entity_id, _name) in enumerate(self._row_entities):
            self.grid.setRowHeight(row, self.grid.row_height())
            for day in range(len(day_names)):
                for period in range(1, period_count + 1):
                    col = day * period_count + (period - 1)
                    blocks = self._cell_blocks(entity_id, day, period)
                    if not blocks:
                        if self.mode == MODE_TEACHER and (entity_id, day, period) in self._unavailable.teacher:
                            payload = {"kind": "unavailable", "bg": theme.CONFLICT_BG}
                            tooltip = "Öğretmen bu saatte müsait değil olarak işaretlenmiş"
                        elif self.mode == MODE_CLASS and (entity_id, day, period) in self._unavailable.class_:
                            payload = {"kind": "unavailable", "bg": theme.CONFLICT_BG}
                            tooltip = "Sınıf bu saatte müsait değil olarak işaretlenmiş"
                        else:
                            payload = {"kind": "empty", "bg": theme.APP_BG}
                            tooltip = ""
                    else:
                        line1, line2 = blocks[0].dense_lines(self.mode)
                        bg, _dot = theme.lesson_colors_for(blocks[0], tinted=self.mode == MODE_TEACHER)
                        if len(blocks) > 1:
                            line1 = f"{line1} (+{len(blocks) - 1})"
                        payload = {"kind": "chip", "bg": bg, "line1": line1, "line2": line2}
                        tooltip = f"{line1}\n{line2}" if line2 else line1
                    payload["border_state"] = "normal"

                    item = self.grid.item(row, col)
                    if item is None:
                        item = QTableWidgetItem()
                        self.grid.setItem(row, col, item)
                    item.setData(Qt.UserRole, payload)
                    item.setToolTip(tooltip)

    def _grouped_pool_items(self, blocks: list) -> list[tuple]:
        """Havuzdaki blokları (rep_block, members) çiftlerine indirger -
        zümre grubundaki bloklar tek bir kart olarak (bkz. _group_members),
        diğer her blok kendi başına."""
        seen_groups: set[int] = set()
        items: list[tuple] = []
        for block in blocks:
            if block.zumre_group_id is not None:
                if block.zumre_group_id in seen_groups:
                    continue
                seen_groups.add(block.zumre_group_id)
                members = self._group_members(block.zumre_group_id)
                rep = min(members, key=lambda b: b.id)
                items.append((rep, members))
            else:
                items.append((block, [block]))
        return items

    def _clear_pool_content(self) -> None:
        while self._pool_content_layout.count():
            child = self._pool_content_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                sub_layout = child.layout()
                if sub_layout is not None:
                    sub_layout.deleteLater()
        self._pool_chips = {}

    def _render_pool(self) -> None:
        all_items = self._grouped_pool_items(self._pool)

        # Kategori onay kutularının sayaçları HER ZAMAN tüm havuza göre
        # (satır filtresinden bağımsız) güncellenir - Oto Ata, ekrandaki
        # satır filtresine değil bu onay kutularına bakar.
        counts_by_type: dict[str, int] = {t: 0 for t in LESSON_TYPES}
        for rep, _members in all_items:
            counts_by_type[rep.type] = counts_by_type.get(rep.type, 0) + 1
        for lesson_type, checkbox in self.category_checks.items():
            count = counts_by_type.get(lesson_type, 0)
            checkbox.setText(f"{theme.lesson_type_label(lesson_type)} ({count})")

        pool_items = all_items
        if self._selected_row_entity_id is not None:
            pool_items = [
                (rep, members) for rep, members in pool_items
                if any(self._row_matches_block(m, self._selected_row_entity_id) for m in members)
            ]
            entity_name = next(
                (n for i, n in self._row_entities if i == self._selected_row_entity_id), ""
            )
            self.pool_filter_label.setText(f"— Filtre: {entity_name}")
            self.pool_filter_clear_button.setVisible(True)
        else:
            self.pool_filter_label.setText("")
            self.pool_filter_clear_button.setVisible(False)
        self.pool_label.setText(f"Atanmamış Dersler ({len(pool_items)})")

        # Seçili kart artık (yerleştirildi/silindi/filtrelendi diye)
        # havuzda yoksa seçim geçersiz kalır.
        visible_ids = {rep.id for rep, _members in pool_items}
        if self._selected_pool_block_id not in visible_ids:
            self._selected_pool_block_id = None

        self._clear_pool_content()

        if not pool_items:
            empty_text = (
                "Bu satır için atanmamış ders yok." if self._selected_row_entity_id is not None
                else "Atanmamış ders yok."
            )
            empty_label = QLabel(empty_text)
            empty_label.setStyleSheet(f"font-size:9pt; color:{theme.INK_MUTED_58}; padding:4px 0;")
            self._pool_content_layout.addWidget(empty_label)

        by_type: dict[str, list[tuple]] = {}
        for rep, members in pool_items:
            by_type.setdefault(rep.type, []).append((rep, members))

        for lesson_type in LESSON_TYPES:
            items = by_type.get(lesson_type)
            if not items:
                continue
            section_header = QLabel(f"{theme.lesson_type_label(lesson_type)} ({len(items)})")
            section_header.setStyleSheet(
                f"font-size:8.6pt; font-weight:700; color:{theme.INK_MUTED_52}; "
                f"padding-top:4px; border-top:1px solid {theme.BORDER_SUBTLE};"
            )
            self._pool_content_layout.addWidget(section_header)

            flow_container = QWidget()
            FlowLayout(flow_container, margin=0, h_spacing=6, v_spacing=6)
            for rep, members in sorted(items, key=lambda pair: pair[0].pool_label()):
                line1, line2 = _pool_dense_lines(rep, members)
                bg, _dot = theme.lesson_colors_for(rep)
                _short, full_text = _group_pool_labels(rep, members)
                chip = PoolChip(rep.id, line1, line2, bg, full_text, self._render_drag_pixmap, flow_container)
                chip.clicked.connect(self._handle_pool_chip_clicked)
                chip.delete_requested.connect(self.handle_delete_pool_lesson)
                chip.set_selected(rep.id == self._selected_pool_block_id)
                self._pool_chips[rep.id] = chip
                flow_container.layout().addWidget(chip)
            self._pool_content_layout.addWidget(flow_container)

        self._pool_content_layout.addStretch()

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
        if self._selected_pool_block_id is None:
            QMessageBox.information(
                self, "Seçim yok",
                "Önce aşağıdaki 'Atanmamış Dersler' listesinden silmek istediğiniz derse tıklayın.",
            )
            return
        block = self._blocks_by_id.get(self._selected_pool_block_id)
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
        self._selected_pool_block_id = None
        self.refresh()

    # ---------- ders ekle / oto ata ----------
    def handle_add_lesson(self) -> None:
        dialog = AddLessonDialog(self.db, self)
        if dialog.exec() == AddLessonDialog.Accepted:
            self.refresh()

    def handle_auto_assign(self) -> None:
        # Kısıt çözücü (bkz. scheduling.auto_assign) çok sayıda öğretmen/
        # sınıfta birkaç saniyeden onlarca saniyeye kadar sürebilir; arayüz
        # o sırada donmuş görünmesin ve ilerleme yüzdesi görülebilsin diye
        # ayrı bir iş parçacığında çalıştırılıyor. Pencere bu süre boyunca
        # UYGULAMA GENELİNDE modal (bkz. setWindowModality altında) - hem
        # kullanıcının yarım kalmış bir işlemi görmesini engeller hem de
        # arka plan iş parçacığıyla veritabanına aynı anda erişilmesini
        # önler (bkz. db.py'deki check_same_thread=False notu).
        selected_types = {t for t, checkbox in self.category_checks.items() if checkbox.isChecked()}
        if not selected_types:
            QMessageBox.information(
                self, "Kategori seçin",
                "Oto Ata çalıştırmak için en az bir ders kategorisi seçili olmalı "
                "(havuzun üstündeki 'Oto Ata kategorileri' onay kutularından).",
            )
            return
        include_types = None if selected_types == set(LESSON_TYPES) else selected_types

        self.auto_assign_button.setEnabled(False)
        self.undo_auto_assign_button.setVisible(False)

        progress_dialog = QProgressDialog("Program hesaplanıyor...", None, 0, 100, self)
        progress_dialog.setWindowTitle("Oto Ata")
        progress_dialog.setWindowModality(Qt.ApplicationModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setCancelButton(None)
        progress_dialog.setAutoClose(False)
        progress_dialog.setValue(0)
        self._auto_assign_progress_dialog = progress_dialog

        worker = _AutoAssignWorker(self.db, self.navigator.week_start, include_types, self)
        worker.progress.connect(self._handle_auto_assign_progress)
        worker.finished_with_result.connect(self._handle_auto_assign_finished)
        self._auto_assign_worker = worker
        worker.start()
        progress_dialog.show()

    def _handle_auto_assign_progress(self, pct: int, msg: str) -> None:
        dialog = self._auto_assign_progress_dialog
        if dialog is None:
            return
        # QProgressDialog.setValue() modal iken içeride kendi processEvents()
        # çağrısını yapar - bu, henüz bu fonksiyondan çıkmadan
        # _handle_auto_assign_finished'ın araya girip diyaloğu kapatıp
        # self._auto_assign_progress_dialog'u None yapmasına yol açabilir.
        # Bu yüzden referansı yerelde tutup setValue'yu EN SON çağırıyoruz -
        # sonrasında self._auto_assign_progress_dialog'a bir daha dokunmuyoruz.
        dialog.setLabelText(msg)
        dialog.setValue(pct)

    def _handle_auto_assign_finished(self, result_or_exc) -> None:
        worker = self._auto_assign_worker
        if self._auto_assign_progress_dialog is not None:
            self._auto_assign_progress_dialog.close()
            self._auto_assign_progress_dialog = None
        self.auto_assign_button.setEnabled(True)
        self._auto_assign_worker = None

        if isinstance(result_or_exc, Exception):
            QMessageBox.critical(self, "Oto Ata", f"Oto Ata sırasında bir hata oluştu:\n{result_or_exc}")
            return

        result = result_or_exc
        self.refresh()
        self._last_auto_assign_block_ids = result.placed_block_ids
        self.undo_auto_assign_button.setVisible(bool(result.placed_block_ids))

        message = f"{result.placed} ders otomatik olarak yerleştirildi."
        if worker is not None and worker.include_types is not None:
            names = ", ".join(theme.lesson_type_label(t) for t in LESSON_TYPES if t in worker.include_types)
            message += f"\n\n(Sadece seçili kategoriler işlendi: {names})"
        if result.placed_block_ids:
            message += "\n\nBeğenmezseniz 'Son Oto Atamayı Geri Al' ile tamamını havuza geri alabilirsiniz."
        if result.warnings:
            message += (
                "\n\nUyarı: Bazı dersler kalıcı olarak yerleştirildi ama başka haftalarda "
                "öğretmenin müsait değil işaretiyle çelişiyor:\n- " + "\n- ".join(result.warnings)
            )
            QMessageBox.warning(self, "Oto Ata", message)
        else:
            QMessageBox.information(self, "Oto Ata", message)

    def handle_undo_auto_assign(self) -> None:
        block_ids = self._last_auto_assign_block_ids
        if not block_ids:
            return
        confirm = QMessageBox.question(
            self, "Geri Al",
            f"Son Oto Ata ile yerleştirilen {len(block_ids)} ders saati 'Atanmamış Dersler' "
            "havuzuna geri alınsın mı?",
        )
        if confirm != QMessageBox.Yes:
            return
        for block_id in block_ids:
            scheduling.clear_block(self.db, self.navigator.week_start, block_id, scheduling.SCOPE_ALWAYS)
        self._last_auto_assign_block_ids = []
        self.undo_auto_assign_button.setVisible(False)
        self.refresh()
