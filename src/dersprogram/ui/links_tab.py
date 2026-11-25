"""Linkler: her öğretmen, öğrenci ve sınıfın kişisel web linki ve
"Siteye Yayınla" (bkz. web_publish.py).

Kullanıcı isteği: ekran görüntülerini WhatsApp'tan tek tek atınca hesap
spam diye kısıtlanıyordu. Artık herkese linki BİR KERE gönderilir
("WhatsApp'ta Gönder" mesajı hazır açar), sonrasında program her
yayınlandığında linkteki program kendiliğinden güncellenir."""
from __future__ import annotations

import datetime as _dt
from urllib.parse import quote

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..db import Database
from .. import web_publish
from .widgets import section_title as _section_title, divider as _divider

KIND_FILTERS = [
    ("", "Hepsi"),
    (web_publish.KIND_TEACHER, "Öğretmenler"),
    (web_publish.KIND_STUDENT, "Öğrenciler"),
    (web_publish.KIND_CLASS, "Sınıflar"),
]


def _format_publish_time(iso_text: str | None) -> str:
    if not iso_text:
        return ""
    try:
        return _dt.datetime.fromisoformat(iso_text).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return iso_text


class PublishSettingsDialog(QDialog):
    """Yayın Ayarları: linklerin başındaki site adresi ve verinin
    yükleneceği gizli GitHub deposu."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Yayın Ayarları")
        self.resize(560, 0)
        config = web_publish.get_config(db)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Programlar gizli (private) bir GitHub deposuna yüklenir, site de oradan okur.\n"
            "Token: GitHub > Settings > Developer settings > Fine-grained tokens > Generate new token.\n"
            "Sadece bu depoyu seçin ve 'Contents' iznini 'Read and write' yapın."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.base_url_edit = QLineEdit(config["base_url"])
        self.base_url_edit.setPlaceholderText("https://vipparkkurs.com/p/")
        self.repo_edit = QLineEdit(config["repo"])
        self.repo_edit.setPlaceholderText("kullanici/depo-adi")
        self.branch_edit = QLineEdit(config["branch"])
        self.folder_edit = QLineEdit(config["folder"])
        self.token_edit = QLineEdit(config["token"])
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setPlaceholderText("github_pat_...")
        form.addRow("Link adresi:", self.base_url_edit)
        form.addRow("GitHub deposu:", self.repo_edit)
        form.addRow("Dal:", self.branch_edit)
        form.addRow("Klasör:", self.folder_edit)
        form.addRow("Token:", self.token_edit)
        layout.addLayout(form)

        self.test_button = QPushButton("Bağlantıyı Test Et")
        self.test_button.setObjectName("outlineButton")
        self.test_button.clicked.connect(self.handle_test)
        layout.addWidget(self.test_button, 0, Qt.AlignLeft)

        buttons = QDialogButtonBox()
        save = buttons.addButton("Kaydet", QDialogButtonBox.AcceptRole)
        save.setObjectName("primaryButton")
        buttons.addButton("Vazgeç", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "base_url": self.base_url_edit.text(),
            "repo": self.repo_edit.text(),
            "branch": self.branch_edit.text() or "main",
            "folder": self.folder_edit.text(),
            "token": self.token_edit.text(),
        }

    def handle_test(self) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            message = web_publish.test_connection(self.values())
        except web_publish.PublishError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Bağlantı Kurulamadı", str(exc))
            return
        QApplication.restoreOverrideCursor()
        QMessageBox.information(self, "Bağlantı Testi", message)

    def accept(self) -> None:
        values = self.values()
        if not values["base_url"].lower().startswith(("http://", "https://")):
            QMessageBox.warning(self, "Link adresi", "Link adresi https:// ile başlamalı (ör. https://vipparkkurs.com/p/).")
            return
        web_publish.save_config(self.db, values)
        super().accept()


class LinksTab(QWidget):
    def __init__(self, db: Database, institution_name=lambda: ""):
        super().__init__()
        self.db = db
        self.institution_name = institution_name
        self._entries: list[dict] = []

        layout = QVBoxLayout(self)
        layout.addWidget(_section_title("Siteye Yayın"))

        publish_row = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        publish_row.addWidget(self.status_label, 1)
        self.settings_button = QPushButton("Yayın Ayarları")
        self.settings_button.setObjectName("outlineButton")
        self.publish_button = QPushButton("Siteye Yayınla")
        self.publish_button.setObjectName("primaryButton")
        publish_row.addWidget(self.settings_button)
        publish_row.addWidget(self.publish_button)
        layout.addLayout(publish_row)

        layout.addWidget(_divider())
        layout.addWidget(_section_title("Kişisel Linkler"))

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Göster:"))
        self.kind_combo = QComboBox()
        for key, label in KIND_FILTERS:
            self.kind_combo.addItem(label, key)
        filter_row.addWidget(self.kind_combo)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("İsimle ara...")
        self.search_edit.setClearButtonEnabled(True)
        filter_row.addWidget(self.search_edit, 1)
        layout.addLayout(filter_row)

        self.table_widget = QTableWidget(0, 4)
        self.table_widget.setHorizontalHeaderLabels(["Tür", "Ad", "Sınıf / Branş", "Link"])
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_widget.verticalHeader().setVisible(False)
        layout.addWidget(self.table_widget, 1)

        button_row = QHBoxLayout()
        self.copy_button = QPushButton("Linki Kopyala")
        self.copy_button.setObjectName("outlineButton")
        self.whatsapp_button = QPushButton("WhatsApp'ta Gönder")
        self.whatsapp_button.setObjectName("primaryButton")
        self.renew_button = QPushButton("Linki Yenile")
        self.renew_button.setObjectName("dangerButton")
        self.excel_button = QPushButton("Link Listesini Excel'e Aktar")
        self.excel_button.setObjectName("outlineButton")
        for button in (self.copy_button, self.whatsapp_button, self.renew_button):
            button_row.addWidget(button)
        button_row.addStretch()
        button_row.addWidget(self.excel_button)
        layout.addLayout(button_row)

        hint = QLabel(
            "Linki her kişiye bir kere gönderin. Program değiştikçe 'Siteye Yayınla'ya "
            "basmanız yeterli; link aynı kalır, içindeki program güncellenir. Sayfa her "
            "zaman o haftayı gösterir, pazartesi günü yeni haftaya geçer."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.settings_button.clicked.connect(self.handle_settings)
        self.publish_button.clicked.connect(self.handle_publish)
        self.copy_button.clicked.connect(self.handle_copy)
        self.whatsapp_button.clicked.connect(self.handle_whatsapp)
        self.renew_button.clicked.connect(self.handle_renew)
        self.excel_button.clicked.connect(self.handle_export_excel)
        self.kind_combo.currentIndexChanged.connect(self._fill_table)
        self.search_edit.textChanged.connect(self._fill_table)
        self.table_widget.itemSelectionChanged.connect(self._update_buttons)

        self.refresh()

    # ---------- liste ----------
    def refresh(self) -> None:
        self._entries = web_publish.list_links(self.db)
        self._fill_table()
        self._update_status()

    def _visible_entries(self) -> list[dict]:
        kind = self.kind_combo.currentData()
        needle = self.search_edit.text().strip().casefold()
        return [
            e for e in self._entries
            if (not kind or e["kind"] == kind) and (not needle or needle in e["name"].casefold())
        ]

    def _fill_table(self) -> None:
        selected = self.selected_entry()
        selected_key = (selected["kind"], selected["id"]) if selected else None
        entries = self._visible_entries()
        self.table_widget.setRowCount(len(entries))
        reselect = None
        for row, entry in enumerate(entries):
            for col, text in enumerate((entry["kind_label"], entry["name"], entry["subtitle"], entry["url"])):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setData(Qt.UserRole, (entry["kind"], entry["id"]))
                self.table_widget.setItem(row, col, item)
            if (entry["kind"], entry["id"]) == selected_key:
                reselect = row
        if reselect is not None:
            self.table_widget.selectRow(reselect)
        self._update_buttons()

    def selected_entry(self) -> dict | None:
        rows = {index.row() for index in self.table_widget.selectionModel().selectedRows()} if self.table_widget.selectionModel() else set()
        if not rows:
            return None
        item = self.table_widget.item(min(rows), 0)
        if item is None:
            return None
        key = item.data(Qt.UserRole)
        for entry in self._entries:
            if (entry["kind"], entry["id"]) == tuple(key):
                return entry
        return None

    def _update_buttons(self) -> None:
        has = self.selected_entry() is not None
        for button in (self.copy_button, self.whatsapp_button, self.renew_button):
            button.setEnabled(has)

    def _update_status(self) -> None:
        config = web_publish.get_config(self.db)
        last = web_publish.last_publish_info(self.db)
        if not web_publish.is_configured(config):
            text = "Yayın ayarları yapılmamış. Linkler hazır ama siteye yüklemek için önce 'Yayın Ayarları'nı doldurun."
        elif last.get("published_at"):
            text = f"Son yayın: {_format_publish_time(last['published_at'])} ({len(last.get('codes', []))} link)"
        else:
            text = "Henüz siteye yayın yapılmadı."
        self.status_label.setText(text)

    # ---------- düğmeler ----------
    def handle_settings(self) -> None:
        dialog = PublishSettingsDialog(self.db, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def handle_publish(self) -> None:
        if not web_publish.is_configured(web_publish.get_config(self.db)):
            QMessageBox.information(self, "Yayın Ayarları", "Önce 'Yayın Ayarları'ndan GitHub deposunu ve token'ı girin.")
            self.handle_settings()
            if not web_publish.is_configured(web_publish.get_config(self.db)):
                return
        publish_now(self, self.db, self.institution_name())
        self.refresh()

    def handle_copy(self) -> None:
        entry = self.selected_entry()
        if entry is None:
            return
        QGuiApplication.clipboard().setText(entry["url"])
        QMessageBox.information(self, "Kopyalandı", f"{entry['name']} için link panoya kopyalandı:\n{entry['url']}")

    def handle_whatsapp(self) -> None:
        entry = self.selected_entry()
        if entry is None:
            return
        text = web_publish.whatsapp_message(entry, self.institution_name())
        # wa.me: WhatsApp (masaüstü uygulaması ya da WhatsApp Web) mesaj
        # yazılmış halde açılır, kişiyi seçip göndermek kullanıcıya kalır.
        QDesktopServices.openUrl(QUrl(f"https://wa.me/?text={quote(text)}"))

    def handle_renew(self) -> None:
        entry = self.selected_entry()
        if entry is None:
            return
        confirm = QMessageBox.question(
            self,
            "Linki Yenile",
            f"{entry['name']} için YENİ bir link oluşturulacak.\n\n"
            "Eski link bir sonraki 'Siteye Yayınla'dan sonra çalışmaz olur; yeni linki "
            "kişiye tekrar göndermeniz gerekir. Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        web_publish.regenerate_code(self.db, entry["kind"], entry["id"])
        self.refresh()
        new_entry = self.selected_entry()
        url = new_entry["url"] if new_entry else ""
        QMessageBox.information(
            self, "Link Yenilendi",
            f"Yeni link:\n{url}\n\nGeçerli olması için 'Siteye Yayınla'ya basmayı unutmayın.",
        )

    def handle_export_excel(self) -> None:
        entries = self._visible_entries()
        if not entries:
            QMessageBox.information(self, "Liste boş", "Aktarılacak link yok.")
            return
        path, _filter = QFileDialog.getSaveFileName(
            self, "Excel Olarak Kaydet", "linkler.xlsx", "Excel Dosyası (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            write_links_workbook(path, entries)
        except OSError as exc:
            QMessageBox.warning(self, "Kaydedilemedi", f"Dosya kaydedilemedi (açık olabilir mi?):\n{exc}")
            return
        QMessageBox.information(self, "Tamamlandı", f"{len(entries)} link kaydedildi:\n{path}")


def write_links_workbook(path: str, entries: list[dict]) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Linkler"
    sheet.append(["Tür", "Ad", "Sınıf / Branş", "Link"])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A5F")
    for entry in entries:
        sheet.append([entry["kind_label"], entry["name"], entry["subtitle"], entry["url"]])
        link_cell = sheet.cell(row=sheet.max_row, column=4)
        link_cell.hyperlink = entry["url"]
        link_cell.font = Font(color="1F5FBF", underline="single")
    for column, width in zip("ABCD", (12, 28, 18, 48)):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A2"
    workbook.save(path)


def publish_now(parent: QWidget, db: Database, institution: str) -> bool:
    """Yayını yapar ve sonucu kullanıcıya gösterir. Başarılıysa True."""
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        result = web_publish.publish(db, institution)
    except web_publish.PublishError as exc:
        QApplication.restoreOverrideCursor()
        QMessageBox.warning(parent, "Yayınlanamadı", str(exc))
        return False
    QApplication.restoreOverrideCursor()
    removed = f"\n{result['removed']} eski link kaldırıldı." if result["removed"] else ""
    QMessageBox.information(
        parent,
        "Yayınlandı",
        f"{result['count']} linkteki program güncellendi.{removed}\n\n"
        "Site birkaç dakika içinde yeni programı göstermeye başlar.",
    )
    return True
