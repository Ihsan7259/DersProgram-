from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QAbstractItemView,
    QWidget,
    QCheckBox,
    QScrollArea,
)
from PySide6.QtCore import Qt

from ..db import Database
from .. import excel_import


class ImportStudentsDialog(QDialog):
    """Excel dosyasından toplu öğrenci içe aktarma penceresi.

    Kullanıcı bir .xlsx dosyası seçer, satırlar önizleme tablosunda
    (eksik sınıf/koç/ünvan uyarılarıyla birlikte) gösterilir, "İçe Aktar"
    ile veritabanına yazılır."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._rows: list[excel_import.ImportRow] = []
        self.class_checks: dict[str, QCheckBox] = {}
        self.setWindowTitle("Excel'den Öğrenci İçe Aktar")
        self.resize(760, 560)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Bir Excel (.xlsx) dosyası seçin. Sütun başlıkları esnek eşleşir "
            "(ör. 'Ad', 'İsim', 'Sınıf', 'Koç', 'Program Ücreti', 'Birebir Ücreti', 'Ünvan'). "
            "Zorunlu olan tek sütun öğrenci adıdır. Hazır bir şablonla başlamak için "
            "'Şablon İndir' butonunu kullanabilirsiniz."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        button_row = QHBoxLayout()
        self.choose_file_button = QPushButton("Dosya Seç...")
        self.choose_file_button.clicked.connect(self.handle_choose_file)
        button_row.addWidget(self.choose_file_button)
        self.template_button = QPushButton("Şablon İndir")
        self.template_button.clicked.connect(self.handle_download_template)
        button_row.addWidget(self.template_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        self.file_label = QLabel("Henüz dosya seçilmedi.")
        layout.addWidget(self.file_label)

        self.missing_classes_label = QLabel(
            "Excel'de olup sistemde henüz olmayan sınıflar - işaretli olanlar yeni "
            "oluşturulacak, işareti kaldırdıklarınız için öğrenci SINIFSIZ eklenecek:"
        )
        self.missing_classes_label.setWordWrap(True)
        self.missing_classes_label.setVisible(False)
        layout.addWidget(self.missing_classes_label)

        self._missing_classes_container = QWidget()
        self._missing_classes_layout = QHBoxLayout(self._missing_classes_container)
        self._missing_classes_layout.setContentsMargins(4, 2, 4, 2)
        self._missing_classes_layout.setSpacing(10)
        self.missing_classes_scroll = QScrollArea()
        self.missing_classes_scroll.setWidgetResizable(True)
        self.missing_classes_scroll.setMaximumHeight(46)
        self.missing_classes_scroll.setWidget(self._missing_classes_container)
        self.missing_classes_scroll.setVisible(False)
        layout.addWidget(self.missing_classes_scroll)

        self.preview_table = QTableWidget(0, 7)
        self.preview_table.setHorizontalHeaderLabels(
            ["Ad", "Sınıf", "Koç", "Program Ücreti", "Birebir Ücreti", "Ünvan", "Uyarılar"]
        )
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview_table.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.preview_table, 1)

        self.summary_label = QLabel("")
        layout.addWidget(self.summary_label)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        self.import_button = QPushButton("İçe Aktar")
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self.handle_import)
        bottom_row.addWidget(self.import_button)
        self.cancel_button = QPushButton("Vazgeç")
        self.cancel_button.clicked.connect(self.reject)
        bottom_row.addWidget(self.cancel_button)
        layout.addLayout(bottom_row)

    def handle_download_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Şablonu Kaydet", "ogrenci_sablonu.xlsx", "Excel Dosyası (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            excel_import.write_template(path)
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Şablon oluşturulamadı:\n{exc}")
            return
        QMessageBox.information(self, "Şablon Kaydedildi", f"Şablon şu konuma kaydedildi:\n{path}")

    def handle_choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Excel Dosyası Seç", "", "Excel Dosyası (*.xlsx)")
        if not path:
            return
        try:
            rows = excel_import.parse_student_workbook(path, self.db)
        except excel_import.ImportError_ as exc:
            QMessageBox.critical(self, "Hata", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Dosya okunamadı:\n{exc}")
            return

        self._rows = rows
        self.file_label.setText(path)
        self._populate_missing_classes()
        self._populate_preview()

    def _populate_missing_classes(self) -> None:
        while self._missing_classes_layout.count():
            item = self._missing_classes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.class_checks = {}

        existing = {c["name"].strip().lower() for c in self.db.list_class_groups()}
        seen: set[str] = set()
        missing_names: list[str] = []
        for row in self._rows:
            if not row.class_name:
                continue
            key = row.class_name.lower()
            if key not in existing and key not in seen:
                seen.add(key)
                missing_names.append(row.class_name)

        has_missing = bool(missing_names)
        self.missing_classes_label.setVisible(has_missing)
        self.missing_classes_scroll.setVisible(has_missing)
        for name in sorted(missing_names, key=str.lower):
            checkbox = QCheckBox(name)
            checkbox.setChecked(True)
            self.class_checks[name] = checkbox
            self._missing_classes_layout.addWidget(checkbox)
        if has_missing:
            self._missing_classes_layout.addStretch()

    def _populate_preview(self) -> None:
        rows = self._rows
        self.preview_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.preview_table.setItem(r, 0, QTableWidgetItem(row.name))
            self.preview_table.setItem(r, 1, QTableWidgetItem(row.class_name or ""))
            self.preview_table.setItem(r, 2, QTableWidgetItem(row.coach_name or ""))
            self.preview_table.setItem(r, 3, QTableWidgetItem(f"{row.program_fee:g}"))
            self.preview_table.setItem(r, 4, QTableWidgetItem(f"{row.one_on_one_fee:g}"))
            self.preview_table.setItem(r, 5, QTableWidgetItem(", ".join(row.title_names)))
            warning_text = "; ".join(row.warnings)
            warning_item = QTableWidgetItem(warning_text)
            if row.warnings:
                warning_item.setForeground(Qt.darkYellow)
            self.preview_table.setItem(r, 6, warning_item)

        if not rows:
            self.summary_label.setText("Dosyada içe aktarılacak öğrenci bulunamadı.")
            self.import_button.setEnabled(False)
            return

        warning_count = sum(1 for row in rows if row.warnings)
        text = f"{len(rows)} öğrenci bulundu."
        if warning_count:
            text += (
                f" ({warning_count} tanesinde eksik sınıf/koç/ünvan uyarısı var - eksik sınıflar için "
                "yukarıdaki onay kutularından seçim yapabilirsiniz, koç/ünvan eksikse boş bırakılır ya "
                "da otomatik oluşturulur.)"
            )
        self.summary_label.setText(text)
        self.import_button.setEnabled(True)

    def handle_import(self) -> None:
        if not self._rows:
            return
        create_class_names = {name.lower() for name, cb in self.class_checks.items() if cb.isChecked()}
        skipped_classes = [name for name, cb in self.class_checks.items() if not cb.isChecked()]

        confirm_text = f"{len(self._rows)} öğrenci veritabanına eklensin mi?"
        if skipped_classes:
            confirm_text += (
                "\n\nİşaretini kaldırdığınız şu sınıflar OLUŞTURULMAYACAK, bu sınıflardaki öğrenciler "
                "sınıfsız eklenecek:\n- " + "\n- ".join(skipped_classes)
            )
        confirm = QMessageBox.question(self, "Onay", confirm_text)
        if confirm != QMessageBox.Yes:
            return
        try:
            imported = excel_import.apply_import(self.db, self._rows, create_class_names=create_class_names)
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"İçe aktarma sırasında bir hata oluştu:\n{exc}")
            return
        QMessageBox.information(self, "Tamamlandı", f"{imported} öğrenci başarıyla içe aktarıldı.")
        self.accept()
