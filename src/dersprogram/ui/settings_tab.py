"""Gün sayısı / ders saati sayısı, görünüm (tema) ve dönem tarihleri gibi
genel ayarlar - ayar tipine göre ayrı sekmelere (Görünüm / Program Günleri
ve Saatleri / Dönem Tarihleri / Veri Yönetimi) bölünmüştür; her sekme kendi
kaydırma alanına sahiptir ki içerik pencereden taşarsa (ör. çok sayıda ders
saati satırı) alt kısımlar erişilemez hale gelmesin."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QTimeEdit,
    QPushButton,
    QMessageBox,
    QLabel,
    QFrame,
    QFileDialog,
    QScrollArea,
    QTabWidget,
    QDialog,
    QDialogButtonBox,
)

from ..db import Database
from .. import seed, institutions

ALL_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    font.setPointSize(font.pointSize() + 1)
    label.setFont(font)
    return label


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


def _safe_filename(name: str) -> str:
    cleaned = "".join(c if (c.isalnum() or c in "-_ ") else "_" for c in name).strip()
    return cleaned or "kurum"


class InstitutionExportDialog(QDialog):
    """'Yedeği Dışa Aktar'da hangi kurum(lar)ın dışa aktarılacağını seçtirir.
    Birden fazla kurum işaretlenebilir - ama her biri (birleştirilmeden)
    kendi ayrı dosyasına yedeklenir (bkz. SettingsTab.handle_export_backup)."""

    def __init__(self, entries: list[dict], active_file: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yedeği Dışa Aktar - Kurum Seçimi")
        self.resize(380, 380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Dışa aktarmak istediğiniz kurum(lar)ı seçin - her biri kendi ayrı "
            "dosyası olarak seçeceğiniz klasöre kaydedilir (kurumlar birleştirilmez)."
        ))

        self._checks: list[tuple[QCheckBox, dict]] = []
        for entry in entries:
            label = entry["name"]
            if entry["file"] == active_file:
                label += "  (şu an aktif)"
            checkbox = QCheckBox(label)
            checkbox.setChecked(entry["file"] == active_file)
            self._checks.append((checkbox, entry))
            layout.addWidget(checkbox)
        layout.addStretch()

        select_row = QHBoxLayout()
        all_button = QPushButton("Tümünü Seç")
        all_button.clicked.connect(lambda: self._set_all(True))
        select_row.addWidget(all_button)
        none_button = QPushButton("Hiçbirini Seçme")
        none_button.clicked.connect(lambda: self._set_all(False))
        select_row.addWidget(none_button)
        select_row.addStretch()
        layout.addLayout(select_row)

        buttons = QDialogButtonBox()
        export_button = buttons.addButton("Dışa Aktar", QDialogButtonBox.AcceptRole)
        export_button.setObjectName("primaryButton")
        buttons.addButton("Vazgeç", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_all(self, checked: bool) -> None:
        for checkbox, _entry in self._checks:
            checkbox.setChecked(checked)

    def selected_entries(self) -> list[dict]:
        return [entry for checkbox, entry in self._checks if checkbox.isChecked()]


class SettingsTab(QWidget):
    def __init__(self, db: Database, on_change=None, on_restore_requested=None):
        super().__init__()
        self.db = db
        self.on_change = on_change
        # Yedekten geri yükleme, sadece bu sekmenin kendi self.db'sini değil
        # TÜM açık sekmeleri (yeni bir Database örneğiyle) yeniden kurmayı
        # gerektirir - bu yüzden gerçek işlem MainWindow'da yapılır, burası
        # sadece dosyayı seçtirip callback'i çağırır (bkz. main_window.py
        # handle_restore_backup).
        self.on_restore_requested = on_restore_requested

        outer_layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_appearance_tab(), "Görünüm")
        self.tabs.addTab(self._build_schedule_tab(), "Program Günleri ve Saatleri")
        self.tabs.addTab(self._build_term_tab(), "Dönem Tarihleri")
        self.tabs.addTab(self._build_data_tab(), "Veri Yönetimi")
        outer_layout.addWidget(self.tabs, 1)

        save_row = QHBoxLayout()
        save_button = QPushButton("Ayarları Kaydet")
        save_button.setObjectName("primaryButton")
        save_button.setToolTip(
            "Görünüm, Program Günleri ve Saatleri, Dönem Tarihleri sekmelerindeki "
            "değişiklikleri kaydeder (Veri Yönetimi sekmesindeki işlemler kendi "
            "düğmelerine basıldığında anında uygulanır)."
        )
        save_button.clicked.connect(self.save)
        save_row.addWidget(save_button)
        save_row.addStretch()
        outer_layout.addLayout(save_row)

    @staticmethod
    def _wrap_scroll(inner: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(inner)
        return scroll

    # ---------- Görünüm ----------
    def _build_appearance_tab(self) -> QScrollArea:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_section_label("Görünüm"))
        appearance_form = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Açık", "light")
        self.theme_combo.addItem("Koyu", "dark")
        idx = self.theme_combo.findData(self.db.theme)
        self.theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        appearance_form.addRow("Tema:", self.theme_combo)
        layout.addLayout(appearance_form)
        layout.addStretch()
        return self._wrap_scroll(page)

    # ---------- Program Günleri ve Saatleri ----------
    def _build_schedule_tab(self) -> QScrollArea:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_section_label("Program Günleri ve Saatleri"))
        layout.addWidget(QLabel(
            "Not: Ders saati sayısını sonradan azaltırsanız, silinen saatlerdeki "
            "atamalar programdan kalkar (veritabanından silinmez, sadece görünmez olabilir)."
        ))

        form = QFormLayout()
        self.day_checks: dict[str, QCheckBox] = {}
        current_days = set(self.db.day_names)
        for day in ALL_DAYS:
            cb = QCheckBox(day)
            cb.setChecked(day in current_days)
            self.day_checks[day] = cb
            form.addRow(cb)

        self.period_spin = QSpinBox()
        self.period_spin.setRange(1, 15)
        self.period_spin.setValue(self.db.period_count)
        form.addRow("Günlük ders saati sayısı:", self.period_spin)

        layout.addLayout(form)

        layout.addWidget(QLabel(
            "Her ders saatinin başlangıç/bitiş saatini isterseniz tek tek girin "
            "(ör. 1. ders 08:30-09:20) - programın diğer yerlerinde saat numarasının "
            "yanında gösterilir. Boş bırakırsanız sadece saat numarası gösterilir."
        ))
        self.period_time_edits: list[tuple[QTimeEdit, QTimeEdit]] = []
        self.period_times_layout = QVBoxLayout()
        self.period_times_layout.setSpacing(4)
        layout.addLayout(self.period_times_layout)
        self.period_spin.valueChanged.connect(self._rebuild_period_time_rows)
        self._rebuild_period_time_rows()
        layout.addStretch()
        return self._wrap_scroll(page)

    # ---------- Dönem Tarihleri ----------
    def _build_term_tab(self) -> QScrollArea:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_section_label("Dönem Tarihleri"))
        layout.addWidget(QLabel(
            "Bu tarihler bilgilendirme amaçlıdır; program yerleştirmelerinde "
            "'kalıcı' seçeneği bu dönem boyunca geçerli olur şeklinde gösterilir."
        ))
        term_form = QFormLayout()
        self.term_start_edit = QDateEdit()
        self.term_start_edit.setCalendarPopup(True)
        self.term_start_edit.setDisplayFormat("dd.MM.yyyy")
        self.term_start_edit.setDate(self._parse_date(self.db.term_start) or QDate.currentDate())
        term_form.addRow("Dönem Başlangıcı:", self.term_start_edit)

        self.term_end_edit = QDateEdit()
        self.term_end_edit.setCalendarPopup(True)
        self.term_end_edit.setDisplayFormat("dd.MM.yyyy")
        default_end = self._parse_date(self.db.term_end) or QDate.currentDate().addMonths(4)
        self.term_end_edit.setDate(default_end)
        term_form.addRow("Dönem Bitişi:", self.term_end_edit)
        layout.addLayout(term_form)
        layout.addStretch()
        return self._wrap_scroll(page)

    # ---------- Veri Yönetimi (örnek veri + yedekleme) ----------
    def _build_data_tab(self) -> QScrollArea:
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(_section_label("Örnek Veri"))
        layout.addWidget(QLabel(
            "Programı denemek için tüm sekmelere (öğretmen, öğrenci, sınıf, ders, "
            "derslik) birkaç örnek kayıt ve haftalık programa birkaç örnek ders "
            "ekler. Mevcut verilerinizi silmez, üzerine ekler."
        ))
        seed_button = QPushButton("Örnek Veri Ekle")
        seed_button.clicked.connect(self.handle_seed_demo_data)
        layout.addWidget(seed_button)

        layout.addWidget(_divider())

        layout.addWidget(_section_label("Yedekleme"))
        layout.addWidget(QLabel(
            "Verileriniz program açıkken otomatik olarak (arka planda, hiçbir şey "
            "yapmanıza gerek kalmadan) periyodik olarak ve program kapanırken yedeklenir. "
            "Birden fazla bilgisayarda çalışıyorsanız, verinizi bir bilgisayardan diğerine "
            "taşımak için aşağıdaki düğmeleri kullanabilirsiniz (ör. yedeği bir USB belleğe "
            "ya da bulut klasörüne kaydedip diğer bilgisayarda geri yükleyerek). Dışa aktarırken "
            "birden fazla kurum seçebilirsiniz - her biri kendi ayrı dosyasına kaydedilir."
        ))
        backup_row = QHBoxLayout()
        export_backup_button = QPushButton("Yedeği Dışa Aktar")
        export_backup_button.setObjectName("outlineButton")
        export_backup_button.clicked.connect(self.handle_export_backup)
        backup_row.addWidget(export_backup_button)
        import_backup_button = QPushButton("Yedekten Geri Yükle")
        import_backup_button.setObjectName("dangerButton")
        import_backup_button.clicked.connect(self.handle_import_backup)
        backup_row.addWidget(import_backup_button)
        backup_row.addStretch()
        layout.addLayout(backup_row)

        layout.addStretch()
        return self._wrap_scroll(page)

    def handle_export_backup(self) -> None:
        entries = institutions.list_institutions()
        if not entries:
            QMessageBox.information(self, "Kurum Yok", "Dışa aktarılacak bir kurum bulunamadı.")
            return
        active = institutions.get_active_institution()
        dialog = InstitutionExportDialog(entries, active["file"], self)
        if dialog.exec() != QDialog.Accepted:
            return
        selected = dialog.selected_entries()
        if not selected:
            return

        folder = QFileDialog.getExistingDirectory(self, "Yedeklerin Kaydedileceği Klasör")
        if not folder:
            return
        folder_path = Path(folder)

        saved_names: list[str] = []
        failed: list[str] = []
        for entry in selected:
            src_path = institutions.institution_db_path(entry)
            if not src_path.exists():
                failed.append(f"{entry['name']} (henüz hiç kullanılmamış, kaydedilecek verisi yok)")
                continue
            dest = folder_path / f"{_safe_filename(entry['name'])}.db"
            try:
                source_db = Database(src_path)
                try:
                    source_db.backup_to(dest)
                finally:
                    source_db.close()
                saved_names.append(entry["name"])
            except Exception as exc:
                failed.append(f"{entry['name']}: {exc}")

        if saved_names:
            message = "Şu kurumlar ayrı dosyalar olarak dışa aktarıldı:\n- " + "\n- ".join(saved_names)
            message += f"\n\nKlasör:\n{folder_path}"
            if failed:
                message += "\n\nDışa aktarılamayanlar:\n- " + "\n- ".join(failed)
            QMessageBox.information(self, "Dışa Aktarıldı", message)
        else:
            QMessageBox.warning(
                self, "Dışa Aktarılamadı",
                "Hiçbir kurum dışa aktarılamadı:\n- " + "\n- ".join(failed),
            )

    def handle_import_backup(self) -> None:
        if self.on_restore_requested is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Yedekten Geri Yükle", "", "Veritabanı Dosyası (*.db)")
        if not path:
            return
        confirm = QMessageBox.question(
            self, "Yedekten Geri Yükle",
            "Mevcut verileriniz, seçtiğiniz yedek dosyasındaki verilerle DEĞİŞTİRİLECEK "
            "(mevcut hali önce ayrıca otomatik yedeklenecek, ama bu ekrandaki değişiklikler "
            "kaybolur). Devam edilsin mi?",
        )
        if confirm != QMessageBox.Yes:
            return
        self.on_restore_requested(path)

    def handle_seed_demo_data(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Örnek Veri Ekle",
            "Tüm sekmelere birkaç örnek kayıt eklenecek (mevcut verileriniz silinmez). "
            "Devam edilsin mi?",
        )
        if confirm != QMessageBox.Yes:
            return
        seed.seed_demo_data(self.db)
        QMessageBox.information(self, "Tamamlandı", "Örnek veriler eklendi.")
        if self.on_change:
            self.on_change()

    def _rebuild_period_time_rows(self) -> None:
        """Ders saati sayısı değişince (spin box) satır sayısını buna göre
        yeniden kurar; zaten girilmiş saatleri korur, yeni saatler için
        önceki saatin bitişinden 10 dakika sonrasını varsayılan önerir."""
        while self.period_times_layout.count():
            item = self.period_times_layout.takeAt(0)
            row_layout = item.layout()
            if row_layout is not None:
                while row_layout.count():
                    sub = row_layout.takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()
                row_layout.deleteLater()
            elif item.widget():
                item.widget().deleteLater()

        saved = self.db.period_times
        self.period_time_edits = []
        prev_end = None
        for period in range(1, self.period_spin.value() + 1):
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{period}. ders:"))
            start_edit = QTimeEdit()
            start_edit.setDisplayFormat("HH:mm")
            end_edit = QTimeEdit()
            end_edit.setDisplayFormat("HH:mm")

            entry = saved[period - 1] if period - 1 < len(saved) else None
            if isinstance(entry, dict) and entry.get("start") and entry.get("end"):
                start_edit.setTime(QTime.fromString(entry["start"], "HH:mm"))
                end_edit.setTime(QTime.fromString(entry["end"], "HH:mm"))
            else:
                default_start = prev_end.addSecs(10 * 60) if prev_end else QTime(8, 30)
                start_edit.setTime(default_start)
                end_edit.setTime(default_start.addSecs(40 * 60))

            row.addWidget(start_edit)
            row.addWidget(QLabel("–"))
            row.addWidget(end_edit)
            row.addStretch()
            self.period_times_layout.addLayout(row)
            self.period_time_edits.append((start_edit, end_edit))
            prev_end = end_edit.time()

    @staticmethod
    def _parse_date(value: str | None) -> QDate | None:
        if not value:
            return None
        try:
            d = _dt.date.fromisoformat(value)
        except ValueError:
            return None
        return QDate(d.year, d.month, d.day)

    def save(self) -> None:
        selected_days = [day for day in ALL_DAYS if self.day_checks[day].isChecked()]
        if not selected_days:
            QMessageBox.warning(self, "Eksik bilgi", "En az bir gün seçmelisiniz.")
            return
        if self.term_start_edit.date() > self.term_end_edit.date():
            QMessageBox.warning(self, "Eksik bilgi", "Dönem başlangıcı, bitişinden sonra olamaz.")
            return

        self.db.set_setting("day_names", selected_days)
        self.db.set_setting("period_count", self.period_spin.value())
        period_times = [
            {"start": start_edit.time().toString("HH:mm"), "end": end_edit.time().toString("HH:mm")}
            for start_edit, end_edit in self.period_time_edits
        ]
        self.db.set_setting("period_times", period_times)
        self.db.set_setting("term_start", self.term_start_edit.date().toString("yyyy-MM-dd"))
        self.db.set_setting("term_end", self.term_end_edit.date().toString("yyyy-MM-dd"))

        new_theme = self.theme_combo.currentData()
        theme_changed = new_theme != self.db.get_setting("theme")
        self.db.set_setting("theme", new_theme)

        message = "Ayarlar kaydedildi."
        if theme_changed:
            message += "\n\nTema değişikliğinin uygulanması için programı kapatıp yeniden açın."
        QMessageBox.information(self, "Kaydedildi", message)
        if self.on_change:
            self.on_change()
