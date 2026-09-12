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
    QScrollArea,
    QCheckBox,
    QWidget,
    QVBoxLayout,
    QLabel,
    QMessageBox,
)

from ..db import (
    Database,
    TYPE_CLASS,
    TYPE_ONE_ON_ONE,
    TYPE_COACHING,
    TYPE_DEPARTMENT,
    TYPE_PROBLEM_SOLVING,
    TYPE_TRIAL,
    TYPE_STUDY,
    TEACHERLESS_TYPES,
    LESSON_TYPE_LABELS,
)

TYPE_ORDER = [
    TYPE_CLASS, TYPE_ONE_ON_ONE, TYPE_COACHING, TYPE_DEPARTMENT,
    TYPE_PROBLEM_SOLVING, TYPE_TRIAL, TYPE_STUDY,
]


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

        self._teacher_subject_ids: dict[int, list[int]] = {}
        self.teacher_combo = QComboBox()
        # Deneme/Etüt öğretmensiz de atanabildiği için listenin başına
        # "(Öğretmensiz)" seçeneği konur; bu seçenek sadece o tiplerde
        # geçerlidir (bkz. _update_visible_fields / _on_accept).
        self.teacher_combo.addItem("(Öğretmensiz)", None)
        for t in db.list_teachers():
            self.teacher_combo.addItem(t["name"], t["id"])
            self._teacher_subject_ids[t["id"]] = db.get_teacher_subject_ids(t["id"])
        if self.teacher_combo.count() > 1:
            self.teacher_combo.setCurrentIndex(1)
        self.teacher_label = QLabel("Öğretmen:")
        layout.addRow(self.teacher_label, self.teacher_combo)

        # Zümre: aynı saatte bir araya gelen öğretmenlerin toplantısı -
        # her öğretmen ayrı bir kutucukla işaretlenir, hangilerinin
        # eklendiği tek bakışta görülür (liste seçiminden farklı olarak).
        self.teacher_checks: dict[int, QCheckBox] = {}
        teachers_container = QWidget()
        teachers_container_layout = QVBoxLayout(teachers_container)
        teachers_container_layout.setContentsMargins(4, 4, 4, 4)
        teachers_container_layout.setSpacing(2)
        for t in db.list_teachers():
            cb = QCheckBox(f"{t['name']} ({t['subject_area'] or '-'})")
            self.teacher_checks[t["id"]] = cb
            teachers_container_layout.addWidget(cb)
        teachers_container_layout.addStretch()
        self.teachers_scroll = QScrollArea()
        self.teachers_scroll.setWidgetResizable(True)
        self.teachers_scroll.setMaximumHeight(160)
        self.teachers_scroll.setWidget(teachers_container)
        self.teachers_list_label = QLabel("Katılacak Öğretmenler:")
        layout.addRow(self.teachers_list_label, self.teachers_scroll)

        self.subject_combo = QComboBox()
        self.subject_combo.addItem("(Yok)", None)
        for s in db.list_rows("subjects"):
            self.subject_combo.addItem(s["name"], s["id"])
        self.subject_label = QLabel("Ders/Branş:")
        layout.addRow(self.subject_label, self.subject_combo)

        self.class_combo = QComboBox()
        # Deneme/Etüt sınıfsız da (ör. sadece bir öğretmenin etüdü) olabilir.
        self.class_combo.addItem("(Yok)", None)
        for c in db.list_class_groups():
            self.class_combo.addItem(c["name"], c["id"])
        if self.class_combo.count() > 1:
            self.class_combo.setCurrentIndex(1)
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
        self.teacher_combo.currentIndexChanged.connect(self._apply_teacher_subject_area)
        self._update_visible_fields()
        self._apply_teacher_subject_area()

    def _apply_teacher_subject_area(self) -> None:
        """Öğretmen seçilince 'Ders/Branş' alanını o öğretmenin branşıyla
        otomatik doldurur (kullanıcı isterse sonradan değiştirebilir).
        Öğretmenin tek branşı varsa doğrudan seçilir; birden fazla
        branşı varsa hangisi kastedildiği belirsiz olduğu için elle
        seçime bırakılır."""
        subject_ids = self._teacher_subject_ids.get(self.teacher_combo.currentData()) or []
        if len(subject_ids) != 1:
            return
        idx = self.subject_combo.findData(subject_ids[0])
        if idx >= 0:
            self.subject_combo.setCurrentIndex(idx)

    def _update_visible_fields(self) -> None:
        t = self.type_combo.currentData()
        is_class = t == TYPE_CLASS
        is_one_on_one = t == TYPE_ONE_ON_ONE
        is_coaching = t == TYPE_COACHING
        is_department = t == TYPE_DEPARTMENT
        is_problem = t == TYPE_PROBLEM_SOLVING
        # Deneme/Etüt: öğretmen ZORUNLU değil, sınıf ise seçilebilir -
        # böylece bir deneme sınavı ya da etüt, hocası olmadan doğrudan
        # sınıfın satırına yerleştirilebilir (kullanıcı isteği).
        is_teacherless = t in TEACHERLESS_TYPES

        single_teacher = not is_department
        self.teacher_label.setVisible(single_teacher)
        self.teacher_combo.setVisible(single_teacher)
        self.teacher_label.setText("Öğretmen (isteğe bağlı):" if is_teacherless else "Öğretmen:")
        self.teachers_list_label.setVisible(is_department)
        self.teachers_scroll.setVisible(is_department)

        show_subject = is_class or is_one_on_one or is_problem or is_teacherless
        self.subject_label.setVisible(show_subject)
        self.subject_combo.setVisible(show_subject)

        show_class = is_class or is_teacherless
        self.class_label.setVisible(show_class)
        self.class_combo.setVisible(show_class)
        self.class_label.setText("Sınıf (isteğe bağlı):" if is_teacherless else "Sınıf:")

        show_student = is_one_on_one or is_coaching
        self.student_label.setVisible(show_student)
        self.student_combo.setVisible(show_student)

        show_room = is_class or is_one_on_one or is_department or is_teacherless
        self.room_label.setVisible(show_room)
        self.room_combo.setVisible(show_room)

    def _on_accept(self) -> None:
        t = self.type_combo.currentData()
        hours = self.hours_spin.value()
        subject_id = self.subject_combo.currentData() if self.subject_combo.isVisible() else None
        room_id = self.room_combo.currentData() if self.room_combo.isVisible() else None

        if t == TYPE_DEPARTMENT:
            teacher_ids = [tid for tid, cb in self.teacher_checks.items() if cb.isChecked()]
            if not teacher_ids:
                QMessageBox.warning(self, "Eksik bilgi", "En az bir öğretmen seçmelisiniz.")
                return
            # Her "saat" ayrı bir buluşma: aynı buluşmadaki tüm öğretmenlerin
            # blokları ortak bir zumre_group_id ile bağlanır ki Ana Program'da
            # tek bir ders olarak görünüp birine sürüklenince hepsi aynı
            # gün/saate yerleşsin (bkz. db.add_zumre_group).
            for _ in range(hours):
                self.db.add_zumre_group(teacher_ids, subject_id=subject_id, room_id=room_id)
            self.accept()
            return

        teacher_id = self.teacher_combo.currentData()
        is_teacherless = t in TEACHERLESS_TYPES
        if teacher_id is None and not is_teacherless:
            QMessageBox.warning(self, "Eksik bilgi", "Öğretmen seçmelisiniz.")
            return

        class_group_id = self.class_combo.currentData() if self.class_combo.isVisible() else None
        student_id = self.student_combo.currentData() if t in (TYPE_ONE_ON_ONE, TYPE_COACHING) else None

        if t == TYPE_CLASS and class_group_id is None:
            QMessageBox.warning(self, "Eksik bilgi", "Sınıf seçmelisiniz (yoksa önce bir sınıf tanımlayın).")
            return
        # Blok, programda ya bir öğretmenin ya da bir sınıfın satırında
        # görünerek yerleştirilir - ikisi de boşsa hiçbir satıra düşmez ve
        # havuzdan çıkarılamaz hale gelir.
        if is_teacherless and teacher_id is None and class_group_id is None:
            QMessageBox.warning(
                self, "Eksik bilgi",
                "Deneme/Etüt için en az bir sınıf ya da bir öğretmen seçmelisiniz - "
                "ders programda bunlardan birinin satırına yerleştirilir.",
            )
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
