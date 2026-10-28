"""Kurum (şube/okul) seçme, ekleme, adını değiştirme ve silme diyaloğu.

Her kurum ayrı bir veritabanı dosyasında saklanır; buradan hangi dosyaya
geçileceği seçilir - gerçek geçiş işlemini MainWindow yapar. Silinen bir
kurumun silinmeden hemen önce yedeği alınır (bkz. handle_delete)."""
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

from .. import backup, institutions
from ..db import Database


class InstitutionDialog(QDialog):
    def __init__(self, current_file: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kurumlar")
        self.resize(480, 400)
        self._current_file = current_file
        self.selected_entry: dict | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Her kurum kendi ayrı dosyasında saklanır; aralarında geçiş yapmak "
            "diğer kurumların verilerini etkilemez."
        ))

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._handle_open)
        layout.addWidget(self.list_widget, 1)
        self._reload_list()

        add_row = QHBoxLayout()
        self.add_button = QPushButton("Yeni Kurum Ekle")
        self.add_button.clicked.connect(self.handle_add)
        add_row.addWidget(self.add_button)
        # Kullanıcı isteği: "kurum adı değiştirme ve kurum datası silme".
        self.rename_button = QPushButton("Adını Değiştir")
        self.rename_button.setObjectName("outlineButton")
        self.rename_button.clicked.connect(self.handle_rename)
        add_row.addWidget(self.rename_button)
        add_row.addStretch()
        self.delete_button = QPushButton("Kurumu Sil")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.setToolTip(
            "Seçili kurumu ve TÜM verilerini siler. Silmeden önce bir yedeği "
            "Yedekler klasörüne alınır."
        )
        self.delete_button.clicked.connect(self.handle_delete)
        add_row.addWidget(self.delete_button)
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

    def _selected_entry(self) -> dict | None:
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "Kurum Seçin", "Önce listeden bir kurum seçin.")
            return None
        return item.data(Qt.UserRole)

    def handle_rename(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        name, ok = QInputDialog.getText(
            self, "Kurumun Adını Değiştir", "Yeni kurum adı:", text=entry["name"],
        )
        if not ok or not name.strip() or name.strip() == entry["name"]:
            return
        try:
            institutions.rename_institution(entry["file"], name.strip())
        except ValueError as exc:
            QMessageBox.warning(self, "Ad Değiştirilemedi", str(exc))
            return
        self._reload_list(select_file=entry["file"])

    def handle_delete(self) -> None:
        """Seçili kurumu ve bütün verisini siler. Güvenlik önlemleri:
        - şu an açık olan kurum silinemez (önce başka kuruma geçilmeli),
        - silmeden önce kurumun bir yedeği Yedekler klasörüne alınır,
        - kullanıcıdan kurumun adını yazarak onay vermesi istenir."""
        entry = self._selected_entry()
        if entry is None:
            return
        if entry["file"] == self._current_file:
            QMessageBox.information(
                self, "Kurum Açık",
                f"'{entry['name']}' şu an açık olan kurum, bu yüzden silinemez.\n\n"
                "Silmek için önce başka bir kuruma geçin (gerekirse 'Yeni Kurum Ekle' ile "
                "bir kurum ekleyip ona geçin), sonra bu pencereyi tekrar açıp silin.",
            )
            return
        typed, ok = QInputDialog.getText(
            self, "Kurumu Sil",
            f"'{entry['name']}' kurumu ve bütün verileri (öğretmenler, öğrenciler, sınıflar,\n"
            "dersler, program, ödemeler...) silinecek.\n\n"
            "Silmeden önce bir yedeği Yedekler klasörüne alınır; gerekirse Ayarlar >\n"
            "'Yedekten Geri Yükle' ile geri getirilebilir.\n\n"
            "Onaylamak için kurumun adını aynen yazın:",
        )
        if not ok:
            return
        if typed.strip() != entry["name"].strip():
            QMessageBox.warning(self, "Silinmedi", "Yazılan ad kurumun adıyla aynı değil - kurum silinmedi.")
            return

        backup_path = None
        db_path = institutions.institution_db_path(entry)
        if db_path.exists():
            try:
                db = Database(db_path)
                backup_path = backup.backup_now(db, entry["file"])
                db.close()
            except Exception:
                backup_path = None
            if backup_path is None:
                confirm = QMessageBox.question(
                    self, "Yedek Alınamadı",
                    "Kurumun yedeği alınamadı. Yine de yedeksiz silinsin mi?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if confirm != QMessageBox.Yes:
                    return
        try:
            institutions.delete_institution(entry["file"])
        except ValueError as exc:
            QMessageBox.warning(self, "Silinemedi", str(exc))
            return
        self._reload_list()
        message = f"'{entry['name']}' kurumu silindi."
        if backup_path is not None:
            message += f"\n\nYedeği: {backup_path}"
        QMessageBox.information(self, "Kurum Silindi", message)

    def _handle_open(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "Kurum Seçin", "Önce listeden bir kurum seçin.")
            return
        self.selected_entry = item.data(Qt.UserRole)
        self.accept()
