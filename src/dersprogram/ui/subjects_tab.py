"""Dersler sekmesi: solda ders/branş tanımları (ekle/güncelle/sil), sağda
SEÇİLİ DERSİN haftalık programı.

Bir dersin (ör. Matematik) haftalık programı, o dersi o gün/saatte veren
TÜM öğretmenleri aynı hücrede alt alta gösterir - "matematik adına
pazartesi 3 saat ders varsa o hocaların isimleri aynı ders bloğunda alt
alta" (kullanıcı isteği). Sınıfların/öğretmenlerin programında olduğu gibi
Kopyala ve PDF düğmeleri de burada. Ayrıca dersin programda hangi renkle
görüneceği buradan elle seçilebilir (bkz. theme.lesson_colors_for).
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QPushButton,
)
from PySide6.QtCore import Qt

from ..db import Database
from .. import scheduling
from .list_tab import ListTab
from .widgets import (
    WeekNavigator,
    MiniScheduleGrid,
    SummaryTable,
    ColorPickButton,
    section_title as _section_title,
    divider as _divider,
)
from .schedule_tab import copy_table_as_image, export_table_as_pdf, sanitize_filename
from . import theme

ROW_MODE_SUBJECT = "subject"


class SubjectsTab(QWidget):
    def __init__(self, db: Database, on_change=None):
        super().__init__()
        self.db = db
        self.on_change = on_change

        root_layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)

        # Sol taraf: ders/branş CRUD ekranı - ortak ListTab bileşeni aynen
        # kullanılır (ekleme/güncelleme/silme mantığı tek yerde kalsın).
        self.list_tab = ListTab(db, "subjects", "Ders/Branş", on_change=self._handle_list_changed)
        self.list_tab.table_widget.itemSelectionChanged.connect(self.refresh_detail)
        splitter.addWidget(self.list_tab)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.detail_title = _section_title("Dersin Haftalık Programı")
        right_layout.addWidget(self.detail_title)
        self.hint_label = QLabel(
            "Soldan bir ders seçin: o dersin bu haftaki programı aşağıda görünür. "
            "Aynı gün/saatte o dersi veren birden fazla öğretmen varsa hepsi aynı "
            "hücrede alt alta sıralanır."
        )
        self.hint_label.setWordWrap(True)
        right_layout.addWidget(self.hint_label)

        self.navigator = WeekNavigator(lambda: len(self.db.day_names))
        self.navigator.week_changed.connect(lambda _w: self.refresh_detail())
        right_layout.addWidget(self.navigator)

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Bu dersin rengi:"))
        self.color_button = ColorPickButton("Ders rengi")
        self.color_button.color_changed.connect(self._handle_color_changed)
        color_row.addWidget(self.color_button)
        color_row.addWidget(QLabel(
            "(Bu dersin sınıf/birebir/soru çözümü derslerinde kullanılır; "
            "ders tipi renginin önüne geçer.)"
        ))
        color_row.addStretch()
        right_layout.addLayout(color_row)

        self.grid = MiniScheduleGrid()
        right_layout.addWidget(self.grid, 1)

        button_row = QHBoxLayout()
        self.copy_button = QPushButton("  Kopyala")
        self.copy_button.setObjectName("outlineButton")
        self.copy_button.setIcon(theme.icon(theme.NAV_ICONS["copy"], theme.ACCENT_HOVER))
        self.copy_button.setToolTip("Bu dersin haftalık programını, başlığıyla birlikte görsel olarak panoya kopyalar.")
        self.copy_button.clicked.connect(self.handle_copy)
        button_row.addWidget(self.copy_button)
        self.pdf_button = QPushButton("  PDF")
        self.pdf_button.setObjectName("outlineButton")
        self.pdf_button.setIcon(theme.icon(theme.NAV_ICONS["document"], theme.ACCENT_HOVER))
        self.pdf_button.setToolTip("Bu dersin haftalık programını PDF dosyası olarak kaydeder.")
        self.pdf_button.clicked.connect(self.handle_export_pdf)
        button_row.addWidget(self.pdf_button)
        button_row.addStretch()
        right_layout.addLayout(button_row)

        right_layout.addWidget(_divider())
        right_layout.addWidget(_section_title("Haftalık özet"))
        self.summary_table = SummaryTable()
        self.summary_table.setMaximumHeight(160)
        right_layout.addWidget(self.summary_table)

        splitter.addWidget(right)
        splitter.setSizes([520, 700])
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

    # ---------- seçili dersin haftalık programı ----------
    def _subject_name(self) -> str:
        subject_id = self.selected_id
        if subject_id is None:
            return ""
        for row in self.db.list_rows("subjects"):
            if row["id"] == subject_id:
                return row["name"]
        return ""

    def _week_blocks(self) -> dict[tuple[int, int], list]:
        subject_id = self.selected_id
        if subject_id is None:
            return {}
        schedule, _pool = scheduling.get_week_view(self.db, self.navigator.week_start)
        filtered: dict[tuple[int, int], list] = {}
        for cell, blocks in schedule.items():
            matched = [b for b in blocks if b.subject_id == subject_id]
            if matched:
                filtered[cell] = matched
        return filtered

    def refresh_detail(self) -> None:
        name = self._subject_name()
        self.detail_title.setText(
            f"{name} - Haftalık Program" if name else "Dersin Haftalık Programı"
        )
        subject_id = self.selected_id
        has_selection = subject_id is not None
        self.color_button.setEnabled(has_selection)
        self.copy_button.setEnabled(has_selection)
        self.pdf_button.setEnabled(has_selection)
        if not has_selection:
            self.color_button.set_color(None)
            self.grid.populate(self.db, {}, row_mode=ROW_MODE_SUBJECT)
            self.summary_table.render({})
            return

        default_bg, _dot = theme.auto_subject_colors(subject_id)
        self.color_button.set_color(self.db.get_subject_color(subject_id), default_preview=default_bg)

        filtered = self._week_blocks()
        self.grid.populate(self.db, filtered, row_mode=ROW_MODE_SUBJECT)

        totals: dict[str, int] = {}
        for blocks in filtered.values():
            for block in blocks:
                totals[block.type] = totals.get(block.type, 0) + 1
        self.summary_table.render(totals)

    def _handle_color_changed(self, color: str | None) -> None:
        subject_id = self.selected_id
        if subject_id is None:
            return
        self.db.set_subject_color(subject_id, color)
        theme.load_color_overrides(self.db)
        self.refresh_detail()
        if self.on_change:
            self.on_change()

    # ---------- Kopyala / PDF ----------
    def _week_text(self) -> str:
        return scheduling.week_label(self.navigator.week_start, len(self.db.day_names))

    def handle_copy(self) -> None:
        name = self._subject_name()
        if not name:
            return
        copy_table_as_image(self, self.grid, name, self._week_text())

    def handle_export_pdf(self) -> None:
        name = self._subject_name()
        if not name:
            return
        export_table_as_pdf(
            self, self.grid, f"{sanitize_filename(name)}_haftalik_program.pdf", name, self._week_text(),
        )
