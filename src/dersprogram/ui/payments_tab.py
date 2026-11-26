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
    QFileDialog,
)

from ..db import Database
from .. import scheduling
from .widgets import section_title as _section_title, divider as _divider
from . import theme


def write_one_on_one_history_workbook(
    path: str,
    student_name: str,
    headers: list[str],
    rows: list[list[str]],
) -> None:
    # Ödemeler > "Geçmiş Birebir Dersleri" > Excel'e Aktar.
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Birebir Ders Geçmişi"
    sheet["A1"] = f"{student_name} - Birebir Ders Geçmişi"
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append([])
    sheet.append(headers)
    header_row = sheet.max_row
    for cell in sheet[header_row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E5F")
        cell.alignment = Alignment(horizontal="center")
    for row in rows:
        sheet.append(row)
    for column, header in enumerate(headers, start=1):
        values = [len(str(header))]
        values.extend(len(str(row[column - 1])) for row in rows)
        sheet.column_dimensions[get_column_letter(column)].width = min(42, max(12, max(values) + 3))
    sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
    if rows:
        sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(len(headers))}{header_row + len(rows)}"
    workbook.save(path)


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
        # Sağ taraf ikiye bölünür: solda ödeme bilgileri, sağda geçmiş birebir dersleri.
        detail_splitter = QSplitter(Qt.Horizontal)
        payment_panel = QWidget()
        payment_layout = QVBoxLayout(payment_panel)
        payment_layout.setContentsMargins(0, 0, 0, 0)

        payment_layout.addWidget(_section_title("Ödeme Bilgileri"))
        self.fees_label = QLabel("Bir öğrenci seçin.")
        payment_layout.addWidget(self.fees_label)

        payment_layout.addWidget(_divider())

        # ---------- birebir paketi ----------
        payment_layout.addWidget(_section_title("Birebir Paketi"))
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
        payment_layout.addLayout(package_row)
        self.ledger_label = QLabel()
        self.ledger_label.setTextFormat(Qt.RichText)
        payment_layout.addWidget(self.ledger_label)

        payment_layout.addWidget(_divider())

        self.payments_table = QTableWidget(0, 3)
        self.payments_table.setHorizontalHeaderLabels(["Tarih", "Tutar", "Not"])
        self.payments_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.payments_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.payments_table.setSelectionBehavior(QTableWidget.SelectRows)
        payment_layout.addWidget(self.payments_table, 1)

        payment_layout.addWidget(_divider())
        payment_layout.addWidget(_section_title("Yeni Ödeme"))
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
        payment_layout.addLayout(form)

        button_row = QHBoxLayout()
        self.add_payment_button = QPushButton("Ödeme Ekle")
        self.add_payment_button.setObjectName("primaryButton")
        self.delete_payment_button = QPushButton("Seçili Ödemeyi Sil")
        self.delete_payment_button.setObjectName("dangerButton")
        button_row.addWidget(self.add_payment_button)
        button_row.addWidget(self.delete_payment_button)
        payment_layout.addLayout(button_row)

        self.balance_label = QLabel()
        font = self.balance_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        self.balance_label.setFont(font)
        payment_layout.addWidget(self.balance_label)

        history_panel = QWidget()
        history_layout = QVBoxLayout(history_panel)
        history_layout.setContentsMargins(0, 0, 0, 0)
        history_header = QHBoxLayout()
        history_header.addWidget(_section_title("Geçmiş Birebir Dersleri"))
        history_header.addStretch()
        self.export_one_on_one_button = QPushButton("Excel'e Aktar")
        self.export_one_on_one_button.setObjectName("outlineButton")
        self.export_one_on_one_button.setEnabled(False)
        self.export_one_on_one_button.clicked.connect(self.handle_export_one_on_one_history)
        history_header.addWidget(self.export_one_on_one_button)
        history_layout.addLayout(history_header)
        self.one_on_one_history_summary = QLabel("Bir öğrenci seçin.")
        history_layout.addWidget(self.one_on_one_history_summary)
        self.one_on_one_history_table = QTableWidget(0, 6)
        self.one_on_one_history_table.setHorizontalHeaderLabels(["Tarih", "Gün", "Saat", "Ders", "Öğretmen", "Derslik"])
        self.one_on_one_history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.one_on_one_history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.one_on_one_history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.one_on_one_history_table.setAlternatingRowColors(True)
        history_layout.addWidget(self.one_on_one_history_table, 1)

        detail_splitter.addWidget(payment_panel)
        detail_splitter.addWidget(history_panel)
        detail_splitter.setStretchFactor(0, 1)
        detail_splitter.setStretchFactor(1, 1)
        detail_splitter.setSizes([1, 1])
        right_layout.addWidget(detail_splitter)

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
        students = self._sorted_filtered_students()
        self.student_list.blockSignals(True)
        self.student_list.clear()
        select_item = None
        for student in students:
            item = QListWidgetItem(student["name"])
            item.setData(Qt.UserRole, student["id"])
            self.student_list.addItem(item)
            if student["id"] == previously_selected:
                select_item = item
        # Aramada tek öğrenci kaldıysa o seçilir.
        if select_item is None and self.search_edit.text().strip() and len(students) == 1:
            select_item = self.student_list.item(0)
        if select_item is not None:
            select_item.setSelected(True)
            self.selected_student_id = select_item.data(Qt.UserRole)
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
            self.one_on_one_history_summary.setText("Bir öğrenci seçin.")
            self.one_on_one_history_table.setRowCount(0)
            self.export_one_on_one_button.setEnabled(False)
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

        occurrences = scheduling.list_one_on_one_occurrences(self.db, self.selected_student_id)
        self.one_on_one_history_summary.setText(f"Geçmiş toplam: {len(occurrences)} birebir ders")
        self.export_one_on_one_button.setEnabled(bool(occurrences))
        self.one_on_one_history_table.setRowCount(len(occurrences))
        day_names = self.db.day_names
        for row_index, occurrence in enumerate(occurrences):
            date_item = QTableWidgetItem(occurrence.date.strftime("%d.%m.%Y"))
            date_item.setData(Qt.UserRole, occurrence.date.isoformat())
            cells = (
                date_item,
                QTableWidgetItem(day_names[occurrence.date.weekday()] if occurrence.date.weekday() < len(day_names) else ""),
                QTableWidgetItem(
                    f"{occurrence.period}. saat"
                    + (f" ({self.db.period_time_label(occurrence.period)})" if self.db.period_time_label(occurrence.period) else "")
                ),
                QTableWidgetItem(occurrence.subject_name),
                QTableWidgetItem(occurrence.teacher_name),
                QTableWidgetItem(occurrence.room_name),
            )
            for column, cell in enumerate(cells):
                self.one_on_one_history_table.setItem(row_index, column, cell)

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

    def handle_export_one_on_one_history(self) -> None:
        if self.selected_student_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce bir öğrenci seçin.")
            return
        student = self.db.get_student(self.selected_student_id)
        occurrences = scheduling.list_one_on_one_occurrences(self.db, self.selected_student_id)
        if not occurrences:
            QMessageBox.information(self, "Geçmiş ders yok", "Bu öğrencinin aktarılacak geçmiş birebir dersi yok.")
            return
        headers = ["Tarih", "Gün", "Saat", "Ders", "Öğretmen", "Derslik"]
        day_names = self.db.day_names
        rows = []
        for occurrence in occurrences:
            day_name = day_names[occurrence.date.weekday()] if occurrence.date.weekday() < len(day_names) else ""
            period_time = self.db.period_time_label(occurrence.period)
            period_text = f"{occurrence.period}. saat"
            if period_time:
                period_text += f" ({period_time})"
            rows.append([
                occurrence.date.strftime("%d.%m.%Y"), day_name, period_text,
                occurrence.subject_name, occurrence.teacher_name, occurrence.room_name,
            ])
        safe_name = "".join(
            character for character in student["name"]
            if character.isalnum() or character in (" ", "-", "_")
        ).strip().replace(" ", "_")
        default_name = f"birebir_gecmisi_{safe_name or self.selected_student_id}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Birebir Ders Geçmişini Excel'e Aktar", default_name, "Excel Dosyası (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            write_one_on_one_history_workbook(path, student["name"], headers, rows)
        except OSError as error:
            QMessageBox.warning(
                self, "Kaydedilemedi",
                f"Excel dosyası kaydedilemedi:\n{error}\n\nDosya başka bir programda açıksa kapatıp tekrar deneyin.",
            )
            return
        except Exception as error:
            QMessageBox.critical(self, "Excel oluşturulamadı", f"Birebir ders geçmişi Excel'e aktarılamadı:\n{error}")
            return
        QMessageBox.information(
            self, "Tamamlandı", f"{len(rows)} birebir ders kaydı şu dosyaya aktarıldı:\n{path}"
        )

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
