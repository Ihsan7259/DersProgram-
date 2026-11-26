"""Excel'den (.xlsx) toplu öğrenci içe aktarma.

Kullanıcı tek tek öğrenci eklemek yerine bir Excel dosyası hazırlayıp
(ya da "Şablon İndir" ile hazır bir şablon alıp) yükleyebilir. Sütun
başlıkları esnek eşleşir (büyük/küçük harf, Türkçe karakter farkı
önemli değil); zorunlu olan tek sütun öğrenci adıdır. Öğrenci numarası
verilen satırlar numaraya göre güncellenir, numarasız satırlar yeni eklenir."""
from __future__ import annotations

from dataclasses import dataclass, field

import openpyxl

from .db import Database

# Her alan için kabul edilen sütun başlığı varyasyonları (küçük harfe
# çevrilip boşluklar sadeleştirilerek karşılaştırılır).
_NAME_HEADERS = {"ad", "isim", "ad soyad", "öğrenci adı", "ogrenci adi", "adı"}
_STUDENT_NUMBER_HEADERS = {
    "öğrenci no", "ogrenci no", "öğrenci numarası", "ogrenci numarasi",
    "öğrenci num.", "ogrenci num.", "student no", "student number",
}
_CLASS_HEADERS = {"sınıf", "sinif"}
_COACH_HEADERS = {"koç", "koc", "koçu", "kocu"}
_PROGRAM_FEE_HEADERS = {"program ücreti", "program ucreti", "sınıf ücreti", "sinif ucreti"}
_ONE_ON_ONE_FEE_HEADERS = {"birebir ücreti", "birebir ucreti"}
_TITLE_HEADERS = {"ünvan", "unvan", "ünvan/paket", "paket", "dersler", "aldığı dersler", "aldigi dersler"}

TEMPLATE_HEADERS = ["Öğrenci No", "Ad", "Sınıf", "Koç", "Program Ücreti", "Birebir Ücreti", "Ünvan"]
TEMPLATE_EXAMPLE_ROW = ["", "Zeynep Yıldız", "9-A", "Ahmet Yılmaz", 8000, 3000, "Sınıf, Birebir"]


def _normalize_header(text) -> str:
    return " ".join(str(text).strip().lower().split())


def _to_optional_float(value) -> float | None:
    # Boş hücre "değiştirme" demek (None); mevcut öğrencide eski ücret korunur.
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_student_number(value) -> str | None:
    if value is None or value == "":
        return None
    # Excel sayıları float okur: 123.0 -> "123"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    number = str(value).strip()
    return number or None


@dataclass
class ImportRow:
    row_number: int  # Excel'deki satır numarası (başlık = 1)
    name: str
    student_number: str | None
    class_name: str | None
    coach_name: str | None
    program_fee: float | None
    one_on_one_fee: float | None
    title_names: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    existing_student_id: int | None = None


@dataclass
class ImportResult:
    added: int = 0
    updated: int = 0


class ImportError_(Exception):
    """Dosya okunamadı veya satırlar güvenli biçimde içe aktarılamadı."""


def parse_student_workbook(path: str, db: Database) -> list[ImportRow]:
    """Excel dosyasını okuyup ImportRow listesine çevirir. Veritabanına
    hiçbir şey YAZMAZ - sadece önizleme için ayrıştırır (bkz. apply_import)."""
    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise ImportError_(f"Dosya açılamadı: {exc}") from exc
    # Satırlar hemen okunup dosya kapatılır (read_only modda dosya açık kalıyordu).
    try:
        workbook_rows = list(workbook.active.iter_rows(values_only=True))
    finally:
        workbook.close()

    rows_iter = iter(workbook_rows)
    header = next(rows_iter, None)
    if not header:
        raise ImportError_("Dosya boş görünüyor.")

    col_index: dict[str, int] = {}
    for i, cell in enumerate(header):
        if cell is None:
            continue
        key = _normalize_header(cell)
        if key in _STUDENT_NUMBER_HEADERS:
            if "student_number" in col_index:
                raise ImportError_("Birden fazla öğrenci numarası sütunu bulundu.")
            col_index["student_number"] = i
        elif key in _NAME_HEADERS:
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
    seen_student_numbers: dict[str, int] = {}
    for row_number, row in enumerate(rows_iter, start=2):
        name = str(cell_value(row, "name") or "").strip()
        if not name:
            continue  # tamamen boş/adsız satırları sessizce atla

        student_number = _to_student_number(cell_value(row, "student_number"))
        if student_number:
            number_key = student_number.casefold()
            if number_key in seen_student_numbers:
                first_row = seen_student_numbers[number_key]
                raise ImportError_(
                    f"Öğrenci numarası '{student_number}' dosyada {first_row}. ve {row_number}. satırlarda "
                    "tekrarlanıyor. Her numara yalnızca bir kez bulunmalı."
                )
            seen_student_numbers[number_key] = row_number

        class_name = str(cell_value(row, "class") or "").strip() or None
        coach_name = str(cell_value(row, "coach") or "").strip() or None
        titles_raw = str(cell_value(row, "titles") or "").strip()
        title_names = [t.strip() for t in titles_raw.split(",") if t.strip()]

        warnings: list[str] = []
        existing_student_id = None
        if student_number:
            try:
                existing_student = db.find_student_by_number(student_number)
            except ValueError as exc:
                raise ImportError_(str(exc)) from exc
            if existing_student:
                existing_student_id = existing_student["id"]
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
                student_number=student_number,
                class_name=class_name,
                coach_name=coach_name,
                program_fee=_to_optional_float(cell_value(row, "program_fee")),
                one_on_one_fee=_to_optional_float(cell_value(row, "one_on_one_fee")),
                title_names=title_names,
                warnings=warnings,
                existing_student_id=existing_student_id,
            )
        )
    return results


def apply_import(
    db: Database,
    rows: list[ImportRow],
    create_class_names: set[str] | None = None,
) -> ImportResult:
    """Ayrıştırılmış satırları veritabanına yazar. Dolu öğrenci numaraları
    eşleşirse mevcut öğrenci güncellenir; numarasız satır yeni eklenir.
    Mevcut kayıtta boş bırakılan isteğe bağlı alanlar korunur.

    `create_class_names`: küçük harfe çevrilmiş sınıf adlarından oluşan
    bir küme - Excel'de olup sistemde henüz olmayan sınıflardan SADECE bu
    kümedekiler oluşturulur; kümede olmayanlar için öğrenci sınıfsız
    (class_id=None) eklenir. None verilirse (varsayılan) eskisi gibi
    eksik olan TÜM sınıflar oluşturulur - kullanıcı hangi eksik sınıfların
    oluşturulacağını seçebilsin diye eklendi (bkz. ImportStudentsDialog)."""
    class_cache = {c["name"].strip().lower(): c["id"] for c in db.list_class_groups()}
    teacher_cache = {t["name"].strip().lower(): t["id"] for t in db.list_teachers()}
    title_cache = {t["name"].strip().lower(): t["id"] for t in db.list_rows("titles")}

    # Yazmaya başlamadan önce: aynı numara iki satırda olmamalı.
    seen_student_numbers = set()
    for row in rows:
        if not row.student_number:
            continue
        number_key = row.student_number.strip().casefold()
        if number_key in seen_student_numbers:
            raise ImportError_(f"Öğrenci numarası '{row.student_number}' birden fazla satırda bulunuyor.")
        seen_student_numbers.add(number_key)

    result = ImportResult()
    for row in rows:
        existing_student = db.find_student_by_number(row.student_number) if row.student_number else None
        class_id = existing_student["class_group_id"] if existing_student else None
        if row.class_name:
            key = row.class_name.lower()
            if key in class_cache:
                class_id = class_cache[key]
            elif create_class_names is None or key in create_class_names:
                class_cache[key] = db.add_class_group(row.class_name)
                class_id = class_cache[key]
            # else: kullanıcı bu sınıfın oluşturulmasını istemedi - öğrenci
            # sınıfsız (class_id=None) eklenecek.

        coach_id = existing_student["coach_teacher_id"] if existing_student else None
        if row.coach_name:
            coach_id = teacher_cache.get(row.coach_name.lower())

        title_ids = []
        for name in row.title_names:
            key = name.lower()
            if key not in title_cache:
                title_cache[key] = db.add_row("titles", name)
            title_ids.append(title_cache[key])

        program_fee = row.program_fee
        one_on_one_fee = row.one_on_one_fee
        if existing_student:
            if program_fee is None:
                program_fee = existing_student["total_program_fee"]
            if one_on_one_fee is None:
                one_on_one_fee = existing_student["total_one_on_one_fee"]
            db.update_student(
                existing_student["id"], row.name, class_id, coach_id, program_fee, one_on_one_fee,
                note=existing_student["note"] or "",
                student_number=row.student_number,
                study_room_id=existing_student["study_room_id"],
            )
            student_id = existing_student["id"]
            result.updated += 1
        else:
            student_id = db.add_student(
                row.name, class_id, coach_id, program_fee or 0, one_on_one_fee or 0,
                student_number=row.student_number,
            )
            result.added += 1
        if title_ids:
            db.set_student_titles(student_id, title_ids)

    return result


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
