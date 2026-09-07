"""Ödemeler: öğrenci seç, ücretlerini ve yaptığı ödemeleri gör, yeni
ödeme ekle, kalan borcu otomatik hesapla.

Program/birebir ücretleri Öğrenciler sekmesinden düzenlenir; burada
sadece görüntülenir."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QDoubleSpinBox,
    QDateEdit,
    QLineEdit,
    QMessageBox,
    QFormLayout,
)

from ..db import Database
from .widgets import section_title as _section_title, divider as _divider


class PaymentsTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.selected_student_id: int | None = None

        layout = QHBoxLayout(self)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(_section_title("Öğrenci Listesi"))
        self.student_list = QListWidget()
        left_layout.addWidget(self.student_list, 1)
        left.setMaximumWidth(260)
        layout.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        right_layout.addWidget(_section_title("Ödeme Bilgileri"))
        self.fees_label = QLabel("Bir öğrenci seçin.")
        right_layout.addWidget(self.fees_label)

        self.payments_table = QTableWidget(0, 3)
        self.payments_table.setHorizontalHeaderLabels(["Tarih", "Tutar", "Not"])
        self.payments_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.payments_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.payments_table.setSelectionBehavior(QTableWidget.SelectRows)
        right_layout.addWidget(self.payments_table, 1)

        right_layout.addWidget(_divider())
        right_layout.addWidget(_section_title("Yeni Ödeme"))
        form = QFormLayout()
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0, 10_000_000)
        self.amount_spin.setSuffix(" TL")
        form.addRow("Tutar:", self.amount_spin)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        form.addRow("Tarih:", self.date_edit)
        self.note_edit = QLineEdit()
        form.addRow("Not:", self.note_edit)
        right_layout.addLayout(form)

        button_row = QHBoxLayout()
        self.add_payment_button = QPushButton("Ödeme Ekle")
        self.add_payment_button.setObjectName("primaryButton")
        self.delete_payment_button = QPushButton("Seçili Ödemeyi Sil")
        self.delete_payment_button.setObjectName("dangerButton")
        button_row.addWidget(self.add_payment_button)
        button_row.addWidget(self.delete_payment_button)
        right_layout.addLayout(button_row)

        self.balance_label = QLabel()
        font = self.balance_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        self.balance_label.setFont(font)
        right_layout.addWidget(self.balance_label)

        layout.addWidget(right, 1)

        self.student_list.itemSelectionChanged.connect(self.handle_student_selected)
        self.add_payment_button.clicked.connect(self.handle_add_payment)
        self.delete_payment_button.clicked.connect(self.handle_delete_payment)

        self.refresh_students()

    def refresh_students(self) -> None:
        self.student_list.clear()
        for student in self.db.list_students():
            item = QListWidgetItem(student["name"])
            item.setData(Qt.UserRole, student["id"])
            self.student_list.addItem(item)
        self.refresh_detail()

    def handle_student_selected(self) -> None:
        items = self.student_list.selectedItems()
        self.selected_student_id = items[0].data(Qt.UserRole) if items else None
        self.refresh_detail()

    def refresh_detail(self) -> None:
        if self.selected_student_id is None:
            self.fees_label.setText("Bir öğrenci seçin.")
            self.payments_table.setRowCount(0)
            self.balance_label.setText("")
            return

        student = self.db.get_student(self.selected_student_id)
        program_fee = student["total_program_fee"]
        one_on_one_fee = student["total_one_on_one_fee"]
        total_fee = program_fee + one_on_one_fee
        self.fees_label.setText(
            f"Program Ücreti: {program_fee:.2f} TL   |   Birebir Ücreti: {one_on_one_fee:.2f} TL   |   Toplam: {total_fee:.2f} TL"
        )

        payments = self.db.list_payments(self.selected_student_id)
        self.payments_table.setRowCount(len(payments))
        for r, p in enumerate(payments):
            date_item = QTableWidgetItem(p["payment_date"])
            date_item.setData(Qt.UserRole, p["id"])
            self.payments_table.setItem(r, 0, date_item)
            self.payments_table.setItem(r, 1, QTableWidgetItem(f"{p['amount']:.2f} TL"))
            self.payments_table.setItem(r, 2, QTableWidgetItem(p["note"] or ""))

        paid = self.db.total_paid(self.selected_student_id)
        remaining = total_fee - paid
        self.balance_label.setText(f"Ödenen: {paid:.2f} TL   |   Kalan Borç: {remaining:.2f} TL")

    def handle_add_payment(self) -> None:
        if self.selected_student_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce bir öğrenci seçin.")
            return
        amount = self.amount_spin.value()
        if amount <= 0:
            QMessageBox.warning(self, "Eksik bilgi", "Tutar sıfırdan büyük olmalı.")
            return
        self.db.add_payment(
            self.selected_student_id,
            amount,
            self.date_edit.date().toString("yyyy-MM-dd"),
            self.note_edit.text().strip(),
        )
        self.amount_spin.setValue(0)
        self.note_edit.clear()
        self.refresh_detail()

    def handle_delete_payment(self) -> None:
        items = self.payments_table.selectedItems()
        if not items:
            QMessageBox.information(self, "Seçim yok", "Silinecek ödemeyi listeden seçin.")
            return
        row = items[0].row()
        payment_id = self.payments_table.item(row, 0).data(Qt.UserRole)
        self.db.delete_payment(payment_id)
        self.refresh_detail()
