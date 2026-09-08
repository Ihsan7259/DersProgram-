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
    QComboBox,
    QMessageBox,
    QFormLayout,
)

from ..db import Database
from .. import scheduling
from .widgets import section_title as _section_title, divider as _divider
from . import theme


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

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Öğrenci ara...")
        left_layout.addWidget(self.search_edit)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("İsme Göre (A-Z)", "name_asc")
        self.sort_combo.addItem("İsme Göre (Z-A)", "name_desc")
        self.sort_combo.addItem("Son Ödeme Tarihine Göre (Yeniden Eskiye)", "last_payment_desc")
        self.sort_combo.addItem("Son Ödeme Tarihine Göre (Eskiden Yeniye)", "last_payment_asc")
        self.sort_combo.addItem("İlk Ödeme Tarihine Göre (Yeniden Eskiye)", "first_payment_desc")
        self.sort_combo.addItem("İlk Ödeme Tarihine Göre (Eskiden Yeniye)", "first_payment_asc")
        left_layout.addWidget(self.sort_combo)

        self.student_list = QListWidget()
        left_layout.addWidget(self.student_list, 1)
        left.setMaximumWidth(260)
        layout.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)

        right_layout.addWidget(_section_title("Ödeme Bilgileri"))
        self.fees_label = QLabel("Bir öğrenci seçin.")
        right_layout.addWidget(self.fees_label)

        right_layout.addWidget(_divider())

        # ---------- birebir paketi ----------
        right_layout.addWidget(_section_title("Birebir Paketi"))
        package_row = QHBoxLayout()
        package_row.addWidget(QLabel("Paket Saati:"))
        self.package_spin = QDoubleSpinBox()
        self.package_spin.setRange(0, 10_000)
        self.package_spin.setDecimals(0)  # saat tam sayı olsun - virgüllü (ondalıklı) görünmesin
        self.package_spin.setSuffix(" saat")
        package_row.addWidget(self.package_spin)
        self.save_package_button = QPushButton("Kaydet")
        self.save_package_button.setObjectName("outlineButton")
        package_row.addWidget(self.save_package_button)
        package_row.addStretch()
        right_layout.addLayout(package_row)
        self.ledger_label = QLabel()
        self.ledger_label.setTextFormat(Qt.RichText)
        right_layout.addWidget(self.ledger_label)

        right_layout.addWidget(_divider())

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
        self.save_package_button.clicked.connect(self.handle_save_package)
        self.search_edit.textChanged.connect(self.refresh_students)
        self.sort_combo.currentIndexChanged.connect(self.refresh_students)

        self.refresh_students()

    def _sorted_filtered_students(self) -> list:
        """Arama kutusuna ve sıralama seçimine göre süzülmüş/sıralanmış
        öğrenci listesi - isme göre (A-Z/Z-A) ya da ilk/son ödeme
        tarihine göre (eskiden yeniye/yeniden eskiye). Hiç ödemesi
        olmayan öğrenciler, tarih bazlı sıralamalarda seçilen yönden
        bağımsız olarak her zaman listenin sonunda kalır."""
        students = list(self.db.list_students())

        query = self.search_edit.text().strip().lower()
        if query:
            students = [s for s in students if query in s["name"].lower()]

        sort_key = self.sort_combo.currentData()
        if sort_key == "name_desc":
            students.sort(key=lambda s: s["name"].lower(), reverse=True)
        elif sort_key in ("last_payment_desc", "last_payment_asc", "first_payment_desc", "first_payment_asc"):
            want_first = sort_key.startswith("first_payment")
            reverse = sort_key.endswith("_desc")
            dates: dict[int, str] = {}
            for s in students:
                payments = self.db.list_payments(s["id"])
                dates[s["id"]] = (payments[0]["payment_date"] if want_first else payments[-1]["payment_date"]) if payments else ""
            with_date = sorted((s for s in students if dates[s["id"]]), key=lambda s: dates[s["id"]], reverse=reverse)
            without_date = [s for s in students if not dates[s["id"]]]
            students = with_date + without_date
        else:
            students.sort(key=lambda s: s["name"].lower())
        return students

    def refresh_students(self) -> None:
        previously_selected = self.selected_student_id
        self.student_list.blockSignals(True)
        self.student_list.clear()
        select_item = None
        for student in self._sorted_filtered_students():
            item = QListWidgetItem(student["name"])
            item.setData(Qt.UserRole, student["id"])
            self.student_list.addItem(item)
            if student["id"] == previously_selected:
                select_item = item
        if select_item is not None:
            select_item.setSelected(True)
        else:
            self.selected_student_id = None
        self.student_list.blockSignals(False)
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
            self.ledger_label.setText("")
            self.package_spin.blockSignals(True)
            self.package_spin.setValue(0)
            self.package_spin.blockSignals(False)
            return

        student = self.db.get_student(self.selected_student_id)
        program_fee = student["total_program_fee"]
        one_on_one_fee = student["total_one_on_one_fee"]
        total_fee = program_fee + one_on_one_fee
        self.fees_label.setText(
            f"Program Ücreti: {program_fee:.2f} TL   |   Birebir Ücreti: {one_on_one_fee:.2f} TL   |   Toplam: {total_fee:.2f} TL"
        )

        ledger = scheduling.compute_one_on_one_ledger(self.db, self.selected_student_id)
        self.package_spin.blockSignals(True)
        self.package_spin.setValue(ledger["package_hours"])
        self.package_spin.blockSignals(False)
        debt = ledger["debt_hours"]
        debt_style = f"color:{theme.CONFLICT_BORDER}; font-weight:700;" if debt > 0 else ""
        self.ledger_label.setText(
            f"Yapılan: {ledger['occurred_hours']:.0f} saat   |   "
            f"Ödenmiş: {ledger['paid_hours']:.0f} saat   |   "
            f"Kalan: {ledger['remaining_hours']:.0f} saat   |   "
            f"<span style='{debt_style}'>Borçlu: {debt:.0f} saat</span>"
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

    def handle_save_package(self) -> None:
        if self.selected_student_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce bir öğrenci seçin.")
            return
        self.db.update_one_on_one_package(self.selected_student_id, self.package_spin.value())
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
