"""Haftalık ders programı ızgarası: bir sınıf seçilir, gün x saat
tablosunda hücrelere tıklanarak ders/öğretmen/derslik atanır."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QPushButton,
    QMessageBox,
)

from ..db import Database

CONFLICT_COLOR = QBrush(QColor("#f8b4b4"))
NORMAL_COLOR = QBrush(QColor("#ffffff"))
EMPTY_COLOR = QBrush(QColor("#f5f5f5"))


class CellEditDialog(QDialog):
    def __init__(self, db: Database, current_row, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Ders Ata")

        layout = QFormLayout(self)

        self.subject_combo = QComboBox()
        self.subject_combo.addItem("(Boş)", None)
        for s in db.list_rows("subjects"):
            self.subject_combo.addItem(s["name"], s["id"])

        self.teacher_combo = QComboBox()
        self.teacher_combo.addItem("(Boş)", None)
        for t in db.list_rows("teachers"):
            self.teacher_combo.addItem(t["name"], t["id"])

        self.room_combo = QComboBox()
        self.room_combo.addItem("(Boş)", None)
        for r in db.list_rows("rooms"):
            self.room_combo.addItem(r["name"], r["id"])

        if current_row is not None:
            self._select(self.subject_combo, current_row["subject_id"])
            self._select(self.teacher_combo, current_row["teacher_id"])
            self._select(self.room_combo, current_row["room_id"])

        layout.addRow("Ders:", self.subject_combo)
        layout.addRow("Öğretmen:", self.teacher_combo)
        layout.addRow("Derslik:", self.room_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.clear_button = QPushButton("Hücreyi Temizle")
        self.clear_button.clicked.connect(self._clear_and_accept)
        layout.addRow(self.clear_button)

        self._cleared = False

    def _select(self, combo: QComboBox, value) -> None:
        if value is None:
            combo.setCurrentIndex(0)
            return
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _clear_and_accept(self) -> None:
        self._cleared = True
        self.accept()

    def result_values(self):
        if self._cleared:
            return "clear"
        return (
            self.subject_combo.currentData(),
            self.teacher_combo.currentData(),
            self.room_combo.currentData(),
        )


class ScheduleTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Sınıf:"))
        self.class_combo = QComboBox()
        self.class_combo.currentIndexChanged.connect(self.refresh_grid)
        top_row.addWidget(self.class_combo)
        top_row.addStretch()
        layout.addLayout(top_row)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self.edit_cell)
        layout.addWidget(self.table)

        hint = QLabel("Bir hücreye çift tıklayarak ders/öğretmen/derslik atayın. "
                      "Kırmızı hücreler: aynı öğretmen ya da derslik aynı saatte başka bir sınıfa atanmış (çakışma).")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.reload_classes()

    def reload_classes(self) -> None:
        current_id = self.class_combo.currentData()
        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        for c in self.db.list_rows("class_groups"):
            self.class_combo.addItem(c["name"], c["id"])
        self.class_combo.blockSignals(False)
        if current_id is not None:
            idx = self.class_combo.findData(current_id)
            if idx >= 0:
                self.class_combo.setCurrentIndex(idx)
        self.refresh_grid()

    def refresh_grid(self) -> None:
        day_names = self.db.day_names
        period_count = self.db.period_count
        self.table.setRowCount(period_count)
        self.table.setColumnCount(len(day_names))
        self.table.setHorizontalHeaderLabels(day_names)
        self.table.setVerticalHeaderLabels([f"{p}. Ders" for p in range(1, period_count + 1)])

        class_id = self.class_combo.currentData()
        if class_id is None:
            for row in range(period_count):
                for col in range(len(day_names)):
                    self.table.setItem(row, col, QTableWidgetItem(""))
            return

        schedule = self.db.get_class_schedule(class_id)
        conflicts = self.db.all_conflicting_cells_for_teacher_room()

        for period in range(1, period_count + 1):
            for day in range(len(day_names)):
                entry = schedule.get((day, period))
                item = QTableWidgetItem()
                if entry is not None:
                    lines = [entry["subject_name"] or ""]
                    if entry["teacher_name"]:
                        lines.append(entry["teacher_name"])
                    if entry["room_name"]:
                        lines.append(entry["room_name"])
                    item.setText("\n".join(lines))
                    if (class_id, day, period) in conflicts:
                        item.setBackground(CONFLICT_COLOR)
                    else:
                        item.setBackground(NORMAL_COLOR)
                else:
                    item.setBackground(EMPTY_COLOR)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(period - 1, day, item)

        self.table.resizeRowsToContents()

    def edit_cell(self, row: int, col: int) -> None:
        class_id = self.class_combo.currentData()
        if class_id is None:
            QMessageBox.information(self, "Sınıf seçin", "Önce bir sınıf seçmelisiniz.")
            return

        period = row + 1
        day = col
        schedule = self.db.get_class_schedule(class_id)
        current_row = schedule.get((day, period))

        dialog = CellEditDialog(self.db, current_row, self)
        if dialog.exec() != QDialog.Accepted:
            return

        values = dialog.result_values()
        if values == "clear":
            self.db.clear_schedule_cell(class_id, day, period)
            self.refresh_grid()
            return

        subject_id, teacher_id, room_id = values
        conflicts = self.db.find_conflicts(class_id, day, period, teacher_id, room_id)
        if conflicts:
            names = ", ".join(sorted({c["class_name"] for c in conflicts}))
            proceed = QMessageBox.question(
                self,
                "Çakışma bulundu",
                f"Bu öğretmen ve/veya derslik aynı saatte şu sınıf(lar)da da kullanılıyor: {names}.\n"
                "Yine de kaydetmek istiyor musunuz?",
            )
            if proceed != QMessageBox.Yes:
                return

        self.db.set_schedule_cell(class_id, day, period, subject_id, teacher_id, room_id)
        self.refresh_grid()
