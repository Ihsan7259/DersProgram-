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
    QFrame,
    QStyle,
)

from ..db import Database, LESSON_TYPE_LABELS
from .. import scheduling
from . import theme


def _set_cell_widget(table: QTableWidget, row: int, col: int, widget: QWidget) -> None:
    """QTableWidget.setCellWidget() eskisini yenisiyle değiştirdiğinde
    önceki widget'ı silmez - üst-alt ilişkisi kalır ama görünmez kalır.
    Sık yeniden çizilen ızgaralarda (müsaitlik tıklaması, haftalık program
    yenilemesi) bu birikip programı zamanla yavaşlatıyordu; eskisini elle
    koparıp siliyoruz."""
    old_widget = table.cellWidget(row, col)
    if old_widget is not None:
        table.removeCellWidget(row, col)
        old_widget.setParent(None)
        old_widget.deleteLater()
    table.setCellWidget(row, col, widget)


def section_title(text: str) -> QLabel:
    """Öğretmen/Öğrenci/Sınıf sekmelerindeki iki-sütunlu düzende bölüm
    başlıkları (ör. 'Öğretmen Listesi', 'Haftalık özet') için ortak stil."""
    label = QLabel(text)
    label.setStyleSheet(f"font-family:'{theme.FONT_HEADING}'; font-weight:700; font-size:10pt; color:{theme.INK_MUTED_30};")
    return label


def divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


def _period_header_labels(db: Database, periods) -> list[str]:
    """'1.' ya da (Ayarlar'da saat girilmişse) '1.\n08:30-09:20' şeklinde
    dikey başlık etiketleri üretir. periods bir int (1..periods) ya da
    doğrudan bir saat numarası listesi/aralığı olabilir."""
    if isinstance(periods, int):
        periods = range(1, periods + 1)
    labels = []
    for p in periods:
        time_label = db.period_time_label(p)
        labels.append(f"{p}.\n{time_label}" if time_label else f"{p}.")
    return labels


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
    """Salt okunur, filtrelenmiş (tek kişi/sınıfa ait) haftalık ızgara.
    Hücreler AvailabilityGrid'deki (bkz. aşağıda _apply_grid_sizing) ile
    AYNI mantıkla ~3:2 (genişlik:yükseklik) oranını korur - isim uzun/kısa
    olsun her hücre AYNI boyutta kalır."""

    def __init__(self):
        super().__init__()
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setShowGrid(False)
        self._day_count = 1
        self._fixed_col_width: int | None = None
        self._last_populate_args: tuple | None = None
        self._applied_sizing: tuple | None = None

    def populate(self, db: Database, blocks_by_cell: dict[tuple[int, int], list], row_mode: str | None = None) -> None:
        """Not: bilerek 'render' değil 'populate' adında - QWidget'ın
        kendi render() metodunu (bir widget'ı QPaintDevice'a çizip pixmap
        üretmek için kullanılır, bkz. schedule_tab._render_table_pixmap)
        gölgelememesi için. Daha önce burası 'render' adındaydı ve PDF/
        Kopyala düğmeleri tam da bu yüzden (table.render(pixmap) çağrısı
        QWidget'ınkini değil BUNU çağırdığı için) çöküyordu.

        Kullanıcı isteği: tüm gün/saat sayısını değil, sadece o kişi/sınıfın
        DERSİNİN OLDUĞU günleri ve saatleri kapsayan EN DAR (optimal)
        dikdörtgeni gösterir - ör. kurumda 15 saat tanımlıysa ama bu sınıfın
        dersleri sadece 1-5. saatlerdeyse, 6-15 arası tamamen boş satırlar
        hiç eklenmez (kutu/yazı boyutu bundan ETKİLENMEZ, sadece kaç satır/
        sütun çizileceği değişir). Hiç dersi yoksa (blocks_by_cell boş) tüm
        hafta gösterilir."""
        self._last_populate_args = (db, blocks_by_cell, row_mode)
        # Hücreler bu çağrıda BAŞTAN oluşturuluyor - _apply_grid_sizing'in
        # "zaten bu boyuttaydı" önbelleği (bkz. aşağıda, titreme önleme
        # amaçlı) burada geçersiz kılınmalı, aksi halde yeni hücreler Qt'nin
        # varsayılan (yanlış) genişliğinde kalabilir.
        self._applied_sizing = None
        day_names = db.day_names
        period_count = db.period_count

        used_days = sorted({day for day, _period in blocks_by_cell.keys()})
        used_periods = sorted({period for _day, period in blocks_by_cell.keys()})
        if used_days and used_periods:
            day_indices = list(range(used_days[0], used_days[-1] + 1))
            periods = list(range(used_periods[0], used_periods[-1] + 1))
        else:
            day_indices = list(range(len(day_names)))
            periods = list(range(1, period_count + 1))

        self._day_count = max(len(day_indices), 1)
        self.setRowCount(len(periods))
        self.setColumnCount(len(day_indices))
        self.setHorizontalHeaderLabels([day_names[d] for d in day_indices])
        self.setVerticalHeaderLabels(_period_header_labels(db, periods))
        self.verticalHeader().setMinimumWidth(30)

        # Kullanıcı isteği: "önce gridin oranı bozulmayacak şekilde sayfaya
        # yerleştir, sonra ... fontu büyüt ... en büyük alandan en fazla
        # verimi almak istiyorum." - dışa aktarımda (self._fixed_col_width
        # SABİT bir değere kilitliyken - bkz. set_fixed_column_width) yazı
        # tipi boyutu bu SABİT piksel genişliğe ORANTILI hesaplanır, böylece
        # yüksek çözünürlüklü büyük hücrelerde yazı da BÜYÜK ve okunaklı olur.
        #
        # Ekranda (dialog içinde, fixed_col_width YOK) ise bilerek TERSİ
        # yapılır: font viewport genişliğine göre DEĞİL, SABİT (pt) bir
        # değerde tutulur. Aksi halde "sekmeler arasında gidip gelince font
        # değişiyor" şikayetine yol açan bir kararsızlık oluşuyordu - dialog
        # ilk açıldığında henüz layout oturmadan (viewport genişliği 0/hazır
        # değilken) populate() çağrılabiliyor, bu da her seferinde FARKLI bir
        # varsayılan genişlikten hesaplanan farklı bir font boyutu demekti.
        # Hücre GENİŞLİĞİ (kutu boyutu) yine de ekrana göre dinamik kalır
        # (bkz. _apply_grid_sizing/resizeEvent) - sadece YAZI TİPİ sabitlendi.
        if self._fixed_col_width is not None:
            col_width = self._fixed_col_width
            primary_px = max(11, min(40, round(col_width * 0.10)))
            secondary_px = max(9, min(32, round(col_width * 0.082)))
            header_px = max(10, min(30, round(col_width * 0.075)))
            self.setStyleSheet(f"QHeaderView::section {{ font-size: {header_px}px; padding: 4px 2px; }}")
        else:
            primary_px = None
            secondary_px = None
            self.setStyleSheet("")

        for row, period in enumerate(periods):
            for col, day in enumerate(day_indices):
                blocks = blocks_by_cell.get((day, period), [])
                _set_cell_widget(self, row, col, theme.make_multi_cell(
                    blocks, compact=True, row_mode=row_mode, primary_px=primary_px, secondary_px=secondary_px,
                ))
        self._apply_grid_sizing()

    def set_fixed_column_width(self, width_px: int | None) -> None:
        """Dışa aktarım (PDF/Kopyala) sırasında hücre genişliğini ekran
        boyutundan BAĞIMSIZ, sabit bir piksel değerine kilitler - böylece
        her sayfa/görsel AYNI hücre boyutunu (ve dolayısıyla aynı 3:2
        oranını) kullanır. None verilirse ekrandaki (dialog) normal
        davranışına, mevcut genişliğe göre otomatik hesaplamaya döner.

        Genişlik gerçekten değiştiğinde hücreleri (ve içindeki yazı tipi
        boyutunu, bkz. populate) son doldurulan verilerle YENİDEN kurar -
        aksi halde kartlar eski (yanlış) genişliğe göre hesaplanmış sabit
        piksel yazı tipiyle kalırdı."""
        if width_px == self._fixed_col_width:
            return
        self._fixed_col_width = width_px
        if self._last_populate_args is not None:
            db, blocks_by_cell, row_mode = self._last_populate_args
            self.populate(db, blocks_by_cell, row_mode=row_mode)
        else:
            self._apply_grid_sizing()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_grid_sizing()

    def _resolve_col_width(self) -> int | None:
        if self._fixed_col_width is not None:
            return self._fixed_col_width
        viewport_w = self.viewport().width()
        if viewport_w <= 0:
            return None
        scrollbar_w = self.style().pixelMetric(QStyle.PM_ScrollBarExtent)
        usable_w = max(viewport_w - scrollbar_w, viewport_w // 2)
        return max(46, usable_w // self._day_count)

    def _apply_grid_sizing(self) -> None:
        """AvailabilityGrid._apply_grid_sizing ile aynı mantık (bkz.
        aşağıda): sütun genişliği önce belirlenir (ekranda mevcut
        genişliğe göre, dışa aktarımda sabit hedef değere göre), satır
        yüksekliği de bu genişliğe göre ~3:2 (genişlik:yükseklik)
        oranında türetilir.

        Kullanıcı bildirimi: önizlemede hücreler bazen "büyüyüp
        küçülüyor" gibi bir titreme gösteriyordu. Qt bazen tek bir
        mantıksal pencere yeniden boyutlandırmasında resizeEvent'i art
        arda birkaç kez tetikleyebiliyor; her seferinde AYNI col_width
        için setColumnWidth/setRowHeight'ı (ve setSectionResizeMode'u)
        yeniden çağırmak gereksiz yeniden düzenlemelere (ve görsel
        titremeye) yol açabiliyordu. Sonuç GERÇEKTEN değişmediyse
        (aynı col_width + aynı satır/sütun sayısı) hiçbir şey yapmadan
        çıkılır."""
        if self.rowCount() == 0 or self.columnCount() == 0:
            return
        col_width = self._resolve_col_width()
        if col_width is None:
            return
        cache_key = (col_width, self.rowCount(), self.columnCount())
        if cache_key == self._applied_sizing:
            return
        self._applied_sizing = cache_key

        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)
        for col in range(self.columnCount()):
            self.setColumnWidth(col, col_width)

        # DİKKAT: yatay başlıkta olduğu gibi dikey başlık da açıkça Fixed
        # yapılmazsa, Qt bir hücredeki widget'ın (ör. uzun bir öğretmen adı
        # yüzünden) minimum boyutu bizim verdiğimiz satır yüksekliğinden
        # büyükse O SATIRI SESSİZCE BÜYÜTÜYOR - böylece aynı hafta içinde
        # bazı satırlar diğerlerinden çok daha uzun/orantısız görünüyordu
        # (kullanıcı ekran görüntüsüyle bildirdi). Fixed ile satır yüksekliği
        # her koşulda bizim belirlediğimiz değerde SABİT kalır.
        v_header = self.verticalHeader()
        v_header.setSectionResizeMode(QHeaderView.Fixed)
        row_height = max(28, int(col_width / 1.5))
        for row in range(self.rowCount()):
            self.setRowHeight(row, row_height)


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
            "QHeaderView::section { font-size: 7pt; padding: 2px 0; }"
        )
        self._occupied: set[tuple[int, int]] = set()
        self._state: dict[tuple[int, int], str] = {}
        self._row_mode: str | None = None
        self._day_header_state: dict[int, str | None] = {}
        self._period_header_state: dict[int, str | None] = {}
        self._day_count = 1
        self._period_count = 1
        self.cellClicked.connect(self._handle_click)
        self.horizontalHeader().setSectionsClickable(True)
        self.verticalHeader().setSectionsClickable(True)
        self.horizontalHeader().sectionClicked.connect(self._handle_day_header_click)
        self.verticalHeader().sectionClicked.connect(self._handle_period_header_click)

    def render(
        self,
        db: Database,
        blocks_by_cell: dict[tuple[int, int], list],
        availability: dict[tuple[int, int], str],
        row_mode: str | None = None,
    ) -> None:
        self._row_mode = row_mode
        day_names = db.day_names
        period_count = db.period_count
        self._day_count = max(len(day_names), 1)
        self._period_count = max(period_count, 1)
        self.setRowCount(period_count)
        self.setColumnCount(len(day_names))
        self.setHorizontalHeaderLabels(day_names)
        self.setVerticalHeaderLabels(_period_header_labels(db, period_count))
        self.horizontalHeader().setMinimumSectionSize(46)
        self.verticalHeader().setMaximumWidth(44)

        self._occupied = set(blocks_by_cell.keys())
        self._state = dict(availability)
        self._day_header_state = {}
        self._period_header_state = {}

        for period in range(1, period_count + 1):
            for day in range(len(day_names)):
                cell = (day, period)
                blocks = blocks_by_cell.get(cell, [])
                if blocks:
                    widget = theme.make_multi_cell(blocks, compact=True, row_mode=row_mode)
                else:
                    widget = self._availability_cell(self._state.get(cell))
                _set_cell_widget(self, period - 1, day, widget)
        self._apply_grid_sizing()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_grid_sizing()

    def _apply_grid_sizing(self) -> None:
        """Yatay alan hep dolu kalsın diye sütun genişliği önce tüm
        genişliği kullanacak şekilde hesaplanır, satır yüksekliği de bu
        genişliğe göre ~3:2 (genişlik:yükseklik) oranında türetilir.
        Saat sayısı çoksa (hücreler yükseklikte sığmıyorsa) oranı bozup
        sıkıştırmak yerine ızgara dikey kaydırılabilir bırakılır - kalan
        saatler aşağıda, kaydırarak görülür."""
        viewport_w = self.viewport().width()
        if viewport_w <= 0 or self.rowCount() == 0 or self.columnCount() == 0:
            return
        # Bir dikey kaydırma çubuğu çıkarsa viewport genişliği azalır, bu da
        # sütunları yeniden hesaplatıp çubuğun görünüp kaybolmasını
        # tetikleyebilir (salınım) - bunu önlemek için çubuk payını en
        # baştan ayırıyoruz.
        scrollbar_w = self.style().pixelMetric(QStyle.PM_ScrollBarExtent)
        usable_w = max(viewport_w - scrollbar_w, viewport_w // 2)
        col_width = max(46, usable_w // self._day_count)

        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)
        for col in range(self.columnCount()):
            self.setColumnWidth(col, col_width)

        # DİKKAT: yatay başlıkta olduğu gibi dikey başlık da açıkça Fixed
        # yapılmazsa, Qt bir hücredeki widget'ın (ör. uzun bir öğretmen adı
        # yüzünden) minimum boyutu bizim verdiğimiz satır yüksekliğinden
        # büyükse O SATIRI SESSİZCE BÜYÜTÜYOR - böylece aynı hafta içinde
        # bazı satırlar diğerlerinden çok daha uzun/orantısız görünüyordu
        # (kullanıcı ekran görüntüsüyle bildirdi). Fixed ile satır yüksekliği
        # her koşulda bizim belirlediğimiz değerde SABİT kalır.
        v_header = self.verticalHeader()
        v_header.setSectionResizeMode(QHeaderView.Fixed)
        row_height = max(28, int(col_width / 1.5))
        for row in range(self.rowCount()):
            self.setRowHeight(row, row_height)

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
        _set_cell_widget(self, period - 1, day, self._availability_cell(next_status))
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
