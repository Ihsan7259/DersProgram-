from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

from .. import scheduling
from ..db import Database
from . import theme


class MakeupLessonsDialog(QDialog):
    # Ana Program > "Geçen Haftadan Telafi": seçili öğretmenin geçen haftaki
    # derslerinden seçilenler bu haftanın havuzuna (tek haftalık kopya) eklenir.
    def __init__(
        self,
        db: Database,
        source_week: _dt.date,
        teacher_id: int,
        teacher_name: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Geçen Haftadan Telafi Dersi")
        self.setMinimumSize(520, 390)
        target_week = source_week + _dt.timedelta(days=7)

        layout = QVBoxLayout(self)
        description = QLabel(
            f"{teacher_name} öğretmeninin {scheduling.week_label(source_week, len(db.day_names))} "
            "haftasındaki derslerinden telafi edilecekleri seçin. Seçilenler "
            f"{scheduling.week_label(target_week, len(db.day_names))} haftasının 'Atanmamış Dersler' "
            "havuzuna eklenir; önceki ve sonraki haftaların programı değişmez."
        )
        description.setWordWrap(True)
        description.setStyleSheet(f"color:{theme.INK_MUTED_52};")
        layout.addWidget(description)

        self.lesson_list = QListWidget()
        layout.addWidget(self.lesson_list, 1)

        schedule, pool = scheduling.get_week_view(db, source_week)
        all_blocks = [block for blocks in schedule.values() for block in blocks] + pool
        # Zümre/toplantı grupları tek satır olarak gösterilir.
        by_group_id = {}
        for block in all_blocks:
            if block.zumre_group_id is not None:
                by_group_id.setdefault(block.zumre_group_id, []).append(block)
        groups = {}
        for blocks in schedule.values():
            for block in blocks:
                if block.teacher_id == teacher_id:
                    key = ("group", block.zumre_group_id) if block.zumre_group_id is not None else ("block", block.id)
                    groups.setdefault(key, by_group_id.get(block.zumre_group_id, [block]))
        for block in pool:
            if block.teacher_id == teacher_id:
                key = ("group", block.zumre_group_id) if block.zumre_group_id is not None else ("block", block.id)
                groups.setdefault(key, by_group_id.get(block.zumre_group_id, [block]))

        for key, matching_members in groups.items():
            members = by_group_id.get(key[1], matching_members) if key[0] == "group" else matching_members
            representative = min((block for block in matching_members if block.teacher_id == teacher_id), key=lambda block: block.id)
            source_ids = [representative.id]
            if representative.day is not None:
                lesson_date = source_week + _dt.timedelta(days=representative.day)
                day_label = (
                    f"{lesson_date.strftime('%d.%m.%Y')} {db.day_names[representative.day]}, "
                    f"{representative.period}. ders"
                )
            else:
                day_label = "Geçen haftanın atanmamış havuzunda"
            label = f"{day_label} — {representative.pool_label()}"
            if len(members) > 1:
                label += f" ({len(members)} öğretmen)"
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, source_ids)
            item.setToolTip(representative.pool_label())
            self.lesson_list.addItem(item)

        if self.lesson_list.count() == 0:
            empty = QListWidgetItem("Geçen hafta bu öğretmene ait aktarılabilecek ders bulunamadı.")
            empty.setFlags(Qt.NoItemFlags)
            self.lesson_list.addItem(empty)

        buttons = QDialogButtonBox()
        self.add_button = buttons.addButton("Seçilenleri Bu Haftaya Ekle", QDialogButtonBox.AcceptRole)
        cancel_button = buttons.addButton("Vazgeç", QDialogButtonBox.RejectRole)
        self.add_button.setEnabled(False)
        self.lesson_list.itemChanged.connect(self._update_add_button)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        cancel_button.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def selected_source_ids(self) -> list[int]:
        selected = []
        for index in range(self.lesson_list.count()):
            item = self.lesson_list.item(index)
            if item.checkState() == Qt.Checked:
                selected.extend(item.data(Qt.UserRole) or [])
        return list(dict.fromkeys(selected))

    def _update_add_button(self, _item) -> None:
        self.add_button.setEnabled(bool(self.selected_source_ids()))
