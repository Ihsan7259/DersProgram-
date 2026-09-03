"""Üst navigasyon çubuğu: koyu lacivert şerit, ikon + etiket yan yana.

Daha önce solda dikey bir şeritti; Ana Program'a daha fazla yatay yer
açmak için üste, yatay bir çubuğa taşındı."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame

from . import theme

NAV_ITEMS = [
    ("ana-program", "Ana Program"),
    ("siniflar", "Sınıflar"),
    ("ogretmenler", "Öğretmenler"),
    ("ogrenciler", "Öğrenciler"),
    ("dersler", "Dersler"),
    ("derslikler", "Derslikler"),
    ("analiz", "Analiz"),
    ("odemeler", "Ödemeler"),
    ("ayarlar", "Ayarlar"),
]


class Sidebar(QWidget):
    page_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(56)
        self.setStyleSheet(f"background: {theme.SIDEBAR_BG};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(18)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(9)
        badge = QLabel("DP")
        badge.setFixedSize(32, 32)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background:{theme.ACCENT}; color:white; border-radius:9px; "
            f"font-family:'{theme.FONT_HEADING}'; font-weight:800; font-size:10.5pt;"
        )
        brand_row.addWidget(badge)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        title = QLabel("Ders Programı")
        title.setStyleSheet(
            f"color:{theme.SIDEBAR_TEXT_ACTIVE}; font-family:'{theme.FONT_HEADING}'; "
            f"font-weight:700; font-size:9.7pt; background: transparent;"
        )
        subtitle = QLabel("Yönetim Paneli")
        subtitle.setStyleSheet(f"color:{theme.SIDEBAR_TEXT_MUTED}; font-size:7.4pt; background: transparent;")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand_row.addLayout(brand_text)
        layout.addLayout(brand_row)

        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setStyleSheet(f"color:{theme.SIDEBAR_BORDER};")
        layout.addWidget(divider)

        self._buttons: dict[str, QPushButton] = {}
        nav_row = QHBoxLayout()
        nav_row.setSpacing(2)
        for item_id, label in NAV_ITEMS:
            button = QPushButton(f" {label}")
            button.setIcon(theme.icon(theme.NAV_ICONS[item_id], theme.SIDEBAR_TEXT_MUTED))
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(38)
            button.clicked.connect(lambda _checked, i=item_id: self._select(i))
            self._buttons[item_id] = button
            nav_row.addWidget(button)
        layout.addLayout(nav_row)

        layout.addStretch()

        avatar = QLabel("SY")
        avatar.setFixedSize(28, 28)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            f"background:{theme.SIDEBAR_AVATAR_BG}; color:{theme.SIDEBAR_TEXT_ACTIVE}; "
            f"border-radius:14px; font-size:8.5pt; font-weight:700;"
        )
        layout.addWidget(avatar)
        footer_text = QVBoxLayout()
        footer_text.setSpacing(0)
        name = QLabel("Sekreterlik")
        name.setStyleSheet(f"color:{theme.SIDEBAR_TEXT_ACTIVE}; font-size:8.6pt; font-weight:600; background:transparent;")
        role = QLabel("Yönetici")
        role.setStyleSheet(f"color:{theme.SIDEBAR_TEXT_MUTED}; font-size:7.4pt; background:transparent;")
        footer_text.addWidget(name)
        footer_text.addWidget(role)
        layout.addLayout(footer_text)

        self.set_active("ana-program")

    def _select(self, item_id: str) -> None:
        self.set_active(item_id)
        self.page_selected.emit(item_id)

    def set_active(self, item_id: str) -> None:
        for i, button in self._buttons.items():
            active = i == item_id
            button.setChecked(active)
            color = theme.SIDEBAR_TEXT_ACTIVE if active else theme.SIDEBAR_TEXT_MUTED
            bg = theme.SIDEBAR_ACTIVE_BG if active else "transparent"
            weight = 700 if active else 500
            button.setIcon(theme.icon(theme.NAV_ICONS[i], color))
            button.setStyleSheet(
                f"QPushButton {{ text-align:left; border:none; border-radius:9px; "
                f"background:{bg}; color:{color}; font-size:8.9pt; font-weight:{weight}; padding:0 10px; }}"
                f"QPushButton:hover {{ background:{theme.SIDEBAR_ACTIVE_BG if active else '#182231'}; }}"
            )
