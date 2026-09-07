"""Excel'den (.xlsx) toplu öğrenci içe aktarma.

Kullanıcı tek tek öğrenci eklemek yerine bir Excel dosyası hazırlayıp
(ya da "Şablon İndir" ile hazır bir şablon alıp) yükleyebilir. Sütun
başlıkları esnek eşleşir (büyük/küçük harf, Türkçe karakter farkı
önemli değil); zorunlu olan tek sütun öğrenci adıdır."""
from __future__ import annotations

from dataclasses import dataclass, field

import openpyxl

from .db import Database

# Her alan için kabul edilen sütun başlığı varyasyonları (küçük harfe
# çevrilip boşluklar sadeleştirilerek karşılaştırılır).
_NAME_HEADERS = {"ad", "isim", "ad soyad", "öğrenci adı", "ogrenci adi", "adı"}
_CLASS_HEADERS = {"sınıf", "sinif"}
_COACH_HEADERS = {"koç", "koc", "koçu", "kocu"}
_PROGRAM_FEE_HEADERS = {"program ücreti", "program ucreti", "sınıf ücreti", "sinif ucreti"}
_ONE_ON_ONE_FEE_HEADERS = {"birebir ücreti", "birebir ucreti"}
_TITLE_HEADERS = {"ünvan", "unvan", "ünvan/paket", "paket", "dersler", "aldığı dersler", "aldigi dersler"}

TEMPLATE_HEADERS = ["Ad", "Sınıf", "Koç", "Program Ücreti", "Birebir Ücreti", "Ünvan"]
TEMPLATE_EXAMPLE_ROW = ["Zeynep Yıldız", "9-A", "Ahmet Yılmaz", 8000, 3000, "Sınıf, Birebir"]


def _normalize_header(text) -> str:
    return " ".join(str(text).strip().lower().split())


def _to_float(value) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class ImportRow:
    row_number: int  # Excel'deki satır numarası (başlık = 1)
    name: str
    class_name: str | None
    coach_name: str | None
    program_fee: float
    one_on_one_fee: float
    title_names: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ImportError_(Exception):
    """Dosya hiç okunamadı ya da 'Ad' sütunu bulunamadı."""


def parse_student_workbook(path: str, db: Database) -> list[ImportRow]:
    """Excel dosyasını okuyup ImportRow listesine çevirir. Veritabanına
    hiçbir şey YAZMAZ - sadece önizleme için ayrıştırır (bkz. apply_import)."""
    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise ImportError_(f"Dosya açılamadı: {exc}") from exc

    sheet = workbook.active
    rows_iter = sheet.iter_rows(values_only=True)
    header = next(rows_iter, None)
    if not header:
        raise ImportError_("Dosya boş görünüyor.")

    col_index: dict[str, int] = {}
    for i, cell in enumerate(header):
        if cell is None:
            continue
        key = _normalize_header(cell)
        if key in _NAME_HEADERS:
            col_index["name"] = i
        elif key in _CLASS_HEADERS:
            col_index["class"] = i
        elif key in _COACH_HEADERS:
            col_index["coach"] = i
        elif key in _PROGRAM_FEE_HEADERS:
            col_index["program_fee"] = i
        elif key in _ONE_ON_ONE_FEE_HEADERS:
            col_index["one_on_one_fee"] = i
        elif key in _TITLE_HEADERS:
            col_index["titles"] = i

    if "name" not in col_index:
        raise ImportError_(
            "'Ad' sütunu bulunamadı. İlk satırda öğrenci adının olduğu sütunun başlığı "
            "'Ad', 'İsim' ya da 'Ad Soyad' olmalı (bkz. 'Şablon İndir')."
        )

    existing_classes = {c["name"].strip().lower() for c in db.list_class_groups()}
    existing_teachers = {t["name"].strip().lower() for t in db.list_teachers()}
    existing_titles = {t["name"].strip().lower() for t in db.list_rows("titles")}

    def cell_value(row, key):
        idx = col_index.get(key)
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    results: list[ImportRow] = []
    for row_number, row in enumerate(rows_iter, start=2):
        name = str(cell_value(row, "name") or "").strip()
        if not name:
            continue  # tamamen boş/adsız satırları sessizce atla

        class_name = str(cell_value(row, "class") or "").strip() or None
        coach_name = str(cell_value(row, "coach") or "").strip() or None
        titles_raw = str(cell_value(row, "titles") or "").strip()
        title_names = [t.strip() for t in titles_raw.split(",") if t.strip()]

        warnings: list[str] = []
        if class_name and class_name.lower() not in existing_classes:
            warnings.append(f"'{class_name}' sınıfı yok - oluşturulup oluşturulmayacağını seçebilirsiniz")
        if coach_name and coach_name.lower() not in existing_teachers:
            warnings.append(f"'{coach_name}' adında öğretmen bulunamadı - koç boş bırakılacak")
        for t in title_names:
            if t.lower() not in existing_titles:
                warnings.append(f"'{t}' ünvanı yok - yeni oluşturulacak")

        results.append(
            ImportRow(
                row_number=row_number,
                name=name,
                class_name=class_name,
                coach_name=coach_name,
                program_fee=_to_float(cell_value(row, "program_fee")),
                one_on_one_fee=_to_float(cell_value(row, "one_on_one_fee")),
                title_names=title_names,
                warnings=warnings,
            )
        )
    return results


def apply_import(db: Database, rows: list[ImportRow], create_class_names: set[str] | None = None) -> int:
    """Ayrıştırılmış satırları veritabanına yazar (eksik ünvanları her
    zaman otomatik oluşturur, eksik koç varsa boş bırakır). Kaç öğrenci
    eklendiğini döner.

    `create_class_names`: küçük harfe çevrilmiş sınıf adlarından oluşan
    bir küme - Excel'de olup sistemde henüz olmayan sınıflardan SADECE bu
    kümedekiler oluşturulur; kümede olmayanlar için öğrenci sınıfsız
    (class_id=None) eklenir. None verilirse (varsayılan) eskisi gibi
    eksik olan TÜM sınıflar oluşturulur - kullanıcı hangi eksik sınıfların
    oluşturulacağını seçebilsin diye eklendi (bkz. ImportStudentsDialog)."""
    class_cache = {c["name"].strip().lower(): c["id"] for c in db.list_class_groups()}
    teacher_cache = {t["name"].strip().lower(): t["id"] for t in db.list_teachers()}
    title_cache = {t["name"].strip().lower(): t["id"] for t in db.list_rows("titles")}

    imported = 0
    for row in rows:
        class_id = None
        if row.class_name:
            key = row.class_name.lower()
            if key in class_cache:
                class_id = class_cache[key]
            elif create_class_names is None or key in create_class_names:
                class_cache[key] = db.add_class_group(row.class_name)
                class_id = class_cache[key]
            # else: kullanıcı bu sınıfın oluşturulmasını istemedi - öğrenci
            # sınıfsız (class_id=None) eklenecek.

        coach_id = teacher_cache.get(row.coach_name.lower()) if row.coach_name else None

        title_ids = []
        for name in row.title_names:
            key = name.lower()
            if key not in title_cache:
                title_cache[key] = db.add_row("titles", name)
            title_ids.append(title_cache[key])

        student_id = db.add_student(row.name, class_id, coach_id, row.program_fee, row.one_on_one_fee)
        if title_ids:
            db.set_student_titles(student_id, title_ids)
        imported += 1

    return imported


def write_template(path: str) -> None:
    """Kullanıcının doldurup yükleyebileceği örnek/boş bir Excel şablonu
    oluşturur - beklenen sütun başlıklarını ve bir örnek satırı içerir."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Öğrenciler"
    sheet.append(TEMPLATE_HEADERS)
    sheet.append(TEMPLATE_EXAMPLE_ROW)
    for column_cells in sheet.columns:
        length = max(len(str(cell.value)) for cell in column_cells if cell.value is not None)
        sheet.column_dimensions[column_cells[0].column_letter].width = max(12, length + 4)
    for cell in sheet[1]:
        cell.font = openpyxl.styles.Font(bold=True)
    workbook.save(path)
