"""'Ders Ekle' diyaloğu: tip seçilir, ilgili alanlar doldurulur, haftalık
saat sayısı kadar 1'er saatlik ders bloğu oluşturulup atanmamış dersler
havuzuna düşürülür."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QComboBox,
    QSpinBox,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QMessageBox,
)
from PySide6.QtCore import Qt

from ..db import (
    Database,
    TYPE_CLASS,
    TYPE_ONE_ON_ONE,
    TYPE_COACHING,
    TYPE_DEPARTMENT,
    TYPE_PROBLEM_SOLVING,
    LESSON_TYPE_LABELS,
)

TYPE_ORDER = [TYPE_CLASS, TYPE_ONE_ON_ONE, TYPE_COACHING, TYPE_DEPARTMENT, TYPE_PROBLEM_SOLVING]


class AddLessonDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Ders Ekle")
        self.resize(420, 420)

        layout = QFormLayout(self)

        self.type_combo = QComboBox()
        for t in TYPE_ORDER:
            self.type_combo.addItem(LESSON_TYPE_LABELS[t], t)
        layout.addRow("Ders Tipi:", self.type_combo)

        self.teacher_combo = QComboBox()
        for t in db.list_teachers():
            self.teacher_combo.addItem(t["name"], t["id"])
        self.teacher_label = QLabel("Öğretmen:")
        layout.addRow(self.teacher_label, self.teacher_combo)

        self.teachers_list = QListWidget()
        self.teachers_list.setSelectionMode(QListWidget.MultiSelection)
        for t in db.list_teachers():
            item = QListWidgetItem(f"{t['name']} ({t['subject_area'] or '-'})")
            item.setData(Qt.UserRole, t["id"])
            self.teachers_list.addItem(item)
        self.teachers_list_label = QLabel("Katılacak Öğretmenler:")
        layout.addRow(self.teachers_list_label, self.teachers_list)

        self.subject_combo = QComboBox()
        self.subject_combo.addItem("(Yok)", None)
        for s in db.list_rows("subjects"):
            self.subject_combo.addItem(s["name"], s["id"])
        self.subject_label = QLabel("Ders/Branş:")
        layout.addRow(self.subject_label, self.subject_combo)

        self.class_combo = QComboBox()
        for c in db.list_rows("class_groups"):
            self.class_combo.addItem(c["name"], c["id"])
        self.class_label = QLabel("Sınıf:")
        layout.addRow(self.class_label, self.class_combo)

        self.student_combo = QComboBox()
        for s in db.list_students():
            self.student_combo.addItem(s["name"], s["id"])
        self.student_label = QLabel("Öğrenci:")
        layout.addRow(self.student_label, self.student_combo)

        self.room_combo = QComboBox()
        self.room_combo.addItem("(Yok)", None)
        for r in db.list_rows("rooms"):
            self.room_combo.addItem(r["name"], r["id"])
        self.room_label = QLabel("Derslik:")
        layout.addRow(self.room_label, self.room_combo)

        self.hours_spin = QSpinBox()
        self.hours_spin.setRange(1, 20)
        self.hours_spin.setValue(1)
        layout.addRow("Haftalık Saat:", self.hours_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.type_combo.currentIndexChanged.connect(self._update_visible_fields)
        self._update_visible_fields()

    def _update_visible_fields(self) -> None:
        t = self.type_combo.currentData()
        is_class = t == TYPE_CLASS
        is_one_on_one = t == TYPE_ONE_ON_ONE
        is_coaching = t == TYPE_COACHING
        is_department = t == TYPE_DEPARTMENT
        is_problem = t == TYPE_PROBLEM_SOLVING

        single_teacher = not is_department
        self.teacher_label.setVisible(single_teacher)
        self.teacher_combo.setVisible(single_teacher)
        self.teachers_list_label.setVisible(is_department)
        self.teachers_list.setVisible(is_department)

        show_subject = is_class or is_one_on_one or is_problem
        self.subject_label.setVisible(show_subject)
        self.subject_combo.setVisible(show_subject)

        self.class_label.setVisible(is_class)
        self.class_combo.setVisible(is_class)

        show_student = is_one_on_one or is_coaching
        self.student_label.setVisible(show_student)
        self.student_combo.setVisible(show_student)

        show_room = is_class or is_one_on_one or is_department
        self.room_label.setVisible(show_room)
        self.room_combo.setVisible(show_room)

    def _on_accept(self) -> None:
        t = self.type_combo.currentData()
        hours = self.hours_spin.value()
        subject_id = self.subject_combo.currentData() if self.subject_combo.isVisible() else None
        room_id = self.room_combo.currentData() if self.room_combo.isVisible() else None

        if t == TYPE_DEPARTMENT:
            teacher_ids = [item.data(Qt.UserRole) for item in self.teachers_list.selectedItems()]
            if not teacher_ids:
                QMessageBox.warning(self, "Eksik bilgi", "En az bir öğretmen seçmelisiniz.")
                return
            for teacher_id in teacher_ids:
                self.db.add_lesson_blocks(
                    t, hours, teacher_id=teacher_id, subject_id=subject_id, room_id=room_id
                )
            self.accept()
            return

        teacher_id = self.teacher_combo.currentData()
        if teacher_id is None:
            QMessageBox.warning(self, "Eksik bilgi", "Öğretmen seçmelisiniz.")
            return

        class_group_id = self.class_combo.currentData() if t == TYPE_CLASS else None
        student_id = self.student_combo.currentData() if t in (TYPE_ONE_ON_ONE, TYPE_COACHING) else None

        if t == TYPE_CLASS and class_group_id is None:
            QMessageBox.warning(self, "Eksik bilgi", "Önce en az bir sınıf tanımlamalısınız.")
            return
        if t in (TYPE_ONE_ON_ONE, TYPE_COACHING) and student_id is None:
            QMessageBox.warning(self, "Eksik bilgi", "Önce en az bir öğrenci tanımlamalısınız.")
            return

        self.db.add_lesson_blocks(
            t,
            hours,
            teacher_id=teacher_id,
            subject_id=subject_id,
            class_group_id=class_group_id,
            student_id=student_id,
            room_id=room_id,
        )
        self.accept()
