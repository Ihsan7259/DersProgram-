"""Havuzdaki her ihtiyacın (ör. '9-A · Matematik · Ahmet Yılmaz') haftanın
hangi gününde neden yerleşemediğini gün gün açıklayan diyalog. Oto Ata'nın
tek satırlık "X saat sığmıyor" uyarısının aksine, kullanıcının TAM OLARAK
hangi günü neyin (çakışma, müsaitlik, günlük sınır/bitişiklik kuralı)
engellediğini görüp veriyi buna göre düzeltebilmesi içindir."""
from __future__ import annotations

from html import escape as _esc

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton

from ..db import Database
from .. import scheduling
from . import theme


class UnplacedReportDialog(QDialog):
    def __init__(self, db: Database, week_start, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Neden Yerleşmedi?")
        self.resize(740, 580)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Atanmamış Dersler havuzundaki her ihtiyaç için, haftanın her gününün neden "
            "uygun ya da uygun değil olduğunu gösterir. Yeşil günlerde en az bir açık saat "
            "var; kırmızı günlerde neden kapalı olduğu (çakışma, müsaitlik ya da günlük "
            "sınır/bitişiklik kuralı) yanında yazar."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text, 1)

        close_button = QPushButton("Kapat")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

        self._render(db, week_start)

    def _render(self, db: Database, week_start) -> None:
        day_names = db.day_names
        reports = scheduling.explain_unplaced_lessons(db, week_start)

        if not reports:
            self.text.setHtml(
                f"<p style='color:{theme.INK_MUTED_58};'>Şu anda havuzda atanmamış ders yok.</p>"
            )
            return

        parts: list[str] = []
        for entry in reports:
            total_open = len(entry["open_slots"])
            if total_open == 0:
                status_text = "hiç uygun saat yok - matematiksel olarak imkansız"
                status_color = theme.CONFLICT_BORDER
            else:
                status_text = f"{total_open} uygun saat var (Oto Ata'yı tekrar çalıştırmak faydalı olabilir)"
                status_color = theme.VALID_BORDER
            parts.append(
                f"<p style='margin-top:16px; margin-bottom:4px;'>"
                f"<b>{_esc(entry['label'])}</b> — {entry['hours_needed']} saat gerekiyor, "
                f"<span style='color:{status_color};'>{_esc(status_text)}</span></p>"
                f"<ul style='margin-top:2px;'>"
            )
            for day_index, day in enumerate(entry["day_summary"]):
                if day_index >= len(day_names):
                    continue
                color = theme.VALID_BORDER if day["open"] else theme.CONFLICT_BORDER
                parts.append(
                    f"<li style='color:{color};'>{_esc(day_names[day_index])}: {_esc(day['text'])}</li>"
                )
            parts.append("</ul>")
        self.text.setHtml("".join(parts))
