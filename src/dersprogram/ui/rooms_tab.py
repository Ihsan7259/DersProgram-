"""Derslikler sekmesi: solda derslik tanımları (ekle/güncelle/sil), sağda
SEÇİLİ DERSLİĞİN haftalık programı ve tüm dersliklerin doluluk takibi.

Sınıfların/öğretmenlerin/derslerin programında olduğu gibi Kopyala ve PDF
düğmeleri burada da var (aynı _render_row_pixmap çıktısı). Ek olarak,
kullanıcı isteği "hangi dersliğin ne kadar kullanıldığını takip etmek
istiyoruz" için altta tüm dersliklerin o haftaki doluluk tablosu
(dolu/boş saat ve yüzde) bulunur - bkz. scheduling.room_usage_for_week.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import Qt

from ..db import Database
from .. import scheduling
from .list_tab import ListTab
from .widgets import (
    WeekNavigator,
    MiniScheduleGrid,
    SummaryTable,
    section_title as _section_title,
    divider as _divider,
)
from .schedule_tab import copy_table_as_image, export_table_as_pdf, sanitize_filename
from . import theme

ROW_MODE_ROOM = "room"


class RoomUsageTable(QTableWidget):
    """Tüm dersliklerin o haftaki doluluk tablosu: dolu saat, boş saat ve
    doluluk yüzdesi. En çok kullanılan derslik en üstte."""

    def __init__(self):
        super().__init__()
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Derslik", "Dolu Saat", "Boş Saat", "Doluluk", "Ders Sayısı"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self._room_ids: list[int] = []

    def render(self, rows: list[dict]) -> None:
        self._room_ids = [row["id"] for row in rows]
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.setItem(r, 0, QTableWidgetItem(row["name"]))
            for col, value in enumerate(
                [f"{row['used']} / {row['total']}", str(row["free"]),
                 f"%{row['percent']:g}", str(row["blocks"])], start=1,
            ):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                self.setItem(r, col, item)

    def room_id_at(self, row: int) -> int | None:
        if 0 <= row < len(self._room_ids):
            return self._room_ids[row]
        return None


class RoomsTab(QWidget):
    def __init__(self, db: Database, on_change=None):
        super().__init__()
        self.db = db
        self.on_change = on_change

        root_layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)

        # Sol taraf: derslik CRUD ekranı - ortak ListTab bileşeni aynen
        # kullanılır (ekleme/güncelleme/silme mantığı tek yerde kalsın).
        self.list_tab = ListTab(db, "rooms", "Derslik", on_change=self._handle_list_changed)
        self.list_tab.table_widget.itemSelectionChanged.connect(self.refresh_detail)
        splitter.addWidget(self.list_tab)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.detail_title = _section_title("Dersliğin Haftalık Programı")
        right_layout.addWidget(self.detail_title)
        self.hint_label = QLabel(
            "Soldan bir derslik seçin: o dersliğin bu haftaki programı aşağıda "
            "görünür. Her hücrede dersliği o saatte kimin kullandığı (sınıf ya "
            "da öğrenci), hangi ders ve hangi öğretmen olduğu yazar."
        )
        self.hint_label.setWordWrap(True)
        right_layout.addWidget(self.hint_label)

        self.navigator = WeekNavigator(lambda: len(self.db.day_names))
        self.navigator.week_changed.connect(lambda _w: self.refresh_detail())
        right_layout.addWidget(self.navigator)

        self.grid = MiniScheduleGrid()
        self.grid.setMinimumHeight(240)
        right_layout.addWidget(self.grid, 1)

        button_row = QHBoxLayout()
        self.copy_button = QPushButton("  Kopyala")
        self.copy_button.setObjectName("outlineButton")
        self.copy_button.setIcon(theme.icon(theme.NAV_ICONS["copy"], theme.ACCENT_HOVER))
        self.copy_button.setToolTip("Bu dersliğin haftalık programını, başlığıyla birlikte görsel olarak panoya kopyalar.")
        self.copy_button.clicked.connect(self.handle_copy)
        button_row.addWidget(self.copy_button)
        self.pdf_button = QPushButton("  PDF")
        self.pdf_button.setObjectName("outlineButton")
        self.pdf_button.setIcon(theme.icon(theme.NAV_ICONS["document"], theme.ACCENT_HOVER))
        self.pdf_button.setToolTip("Bu dersliğin haftalık programını PDF dosyası olarak kaydeder.")
        self.pdf_button.clicked.connect(self.handle_export_pdf)
        button_row.addWidget(self.pdf_button)
        button_row.addStretch()
        right_layout.addLayout(button_row)

        right_layout.addWidget(_divider())
        right_layout.addWidget(_section_title("Bu dersliğin haftalık özeti"))
        self.summary_table = SummaryTable()
        self.summary_table.setMaximumHeight(120)
        right_layout.addWidget(self.summary_table)

        right_layout.addWidget(_divider())
        right_layout.addWidget(_section_title("Derslik kullanımı (bu hafta)"))
        usage_hint = QLabel(
            "Hangi dersliğin ne kadar kullanıldığı. 'Dolu Saat', o derslikte "
            "ders olan gün/saat gözlerinin sayısıdır; en çok kullanılan derslik "
            "en üsttedir. Bir satıra tıklayarak o dersliğin programına geçebilirsiniz."
        )
        usage_hint.setWordWrap(True)
        right_layout.addWidget(usage_hint)
        self.usage_table = RoomUsageTable()
        self.usage_table.setMaximumHeight(180)
        self.usage_table.cellClicked.connect(self._handle_usage_row_clicked)
        right_layout.addWidget(self.usage_table)

        splitter.addWidget(right)
        splitter.setSizes([460, 760])
        root_layout.addWidget(splitter)

        self.refresh_detail()

    # ---------- ortak erişim (MainWindow ve diğer sekmeler için) ----------
    @property
    def selected_id(self) -> int | None:
        return self.list_tab.selected_id

    def refresh(self) -> None:
        self.list_tab.refresh()
        self.refresh_detail()

    def _handle_list_changed(self) -> None:
        self.refresh_detail()
        if self.on_change:
            self.on_change()

    # ---------- seçili dersliğin haftalık programı ----------
    def _room_name(self) -> str:
        room_id = self.selected_id
        if room_id is None:
            return ""
        for row in self.db.list_rows("rooms"):
            if row["id"] == room_id:
                return row["name"]
        return ""

    def _week_blocks(self) -> dict[tuple[int, int], list]:
        room_id = self.selected_id
        if room_id is None:
            return {}
        schedule, _pool = scheduling.get_week_view(self.db, self.navigator.week_start)
        filtered: dict[tuple[int, int], list] = {}
        for cell, blocks in schedule.items():
            matched = [b for b in blocks if b.room_id == room_id]
            if matched:
                filtered[cell] = matched
        return filtered

    def refresh_detail(self) -> None:
        name = self._room_name()
        self.detail_title.setText(
            f"{name} - Haftalık Program" if name else "Dersliğin Haftalık Programı"
        )
        room_id = self.selected_id
        has_selection = room_id is not None
        self.copy_button.setEnabled(has_selection)
        self.pdf_button.setEnabled(has_selection)

        # Doluluk tablosu seçimden bağımsızdır - her zaman TÜM derslikleri
        # gösterir (takip amacı).
        self.usage_table.render(scheduling.room_usage_for_week(self.db, self.navigator.week_start))

        if not has_selection:
            self.grid.populate(self.db, {}, row_mode=ROW_MODE_ROOM)
            self.summary_table.render({})
            return

        filtered = self._week_blocks()
        self.grid.populate(self.db, filtered, row_mode=ROW_MODE_ROOM)

        totals: dict[str, int] = {}
        for blocks in filtered.values():
            for block in blocks:
                totals[block.type] = totals.get(block.type, 0) + 1
        self.summary_table.render(totals)

    def _handle_usage_row_clicked(self, row: int, _col: int) -> None:
        """Doluluk tablosundan bir dersliğe tıklayınca soldaki listede o
        derslik seçilir - programı hemen üstte açılır."""
        room_id = self.usage_table.room_id_at(row)
        if room_id is None:
            return
        self.list_tab.select_id(room_id)

    # ---------- Kopyala / PDF ----------
    def _week_text(self) -> str:
        return scheduling.week_label(self.navigator.week_start, len(self.db.day_names))

    def handle_copy(self) -> None:
        name = self._room_name()
        if not name:
            return
        copy_table_as_image(self, self.grid, name, self._week_text())

    def handle_export_pdf(self) -> None:
        name = self._room_name()
        if not name:
            return
        export_table_as_pdf(
            self, self.grid, f"{sanitize_filename(name)}_haftalik_program.pdf", name, self._week_text(),
        )
