"""Sol navigasyon menüsü: koyu lacivert şerit, ikon + etiket."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame

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
        self.setFixedWidth(230)
        self.setStyleSheet(f"background: {theme.SIDEBAR_BG};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 20, 14, 16)
        layout.setSpacing(22)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        badge = QLabel("DP")
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background:{theme.ACCENT}; color:white; border-radius:9px; "
            f"font-family:'{theme.FONT_HEADING}'; font-weight:800; font-size:11pt;"
        )
        brand_row.addWidget(badge)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        title = QLabel("Ders Programı")
        title.setStyleSheet(
            f"color:{theme.SIDEBAR_TEXT_ACTIVE}; font-family:'{theme.FONT_HEADING}'; "
            f"font-weight:700; font-size:10.5pt; background: transparent;"
        )
        subtitle = QLabel("Yönetim Paneli")
        subtitle.setStyleSheet(f"color:{theme.SIDEBAR_TEXT_MUTED}; font-size:8pt; background: transparent;")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand_row.addLayout(brand_text)
        brand_row.addStretch()
        layout.addLayout(brand_row)

        self._buttons: dict[str, QPushButton] = {}
        nav_col = QVBoxLayout()
        nav_col.setSpacing(2)
        for item_id, label in NAV_ITEMS:
            button = QPushButton(f"  {label}")
            button.setIcon(theme.icon(theme.NAV_ICONS[item_id], theme.SIDEBAR_TEXT_MUTED))
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(36)
            button.clicked.connect(lambda _checked, i=item_id: self._select(i))
            self._buttons[item_id] = button
            nav_col.addWidget(button)
        layout.addLayout(nav_col)

        layout.addStretch()

        footer = QFrame()
        footer.setStyleSheet(f"border-top: 1px solid {theme.SIDEBAR_BORDER};")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(6, 12, 6, 0)
        footer_layout.setSpacing(10)
        avatar = QLabel("SY")
        avatar.setFixedSize(26, 26)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            f"background:{theme.SIDEBAR_AVATAR_BG}; color:{theme.SIDEBAR_TEXT_ACTIVE}; "
            f"border-radius:13px; font-size:8.5pt; font-weight:700;"
        )
        footer_layout.addWidget(avatar)
        footer_text = QVBoxLayout()
        footer_text.setSpacing(0)
        name = QLabel("Sekreterlik")
        name.setStyleSheet(f"color:{theme.SIDEBAR_TEXT_ACTIVE}; font-size:9pt; font-weight:600; background:transparent;")
        role = QLabel("Yönetici")
        role.setStyleSheet(f"color:{theme.SIDEBAR_TEXT_MUTED}; font-size:8pt; background:transparent;")
        footer_text.addWidget(name)
        footer_text.addWidget(role)
        footer_layout.addLayout(footer_text)
        footer_layout.addStretch()
        layout.addWidget(footer)

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
                f"background:{bg}; color:{color}; font-size:9.7pt; font-weight:{weight}; padding-left:6px; }}"
                f"QPushButton:hover {{ background:{theme.SIDEBAR_ACTIVE_BG if active else '#182231'}; }}"
            )
