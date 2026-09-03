"""Öğretmen/Öğrenci/Sınıf/Ana Program sekmelerinde ortak kullanılan
küçük bileşenler: hafta gezinme çubuğu, salt-okunur mini program
tablosu, özet (saat) tablosu, kapsam seçim diyaloğu."""
from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QDialogButtonBox,
    QRadioButton,
)

from ..db import Database, LESSON_TYPE_LABELS
from .. import scheduling
from . import theme


class WeekNavigator(QWidget):
    week_changed = Signal(object)  # _dt.date (o haftanın pazartesisi)

    def __init__(self, day_count_provider):
        super().__init__()
        self._day_count_provider = day_count_provider
        self.week_start = scheduling.monday_of(_dt.date.today())

        container = QHBoxLayout(self)
        container.setContentsMargins(0, 0, 0, 0)
        bar = QWidget()
        bar.setObjectName("navBar")
        bar.setStyleSheet(
            f"#navBar {{ background:{theme.SURFACE}; border:1px solid {theme.BORDER_SUBTLE}; border-radius:11px; }}"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)

        icon_btn_style = (
            f"QPushButton {{ border:1px solid {theme.BORDER_INPUT}; border-radius:8px; "
            f"background:{theme.SURFACE}; padding:5px; }}"
            f"QPushButton:hover {{ background:{theme.APP_BG}; }}"
        )

        self.prev_button = QPushButton()
        self.prev_button.setIcon(theme.icon(theme.NAV_ICONS["prev"], theme.INK_MUTED_38, 13))
        self.prev_button.setFixedSize(28, 28)
        self.prev_button.setStyleSheet(icon_btn_style)

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setMinimumWidth(190)
        self.label.setStyleSheet(
            f"font-family:'{theme.FONT_HEADING}'; font-weight:700; font-size:9.8pt; color:{theme.INK_MUTED_30};"
        )

        self.next_button = QPushButton()
        self.next_button.setIcon(theme.icon(theme.NAV_ICONS["next"], theme.INK_MUTED_38, 13))
        self.next_button.setFixedSize(28, 28)
        self.next_button.setStyleSheet(icon_btn_style)

        self.today_button = QPushButton("Bu Hafta")
        self.today_button.setStyleSheet(
            f"QPushButton {{ border:1px solid {theme.BORDER_INPUT}; border-radius:8px; "
            f"background:{theme.SURFACE}; padding:6px 12px; font-size:9pt; font-weight:600; color:{theme.INK_MUTED_38}; }}"
            f"QPushButton:hover {{ background:{theme.APP_BG}; }}"
        )

        layout.addWidget(self.prev_button)
        layout.addWidget(self.label)
        layout.addWidget(self.next_button)
        layout.addSpacing(6)
        layout.addWidget(self.today_button)
        layout.addStretch()
        container.addWidget(bar)

        self.prev_button.clicked.connect(self.go_prev)
        self.next_button.clicked.connect(self.go_next)
        self.today_button.clicked.connect(self.go_today)

        self._refresh_label()

    def _refresh_label(self) -> None:
        self.label.setText(scheduling.week_label(self.week_start, self._day_count_provider()))

    def go_prev(self) -> None:
        self.week_start -= _dt.timedelta(days=7)
        self._refresh_label()
        self.week_changed.emit(self.week_start)

    def go_next(self) -> None:
        self.week_start += _dt.timedelta(days=7)
        self._refresh_label()
        self.week_changed.emit(self.week_start)

    def go_today(self) -> None:
        self.week_start = scheduling.monday_of(_dt.date.today())
        self._refresh_label()
        self.week_changed.emit(self.week_start)

    def set_week(self, week_start: _dt.date, emit: bool = True) -> None:
        """Haftayı programatik olarak (kullanıcı tıklamadan) değiştirir -
        sekmeler arasında tek bir 'şu an bakılan hafta' durumunu
        senkronize tutmak için kullanılır (bkz. MainWindow)."""
        if week_start == self.week_start:
            return
        self.week_start = week_start
        self._refresh_label()
        if emit:
            self.week_changed.emit(self.week_start)


class MiniScheduleGrid(QTableWidget):
    """Salt okunur, filtrelenmiş (tek kişi/sınıfa ait) haftalık ızgara."""

    def __init__(self):
        super().__init__()
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setShowGrid(False)

    def render(self, db: Database, blocks_by_cell: dict[tuple[int, int], list]) -> None:
        day_names = db.day_names
        period_count = db.period_count
        self.setRowCount(period_count)
        self.setColumnCount(len(day_names))
        self.setHorizontalHeaderLabels(day_names)
        self.setVerticalHeaderLabels([f"{p}." for p in range(1, period_count + 1)])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        for period in range(1, period_count + 1):
            self.setRowHeight(period - 1, 40)
            for day in range(len(day_names)):
                blocks = blocks_by_cell.get((day, period), [])
                self.setCellWidget(period - 1, day, theme.make_multi_cell(blocks, compact=True))


class AvailabilityGrid(QTableWidget):
    """Bir öğretmenin haftalık müsaitlik durumunu düzenlemek için
    tıklanabilir ızgara. Zaten ders atanmış hücreler (ders kartı gösterilir)
    tıklanamaz. Boş hücrelere tıklamak durumu döngüsel değiştirir:
    boş -> müsait (yeşil) -> müsait değil (kırmızı) -> boş. Gün başlığına
    (üstte) tıklamak o günün tümünü, saat başlığına (solda) tıklamak o
    saatin tüm günlerini aynı döngüyle topluca değiştirir."""

    changed = Signal(int, int, object)  # day, period, yeni durum (None/'available'/'unavailable')

    _ORDER = {None: "available", "available": "unavailable", "unavailable": None}

    def __init__(self):
        super().__init__()
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setShowGrid(False)
        self.setStyleSheet(
            "QHeaderView::section { font-size: 8pt; padding: 2px 0; }"
        )
        self._occupied: set[tuple[int, int]] = set()
        self._state: dict[tuple[int, int], str] = {}
        self._day_header_state: dict[int, str | None] = {}
        self._period_header_state: dict[int, str | None] = {}
        self.cellClicked.connect(self._handle_click)
        self.horizontalHeader().setSectionsClickable(True)
        self.verticalHeader().setSectionsClickable(True)
        self.horizontalHeader().sectionClicked.connect(self._handle_day_header_click)
        self.verticalHeader().sectionClicked.connect(self._handle_period_header_click)

    def render(self, db: Database, blocks_by_cell: dict[tuple[int, int], list], availability: dict[tuple[int, int], str]) -> None:
        day_names = db.day_names
        period_count = db.period_count
        self.setRowCount(period_count)
        self.setColumnCount(len(day_names))
        self.setHorizontalHeaderLabels(day_names)
        self.setVerticalHeaderLabels([f"{p}." for p in range(1, period_count + 1)])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.horizontalHeader().setMinimumSectionSize(46)
        self.verticalHeader().setMaximumWidth(26)

        self._occupied = set(blocks_by_cell.keys())
        self._state = dict(availability)
        self._day_header_state = {}
        self._period_header_state = {}

        row_height = max(28, min(52, 340 // max(period_count, 1)))
        for period in range(1, period_count + 1):
            self.setRowHeight(period - 1, row_height)
            for day in range(len(day_names)):
                cell = (day, period)
                blocks = blocks_by_cell.get(cell, [])
                if blocks:
                    widget = theme.make_multi_cell(blocks, compact=True)
                else:
                    widget = self._availability_cell(self._state.get(cell))
                self.setCellWidget(period - 1, day, widget)

    @staticmethod
    def _availability_cell(status: str | None) -> QWidget:
        if status == "available":
            style = (
                f"#cellFrame {{ background:{theme.VALID_BG}; "
                f"border:1.5px solid {theme.VALID_BORDER}; border-radius:6px; }}"
            )
        elif status == "unavailable":
            style = (
                f"#cellFrame {{ background:{theme.CONFLICT_BG}; "
                f"border:1.5px solid {theme.CONFLICT_BORDER}; border-radius:6px; }}"
            )
        else:
            style = (
                f"#cellFrame {{ background:transparent; "
                f"border:1.5px dashed {theme.BORDER_INPUT}; border-radius:6px; }}"
            )
        frame = QWidget()
        frame.setObjectName("cellFrame")
        frame.setStyleSheet(style)
        return frame

    def _apply(self, day: int, period: int, next_status: str | None) -> None:
        cell = (day, period)
        if next_status is None:
            self._state.pop(cell, None)
        else:
            self._state[cell] = next_status
        self.setCellWidget(period - 1, day, self._availability_cell(next_status))
        self.viewport().update()
        self.changed.emit(day, period, next_status)

    def _handle_click(self, row: int, col: int) -> None:
        cell = (col, row + 1)  # (day, period)
        if cell in self._occupied:
            return
        next_status = self._ORDER[self._state.get(cell)]
        self._apply(cell[0], cell[1], next_status)

    def _handle_day_header_click(self, day: int) -> None:
        next_status = self._ORDER[self._day_header_state.get(day)]
        self._day_header_state[day] = next_status
        for period in range(1, self.rowCount() + 1):
            if (day, period) in self._occupied:
                continue
            self._apply(day, period, next_status)

    def _handle_period_header_click(self, row: int) -> None:
        period = row + 1
        next_status = self._ORDER[self._period_header_state.get(period)]
        self._period_header_state[period] = next_status
        for day in range(self.columnCount()):
            if (day, period) in self._occupied:
                continue
            self._apply(day, period, next_status)


class SummaryTable(QTableWidget):
    """Ders tipine göre saat sayısı özeti (ör. Sınıf Dersi: 4, Birebir: 2)."""

    def __init__(self):
        super().__init__()
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["Ders Tipi", "Saat"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)

    def render(self, totals: dict[str, int]) -> None:
        rows = [(LESSON_TYPE_LABELS[t], count) for t, count in totals.items() if count]
        self.setRowCount(len(rows))
        for r, (label, count) in enumerate(rows):
            self.setItem(r, 0, QTableWidgetItem(label))
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(r, 1, count_item)


class ScopeDialog(QDialog):
    """Bir yerleştirme/temizleme işleminin sadece bu hafta mı yoksa
    kalıcı (şablon - dönem boyunca) mı olacağını sorar."""

    def __init__(self, db: Database, parent=None, action_desc: str = "Bu değişiklik"):
        super().__init__(parent)
        self.setWindowTitle("Kapsam Seç")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{action_desc} hangi haftalar için geçerli olsun?"))

        always_label = "Her hafta (kalıcı program)"
        term_start = db.term_start
        term_end = db.term_end
        if term_start and term_end:
            start_txt = _dt.date.fromisoformat(term_start).strftime("%d.%m.%Y")
            end_txt = _dt.date.fromisoformat(term_end).strftime("%d.%m.%Y")
            always_label = f"Bu dönem boyunca ({start_txt} – {end_txt})"

        self.week_only = QRadioButton("Sadece bu hafta")
        self.always = QRadioButton(always_label)
        self.always.setChecked(True)
        layout.addWidget(self.always)
        layout.addWidget(self.week_only)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def scope(self) -> str:
        return scheduling.SCOPE_WEEK_ONLY if self.week_only.isChecked() else scheduling.SCOPE_ALWAYS
