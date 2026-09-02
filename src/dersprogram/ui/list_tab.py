"""Öğretmen / Ders / Sınıf / Derslik gibi basit liste ekranları için
tekrar kullanılabilir bir bileşen."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLineEdit,
    QLabel,
    QMessageBox,
    QHeaderView,
)

from ..db import Database


class ListTab(QWidget):
    """table: veritabanı tablo adı (ör. 'teachers')
    title_singular: 'Öğretmen' gibi tekil isim (diyaloglarda kullanılır)
    """

    def __init__(self, db: Database, table: str, title_singular: str, on_change=None):
        super().__init__()
        self.db = db
        self.table = table
        self.title_singular = title_singular
        self.on_change = on_change
        self.selected_id: int | None = None

        layout = QVBoxLayout(self)

        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Ad:"))
        self.name_edit = QLineEdit()
        form_row.addWidget(self.name_edit)
        form_row.addWidget(QLabel("Not:"))
        self.note_edit = QLineEdit()
        form_row.addWidget(self.note_edit)
        layout.addLayout(form_row)

        button_row = QHBoxLayout()
        self.add_button = QPushButton(f"{title_singular} Ekle")
        self.update_button = QPushButton("Güncelle")
        self.delete_button = QPushButton("Sil")
        self.clear_button = QPushButton("Temizle")
        for b in (self.add_button, self.update_button, self.delete_button, self.clear_button):
            button_row.addWidget(b)
        layout.addLayout(button_row)

        self.table_widget = QTableWidget(0, 2)
        self.table_widget.setHorizontalHeaderLabels(["Ad", "Not"])
        self.table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table_widget)

        self.add_button.clicked.connect(self.handle_add)
        self.update_button.clicked.connect(self.handle_update)
        self.delete_button.clicked.connect(self.handle_delete)
        self.clear_button.clicked.connect(self.clear_form)
        self.table_widget.itemSelectionChanged.connect(self.handle_selection)

        self.refresh()

    def refresh(self) -> None:
        rows = self.db.list_rows(self.table)
        self.table_widget.setRowCount(len(rows))
        for r, row in enumerate(rows):
            item_name = QTableWidgetItem(row["name"])
            item_name.setData(256, row["id"])  # Qt.UserRole
            self.table_widget.setItem(r, 0, item_name)
            self.table_widget.setItem(r, 1, QTableWidgetItem(row["note"] or ""))

    def handle_selection(self) -> None:
        items = self.table_widget.selectedItems()
        if not items:
            self.selected_id = None
            return
        row = items[0].row()
        name_item = self.table_widget.item(row, 0)
        note_item = self.table_widget.item(row, 1)
        self.selected_id = name_item.data(256)
        self.name_edit.setText(name_item.text())
        self.note_edit.setText(note_item.text())

    def clear_form(self) -> None:
        self.selected_id = None
        self.name_edit.clear()
        self.note_edit.clear()
        self.table_widget.clearSelection()

    def handle_add(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik bilgi", f"{self.title_singular} adı boş olamaz.")
            return
        self.db.add_row(self.table, name, self.note_edit.text().strip())
        self.clear_form()
        self.refresh()
        if self.on_change:
            self.on_change()

    def handle_update(self) -> None:
        if self.selected_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce listeden bir kayıt seçin.")
            return
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik bilgi", f"{self.title_singular} adı boş olamaz.")
            return
        self.db.update_row(self.table, self.selected_id, name, self.note_edit.text().strip())
        self.clear_form()
        self.refresh()
        if self.on_change:
            self.on_change()

    def handle_delete(self) -> None:
        if self.selected_id is None:
            QMessageBox.information(self, "Seçim yok", "Önce listeden bir kayıt seçin.")
            return
        confirm = QMessageBox.question(
            self,
            "Silme Onayı",
            f"Bu {self.title_singular.lower()} kaydını silmek istediğinize emin misiniz?\n"
            "Bu kayda bağlı program hücreleri de etkilenebilir.",
        )
        if confirm != QMessageBox.Yes:
            return
        self.db.delete_row(self.table, self.selected_id)
        self.clear_form()
        self.refresh()
        if self.on_change:
            self.on_change()
