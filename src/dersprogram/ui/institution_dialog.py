"""Kurum (şube/okul) seçme ve yeni kurum ekleme diyaloğu.

Her kurum ayrı bir veritabanı dosyasında saklanır; buradan sadece hangi
dosyaya geçileceği seçilir - gerçek geçiş işlemini MainWindow yapar."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QInputDialog,
    QMessageBox,
    QDialogButtonBox,
)

from .. import institutions


class InstitutionDialog(QDialog):
    def __init__(self, current_file: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kurumlar")
        self.resize(380, 380)
        self._current_file = current_file
        self.selected_entry: dict | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Her kurum kendi ayrı dosyasında saklanır; aralarında geçiş yapmak "
            "diğer kurumların verilerini etkilemez, hiçbir dosya silinmez."
        ))

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._handle_open)
        layout.addWidget(self.list_widget, 1)
        self._reload_list()

        add_row = QHBoxLayout()
        add_button = QPushButton("Yeni Kurum Ekle")
        add_button.clicked.connect(self.handle_add)
        add_row.addWidget(add_button)
        add_row.addStretch()
        layout.addLayout(add_row)

        buttons = QDialogButtonBox()
        open_button = buttons.addButton("Bu Kuruma Geç", QDialogButtonBox.AcceptRole)
        open_button.setObjectName("primaryButton")
        buttons.addButton("Kapat", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._handle_open)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _reload_list(self, select_file: str | None = None) -> None:
        self.list_widget.clear()
        entries = institutions.list_institutions()
        select_file = select_file or self._current_file
        for entry in entries:
            label = entry["name"]
            if entry["file"] == self._current_file:
                label += "  (şu an açık)"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entry)
            self.list_widget.addItem(item)
            if entry["file"] == select_file:
                self.list_widget.setCurrentItem(item)

    def handle_add(self) -> None:
        name, ok = QInputDialog.getText(self, "Yeni Kurum Ekle", "Kurum adı:")
        if not ok or not name.strip():
            return
        try:
            entry = institutions.add_institution(name.strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Kurum Eklenemedi", str(exc))
            return
        self._reload_list(select_file=entry["file"])

    def _handle_open(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "Kurum Seçin", "Önce listeden bir kurum seçin.")
            return
        self.selected_entry = item.data(Qt.UserRole)
        self.accept()
