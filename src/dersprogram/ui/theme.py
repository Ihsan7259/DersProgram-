"""Görsel kimlik: renkler, fontlar, ikonlar ve genel stylesheet.

Renk paleti, tasarım taslağındaki (Claude Design ile hazırlanan mockup)
oklch değerlerinden hex'e çevrilerek buraya taşındı; tek doğru kaynak
burasıdır - başka yerde renk kodu hardcode edilmemeli.

Açık/Koyu tema: nötr tonlar (arkaplan/yüzey/kenarlık/metin) `apply_theme()`
ile değişir; vurgu renkleri (accent, amber, ders tipi renkleri, çakışma/
uygun renkleri, kenar çubuğu) her iki temada da sabit kalır - bunlar zaten
kendi arkaplanlarını taşıyor, uygulama temasından etkilenmeleri gerekmiyor.
"""
from __future__ import annotations

import sys
from html import escape as _html_escape
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFontDatabase, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from ..db import (
    TYPE_CLASS,
    TYPE_ONE_ON_ONE,
    TYPE_COACHING,
    TYPE_DEPARTMENT,
    TYPE_PROBLEM_SOLVING,
    LESSON_TYPE_LABELS,
)

FONT_HEADING = "Manrope"
FONT_BODY = "Work Sans"

MODE = "light"

# ---------- temaya göre değişen nötr tonlar ----------
_LIGHT = {
    "APP_BG": "#f7f5f1",
    "SURFACE": "#fcfcfa",
    "BORDER_SUBTLE": "#dee1e7",
    "BORDER_INPUT": "#d4d8dd",
    "DIVIDER": "#e9e8e3",
    "INK": "#10161f",
    "INK_MUTED_30": "#282e38",
    "INK_MUTED_38": "#3c434d",
    "INK_MUTED_42": "#434e5e",
    "INK_MUTED_52": "#626a75",
    "INK_MUTED_58": "#737b86",
    "INK_MUTED_72": "#a1a5aa",
    "ACCENT_SOFT_BG": "#d2eef0",
    "ACCENT_SOFT_TEXT": "#005157",
}

_DARK = {
    "APP_BG": "#141b24",
    "SURFACE": "#1c2530",
    "BORDER_SUBTLE": "#2c3541",
    "BORDER_INPUT": "#3a4552",
    "DIVIDER": "#26303a",
    "INK": "#eef1f4",
    "INK_MUTED_30": "#e4e7ea",
    "INK_MUTED_38": "#cdd2d8",
    "INK_MUTED_42": "#c0c6cc",
    "INK_MUTED_52": "#9aa1a9",
    "INK_MUTED_58": "#868e97",
    "INK_MUTED_72": "#5b636c",
    "ACCENT_SOFT_BG": "#0d3a3d",
    "ACCENT_SOFT_TEXT": "#7fd8de",
}

# başlangıç değerleri (açık tema) - apply_theme() bunları değiştirir
APP_BG = _LIGHT["APP_BG"]
SURFACE = _LIGHT["SURFACE"]
BORDER_SUBTLE = _LIGHT["BORDER_SUBTLE"]
BORDER_INPUT = _LIGHT["BORDER_INPUT"]
DIVIDER = _LIGHT["DIVIDER"]
INK = _LIGHT["INK"]
INK_MUTED_30 = _LIGHT["INK_MUTED_30"]
INK_MUTED_38 = _LIGHT["INK_MUTED_38"]
INK_MUTED_42 = _LIGHT["INK_MUTED_42"]
INK_MUTED_52 = _LIGHT["INK_MUTED_52"]
INK_MUTED_58 = _LIGHT["INK_MUTED_58"]
INK_MUTED_72 = _LIGHT["INK_MUTED_72"]
ACCENT_SOFT_BG = _LIGHT["ACCENT_SOFT_BG"]
ACCENT_SOFT_TEXT = _LIGHT["ACCENT_SOFT_TEXT"]

# ---------- her iki temada da sabit kalan renkler ----------
SIDEBAR_BG = "#101925"
SIDEBAR_ACTIVE_BG = "#003639"
SIDEBAR_TEXT_MUTED = "#9199a5"
SIDEBAR_TEXT_ACTIVE = "#f8f5ee"
SIDEBAR_BORDER = "#282e38"
SIDEBAR_AVATAR_BG = "#394353"

ACCENT = "#00848b"
ACCENT_HOVER = "#00666d"

AMBER = "#e1901f"
AMBER_HOVER = "#c97e14"
AMBER_TEXT = "#271704"

CONFLICT_BORDER = "#c92f36"
CONFLICT_BG = "#ffe2de"
CONFLICT_TEXT = "#8d0012"

VALID_BORDER = "#0e9254"
VALID_BG = "#d8f8e2"
VALID_TEXT = "#006933"

# tip -> (arkaplan, nokta rengi) - pastel kartlar her iki temada da aynı
# (koyu arkaplan üzerinde açık renkli rozet olarak kalması okunurluğu korur)
LESSON_TYPE_COLORS: dict[str, tuple[str, str]] = {
    TYPE_CLASS: ("#d7eaff", "#1f74bf"),
    TYPE_ONE_ON_ONE: ("#ede2fb", "#865eb1"),
    TYPE_COACHING: ("#f8e5c7", "#b47900"),
    TYPE_DEPARTMENT: ("#d0f1e1", "#008b61"),
    TYPE_PROBLEM_SOLVING: ("#ffdedb", "#bf534e"),
}
LESSON_TYPE_TEXT = "#10161f"  # pastel kart üzerindeki metin - temadan bağımsız koyu
LESSON_TYPE_TEXT_MUTED = "#4b5768"  # pastel kart üzerindeki ikincil metin

NAV_ICONS: dict[str, str] = {
    "ana-program": "M4 5h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M8 3v4 M16 3v4 M3 10h18",
    "siniflar": "M5 21V6l7-3 7 3v15 M9 21v-6h6v6 M9 10h1 M14 10h1 M9 14h1 M14 14h1",
    "ogretmenler": "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4.5 21a7.5 7.5 0 0 1 15 0",
    "ogrenciler": "M2 9.5 12 5l10 4.5-10 4.5-10-4.5z M6 12v4.5c0 1.7 2.7 3 6 3s6-1.3 6-3V12 M20 9.5v6",
    "dersler": "M5 4.5A1.5 1.5 0 0 1 6.5 3H18a1 1 0 0 1 1 1v16a1 1 0 0 0-1-1H6.5A1.5 1.5 0 0 0 5 20.5v-16z M8 3v17.2",
    "derslikler": "M6 21V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v17 M6 21h9 M6 21H4 M15 21h3 M13.2 12.2a.8.8 0 1 0 0-1.6.8.8 0 0 0 0 1.6z",
    "analiz": "M4 20V11 M10 20V6 M16 20V13 M4 20h16",
    "odemeler": "M4 7.5A1.5 1.5 0 0 1 5.5 6H19a1 1 0 0 1 1 1v10a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17V7.5z M15 12.2h.01 M4 10h16",
    "ayarlar": "M4 7h9 M17 7h3 M4 17h3 M11 17h9 M14 4.5v5 M8 14.5v5",
    "prev": "M15 18l-6-6 6-6",
    "next": "M9 18l6-6-6-6",
    "up": "M18 15l-6-6-6 6",
    "down": "M6 9l6 6 6-6",
    "plus": "M12 5v14M5 12h14",
    "bolt": "M13 3 4 14h6l-1 7 9-11h-6l1-7z",
    "search": "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z M21 21l-4.3-4.3",
    "copy": "M8 8h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z M5 16H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1",
    "document": "M6 2h8l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z M14 2v6h5",
}


def apply_theme(mode: str) -> None:
    """Nötr renk tonlarını açık/koyu temaya göre değiştirir. Zaten
    oluşturulmuş özel renkli widget'lar (ders kartları, ızgara hücreleri)
    otomatik güncellenmez - bunları çağıran taraf yeniden çizmeli
    (bkz. MainWindow.apply_theme_change)."""
    global MODE
    global APP_BG, SURFACE, BORDER_SUBTLE, BORDER_INPUT, DIVIDER
    global INK, INK_MUTED_30, INK_MUTED_38, INK_MUTED_42, INK_MUTED_52, INK_MUTED_58, INK_MUTED_72
    global ACCENT_SOFT_BG, ACCENT_SOFT_TEXT

    MODE = "dark" if mode == "dark" else "light"
    palette = _DARK if MODE == "dark" else _LIGHT

    APP_BG = palette["APP_BG"]
    SURFACE = palette["SURFACE"]
    BORDER_SUBTLE = palette["BORDER_SUBTLE"]
    BORDER_INPUT = palette["BORDER_INPUT"]
    DIVIDER = palette["DIVIDER"]
    INK = palette["INK"]
    INK_MUTED_30 = palette["INK_MUTED_30"]
    INK_MUTED_38 = palette["INK_MUTED_38"]
    INK_MUTED_42 = palette["INK_MUTED_42"]
    INK_MUTED_52 = palette["INK_MUTED_52"]
    INK_MUTED_58 = palette["INK_MUTED_58"]
    INK_MUTED_72 = palette["INK_MUTED_72"]
    ACCENT_SOFT_BG = palette["ACCENT_SOFT_BG"]
    ACCENT_SOFT_TEXT = palette["ACCENT_SOFT_TEXT"]


def build_palette(mode: str) -> QPalette:
    """Qt'nin kendi (stillenmemiş) bileşenleri için de - onay kutusu,
    açılır liste menüsü, mesaj kutusu gibi - tutarlı bir renk seti.
    Fusion stiliyle birlikte kullanılır; Windows'un koyu/açık temasından
    bağımsız, her zaman öngörülebilir bir görünüm sağlar."""
    colors = _DARK if mode == "dark" else _LIGHT
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(colors["APP_BG"]))
    pal.setColor(QPalette.WindowText, QColor(colors["INK"]))
    pal.setColor(QPalette.Base, QColor(colors["SURFACE"]))
    pal.setColor(QPalette.AlternateBase, QColor(colors["APP_BG"]))
    pal.setColor(QPalette.Text, QColor(colors["INK"]))
    pal.setColor(QPalette.Button, QColor(colors["SURFACE"]))
    pal.setColor(QPalette.ButtonText, QColor(colors["INK"]))
    pal.setColor(QPalette.ToolTipBase, QColor(colors["SURFACE"]))
    pal.setColor(QPalette.ToolTipText, QColor(colors["INK"]))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.PlaceholderText, QColor(colors["INK_MUTED_58"]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(colors["INK_MUTED_72"]))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(colors["INK_MUTED_72"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colors["INK_MUTED_72"]))
    return pal


def _assets_dir() -> Path:
    """PyInstaller ile tek dosya .exe haline getirildiğinde varlıklar
    sys._MEIPASS altına açılır; geliştirme ortamında ise dosya sisteminde
    bu modülün yanındadır."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "dersprogram" / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


def load_fonts() -> None:
    fonts_dir = _assets_dir() / "fonts"
    QFontDatabase.addApplicationFont(str(fonts_dir / "Manrope.ttf"))
    QFontDatabase.addApplicationFont(str(fonts_dir / "WorkSans.ttf"))


def app_icon() -> QIcon:
    """Uygulama/pencere simgesi (taskbar, pencere başlığı) - .exe'nin kendi
    simgesi PyInstaller --icon ile ayrıca gömülür (bkz. build-windows-exe.yml),
    burası SADECE çalışırkenki pencere simgesini ayarlar."""
    return QIcon(str(_assets_dir() / "icons" / "app.png"))


def icon(path_d: str, color: str | None = None, size: int = 18) -> QIcon:
    color = color or INK_MUTED_58
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="{path_d}"></path></svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    scale = 3
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QIcon(pixmap)


def lesson_type_label(type_: str) -> str:
    return LESSON_TYPE_LABELS.get(type_, type_)


# Öğretmenin haftalık programında/önizlemesinde aynı ders tipi (ör. Sınıf
# Dersi = mavi) farklı sınıflar/öğrenciler arasında küçük ton farklarıyla
# ayırt edilsin diye - hem tipi hem de "kiminle" olduğunu tek bakışta
# gösterir. Işık (L) kanalında küçük kaymalar, rengin ana kimliğini
# (hue/saturation) korur.
_TONE_SHIFTS = [0, -20, 16, -36, 28, -10, 10, -28]


def _tone_shift(hex_color: str, amount: int) -> str:
    color = QColor(hex_color)
    h, s, l, a = color.getHsl()
    l = max(30, min(240, l + amount))
    return QColor.fromHsl(h, s, l, a).name()


# Sınıf dersi / birebir / soru çözümü kartlarında artık DERSİN KENDİSİ
# (branş) renk belirliyor - "Matematik" mavi, "Kimya" yeşil, "Türkçe" pembe
# gibi - aynı ders tipindeki (ör. hepsi "sınıf dersi") kartlar birbirinden
# ayırt edilebilsin diye. Koçluk ve zümre gibi branşsız/tek amaçlı
# derslerde eski tip-bazlı renk (amber/yeşil) korunuyor. Sabit bir renk
# çemberinden (hue) eşit aralıklarla seçilir - subject_id'ye göre
# deterministik olduğundan aynı ders her zaman aynı renkte kalır.
_SUBJECT_APPLICABLE_TYPES = {TYPE_CLASS, TYPE_ONE_ON_ONE, TYPE_PROBLEM_SOLVING}
_SUBJECT_HUES = [210, 20, 140, 280, 45, 165, 320, 0, 190, 100, 260, 340, 60, 230]


def _subject_colors(subject_id: int) -> tuple[str, str]:
    hue = _SUBJECT_HUES[subject_id % len(_SUBJECT_HUES)]
    bg = QColor.fromHsl(hue, 190, 228).name()
    dot = QColor.fromHsl(hue, 200, 100).name()
    return bg, dot


def lesson_colors_for(block, tinted: bool = False) -> tuple[str, str]:
    """(Arkaplan, nokta) rengi döner - branşı olan ders tiplerinde
    (sınıf/birebir/soru çözümü) dersin kendisine (subject_id) göre, yoksa
    (koçluk/zümre) ders tipine göre. tinted=True ise (öğretmen
    görünümünde) sınıf/öğrenciye göre küçük bir ton farkı eklenir - renk
    ailesi korunur, sadece tonu değişir."""
    if block.type in _SUBJECT_APPLICABLE_TYPES and block.subject_id is not None:
        bg, dot = _subject_colors(block.subject_id)
    else:
        bg, dot = LESSON_TYPE_COLORS.get(block.type, (SURFACE, INK_MUTED_58))
    if not tinted:
        return bg, dot
    key = block.class_group_id or block.student_id or block.subject_id or 0
    shift = _TONE_SHIFTS[key % len(_TONE_SHIFTS)]
    return _tone_shift(bg, shift), _tone_shift(dot, shift // 2)


def make_lesson_card(block, compact: bool = False, row_mode: str | None = None) -> QWidget:
    """Bir ders bloğunu (block: scheduling.BlockView) küçük renkli bir
    kart olarak gösterir - tipe göre pastel arkaplan + nokta işareti.

    row_mode='class' ise (sınıfın kendi haftalık programı) kart 'ders adı /
    öğretmen adı' şeklinde gösterilir; sınıf adı zaten belli olduğu için
    tekrar edilmez. row_mode='teacher' ise (öğretmenin kendi programı/
    önizlemesi) kart 'sınıf ya da öğrenci adı / branş' şeklinde gösterilir
    ve renk tonu sınıfa göre hafifçe değişir. row_mode='student' ise
    (öğrencinin kendi programı/önizlemesi - kişisel + sınıfının ortak
    dersleri birlikte) kart 'ders/tür adı / öğretmen adı' şeklinde
    gösterilir."""
    bg, dot = lesson_colors_for(block, tinted=row_mode in ("teacher", "student"))
    if row_mode == "class":
        primary, secondary = block.class_row_lines()
        tertiary = ""
    elif row_mode == "teacher":
        primary, secondary = block.teacher_row_lines()
        tertiary = ""
    elif row_mode == "student":
        primary, secondary = block.student_row_lines()
        tertiary = ""
    else:
        primary, secondary, tertiary = block.card_lines()

    card = QWidget()
    card.setObjectName("lessonCard")
    # Kompakt modda (mini önizleme ızgaraları / PDF / Kopyala) köşeler
    # KARE tutulur - yuvarlak köşeler bitişik hücrelerin arasında (aynı
    # renkte bile olsalar) küçük bir "boşluk" izlenimi yaratıyordu, kart
    # her zaman hücreyi tam dolduracağından burada yuvarlamaya gerek yok.
    radius = 0 if compact else 8
    card.setStyleSheet(f"#lessonCard {{ background: {bg}; border-radius: {radius}px; }}")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(7, 5, 7, 4 if compact else 5)
    layout.setSpacing(1)

    if not compact:
        head = QHBoxLayout()
        head.setSpacing(4)
        dot_label = QLabel()
        dot_label.setFixedSize(6, 6)
        dot_label.setStyleSheet(f"background: {dot}; border-radius: 3px;")
        head.addWidget(dot_label)
        type_label = QLabel(lesson_type_label(block.type).upper())
        type_label.setStyleSheet(
            f"font-size: 7.3pt; font-weight: 700; color: {LESSON_TYPE_TEXT_MUTED}; letter-spacing: 0.4px; background: transparent;"
        )
        head.addWidget(type_label)
        head.addStretch()
        layout.addLayout(head)
    else:
        # Kartın kendisi hep hücre boyutunda (sabit) kalır; içerik az ya da
        # çok olsun (kısa/uzun isim) her zaman DİKEY OLARAK ORTALANIR - aksi
        # halde kısa metinli kartlar üstte sıkışıp altında boşluk kalıyor,
        # bu da kartların "farklı boyuttaymış" gibi görünmesine yol açıyordu.
        layout.addStretch()

    primary_label = QLabel(primary)
    primary_label.setWordWrap(True)
    primary_label.setStyleSheet(
        f"font-family: '{FONT_HEADING}'; font-weight: 700; "
        f"font-size: {'8.8pt' if compact else '9.3pt'}; color: {LESSON_TYPE_TEXT}; background: transparent;"
    )
    layout.addWidget(primary_label)

    if secondary and (not compact or row_mode in ("class", "teacher", "student")):
        secondary_label = QLabel(secondary)
        secondary_label.setWordWrap(True)
        secondary_label.setStyleSheet(
            f"font-size: {'7.9pt' if compact else '8.2pt'}; color: {LESSON_TYPE_TEXT_MUTED}; background: transparent;"
        )
        layout.addWidget(secondary_label)

    if tertiary and not compact:
        tertiary_label = QLabel(tertiary)
        tertiary_label.setWordWrap(True)
        tertiary_label.setStyleSheet(f"font-size: 7.8pt; color: {LESSON_TYPE_TEXT_MUTED}; background: transparent;")
        layout.addWidget(tertiary_label)

    layout.addStretch()
    return card


def _elide(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def make_dense_chip(line1: str, line2: str, bg: str) -> QWidget:
    """Kurum geneli ızgara (satır=sınıf/öğretmen) için çok kompakt hücre
    kartı. Ana Program'da hücreler arasında boşluk bırakmamak ve köşeleri
    kare tutmak için tek bir QLabel'e sıkıştırılır (satır=sınıf/öğretmen ×
    gün×saat kadar hücre olabileceğinden, hücre başına widget sayısını
    azaltmak tepki hızını da korur)."""
    text = f"<div style='font-weight:700; font-size:6.9pt; color:{LESSON_TYPE_TEXT};'>{_html_escape(_elide(line1, 5))}</div>"
    if line2:
        text += f"<div style='font-size:6.3pt; color:{LESSON_TYPE_TEXT_MUTED};'>{_html_escape(_elide(line2, 6))}</div>"
    label = QLabel()
    label.setObjectName("cellFrame")
    label.setTextFormat(Qt.RichText)
    label.setText(text)
    label.setAlignment(Qt.AlignCenter)
    label.setToolTip(f"{line1}\n{line2}" if line2 else line1)
    # Kenarlık widget'ın kendi stilinde değil, ızgaranın gridline'ında
    # çiziliyor (bkz. MainGrid.setShowGrid(True)) - böylece bitişik iki
    # hücre arasında tek ince çizgi kalır, çift kenarlıktan doğan görünür
    # boşluk oluşmaz.
    label.setStyleSheet(f"#cellFrame {{ background:{bg}; border-radius:0; border:none; }}")
    return label


def make_day_banner(day_name: str) -> QWidget:
    """Ana Program ızgarasında her günü ayıran bant başlığı."""
    band = QWidget()
    band.setObjectName("dayBanner")
    band.setStyleSheet(f"#dayBanner {{ background:{SIDEBAR_ACTIVE_BG}; border-radius:5px; }}")
    layout = QHBoxLayout(band)
    layout.setContentsMargins(10, 0, 10, 0)
    label = QLabel(day_name)
    label.setStyleSheet(
        "font-family:'" + FONT_HEADING + "'; font-weight:700; font-size:8.6pt; color:#7fd8de; background:transparent;"
    )
    layout.addWidget(label)
    return band


def make_dense_empty() -> QWidget:
    frame = QWidget()
    frame.setObjectName("cellFrame")
    frame.setStyleSheet(f"#cellFrame {{ background:{APP_BG}; border-radius:0; border:none; }}")
    return frame


def make_dense_unavailable() -> QWidget:
    """Ana Program'ın kurum geneli ızgarasında, öğretmenin kendisinin
    'müsait değil' işaretlediği boş bir hücre için küçük bir x işareti."""
    label = QLabel("×")
    label.setObjectName("cellFrame")
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet(
        f"#cellFrame {{ background:{CONFLICT_BG}; border-radius:0; border:none; "
        f"color:{CONFLICT_BORDER}; font-weight:700; font-size:10pt; }}"
    )
    label.setToolTip("Öğretmen bu saatte müsait değil olarak işaretlenmiş")
    return label


def make_empty_cell(compact: bool = False) -> QWidget:
    frame = QWidget()
    frame.setObjectName("cellFrame")
    radius = 0 if compact else 8
    frame.setStyleSheet(
        f"#cellFrame {{ border: 1.5px dashed {BORDER_INPUT}; border-radius: {radius}px; background: transparent; }}"
    )
    if not compact:
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel("Boş")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(f"color: {INK_MUTED_72}; font-size: 8pt; background: transparent; border: none;")
        layout.addWidget(label)
    return frame


def make_multi_cell(blocks: list, compact: bool = False, row_mode: str | None = None) -> QWidget:
    """Bir (gün, saat) hücresindeki tüm ders bloklarını üst üste dizer.
    Ana Program hücresinde birden fazla ders (farklı sınıflar) aynı
    saatte olabilir; filtrelenmiş mini programlarda genelde tek olur."""
    if not blocks:
        return make_empty_cell(compact=compact)
    frame = QWidget()
    frame.setObjectName("cellFrame")
    radius = 0 if compact else 8
    frame.setStyleSheet(f"#cellFrame {{ border: none; border-radius: {radius}px; background: transparent; }}")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    for block in blocks:
        layout.addWidget(make_lesson_card(block, compact=compact, row_mode=row_mode))
    return frame


def stylesheet() -> str:
    return f"""
    QWidget {{
        font-family: '{FONT_BODY}';
        font-size: 10.5pt;
        color: {INK};
    }}
    QMainWindow, #contentArea {{
        background: {APP_BG};
    }}
    QLabel#pageTitle {{
        font-family: '{FONT_HEADING}';
        font-weight: 800;
        font-size: 15.5pt;
        color: {INK};
    }}
    QLabel#pageSubtitle {{
        color: {INK_MUTED_52};
        font-size: 9.5pt;
    }}
    QToolTip {{
        background: {SURFACE};
        color: {INK};
        border: 1px solid {BORDER_SUBTLE};
        padding: 3px 6px;
    }}
    QPushButton {{
        background: {SURFACE};
        border: 1px solid {BORDER_INPUT};
        border-radius: 8px;
        padding: 6px 14px;
        font-weight: 600;
        color: {INK};
    }}
    QPushButton:hover {{
        background: {APP_BG};
    }}
    QPushButton#primaryButton {{
        background: {AMBER};
        color: {AMBER_TEXT};
        border: none;
        font-weight: 700;
        padding: 7px 16px;
    }}
    QPushButton#primaryButton:hover {{
        background: {AMBER_HOVER};
    }}
    QPushButton#outlineButton {{
        background: transparent;
        border: 1.5px solid {ACCENT};
        color: {ACCENT_HOVER};
        font-weight: 600;
        padding: 6.5px 15px;
    }}
    QPushButton#outlineButton:hover {{
        background: {ACCENT_SOFT_BG};
    }}
    QPushButton#dangerButton {{
        background: transparent;
        border: 1.5px solid {CONFLICT_BORDER};
        color: {CONFLICT_BORDER};
        font-weight: 600;
        padding: 6.5px 15px;
    }}
    QPushButton#dangerButton:hover {{
        background: {CONFLICT_BG};
    }}
    QPushButton#modeButton {{
        background: {SURFACE};
        border: 1px solid {BORDER_INPUT};
        color: {INK_MUTED_52};
        font-weight: 600;
        padding: 6px 14px;
    }}
    QPushButton#modeButton:checked {{
        background: {SIDEBAR_ACTIVE_BG};
        border: 1px solid {SIDEBAR_ACTIVE_BG};
        color: #7fd8de;
    }}
    QPushButton#iconButton {{
        padding: 4px;
        border-radius: 7px;
    }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{
        background: {SURFACE};
        border: 1px solid {BORDER_INPUT};
        border-radius: 8px;
        padding: 5px 9px;
        color: {INK};
        selection-background-color: {ACCENT_SOFT_BG};
        selection-color: {INK};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
        border: 1.5px solid {ACCENT};
    }}
    QComboBox QAbstractItemView {{
        background: {SURFACE};
        color: {INK};
        border: 1px solid {BORDER_SUBTLE};
        selection-background-color: {ACCENT_SOFT_BG};
        selection-color: {INK};
        outline: none;
    }}
    QCheckBox, QRadioButton {{
        color: {INK};
        spacing: 7px;
    }}
    QTableWidget, QListWidget {{
        background: {SURFACE};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 12px;
        gridline-color: {DIVIDER};
        outline: none;
        color: {INK};
    }}
    QTableWidget::item, QListWidget::item {{
        padding: 3px;
    }}
    QTableWidget::item:selected, QListWidget::item:selected {{
        background: {ACCENT_SOFT_BG};
        color: {INK};
    }}
    QHeaderView::section {{
        background: {APP_BG};
        border: none;
        border-bottom: 1px solid {BORDER_SUBTLE};
        padding: 7px;
        font-weight: 700;
        color: {INK_MUTED_42};
    }}
    QTabWidget::pane {{
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 10px;
        background: {SURFACE};
    }}
    QTabBar::tab {{
        background: transparent;
        padding: 8px 14px;
        color: {INK_MUTED_52};
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        color: {ACCENT_HOVER};
        border-bottom: 2px solid {ACCENT};
    }}
    QSplitter::handle {{
        background: {DIVIDER};
    }}
    QScrollBar:vertical {{
        width: 10px; background: transparent;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER_INPUT}; border-radius: 5px; min-height: 24px;
    }}
    QMessageBox {{
        background: {SURFACE};
    }}
    QDialog {{
        background: {APP_BG};
    }}
    """
