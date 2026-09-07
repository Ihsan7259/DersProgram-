"""Gün sayısı / ders saati sayısı, görünüm (tema) ve dönem tarihleri gibi
genel ayarlar."""
from __future__ import annotations

import datetime as _dt

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
)

from ..db import Database
from .. import seed

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

        layout = QVBoxLayout(self)

        # ---------- görünüm ----------
        layout.addWidget(_section_label("Görünüm"))
        appearance_form = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Açık", "light")
        self.theme_combo.addItem("Koyu", "dark")
        idx = self.theme_combo.findData(self.db.theme)
        self.theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        appearance_form.addRow("Tema:", self.theme_combo)
        layout.addLayout(appearance_form)

        layout.addWidget(_divider())

        # ---------- program günleri ----------
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

        layout.addWidget(_divider())

        # ---------- dönem tarihleri ----------
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

        save_button = QPushButton("Ayarları Kaydet")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self.save)
        layout.addWidget(save_button)

        layout.addWidget(_divider())

        # ---------- örnek veri ----------
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

        # ---------- yedekleme ----------
        layout.addWidget(_section_label("Yedekleme"))
        layout.addWidget(QLabel(
            "Verileriniz program açıkken otomatik olarak (arka planda, hiçbir şey "
            "yapmanıza gerek kalmadan) periyodik olarak ve program kapanırken yedeklenir. "
            "Birden fazla bilgisayarda çalışıyorsanız, verinizi bir bilgisayardan diğerine "
            "taşımak için aşağıdaki düğmeleri kullanabilirsiniz (ör. yedeği bir USB belleğe "
            "ya da bulut klasörüne kaydedip diğer bilgisayarda geri yükleyerek)."
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

    def handle_export_backup(self) -> None:
        default_name = f"ders_programi_yedek_{_dt.date.today().isoformat()}.db"
        path, _ = QFileDialog.getSaveFileName(self, "Yedeği Dışa Aktar", default_name, "Veritabanı Dosyası (*.db)")
        if not path:
            return
        if not path.lower().endswith(".db"):
            path += ".db"
        try:
            self.db.backup_to(path)
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Yedek oluşturulamadı:\n{exc}")
            return
        QMessageBox.information(
            self, "Yedek Kaydedildi",
            f"Yedek şu konuma kaydedildi:\n{path}\n\n"
            "Bu dosyayı başka bir bilgisayara taşıyıp Ayarlar'daki "
            "'Yedekten Geri Yükle' ile açabilirsiniz.",
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
