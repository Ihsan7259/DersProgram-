"""Program motoru: hafta hesaplama, şablon+istisna birleştirme, yerleştirme,
çakışma kontrolü ve oto-atama.

Bu modül db.py'nin ham CRUD fonksiyonlarını kullanarak "bu hafta ekranda
ne görünmeli" sorusuna cevap verir.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field

from .db import (
    Database,
    LESSON_TYPE_LABELS,
    TYPE_CLASS,
    TYPE_ONE_ON_ONE,
    TYPE_COACHING,
    TYPE_DEPARTMENT,
)

SCOPE_WEEK_ONLY = "week"
SCOPE_ALWAYS = "always"


def monday_of(d: _dt.date) -> _dt.date:
    return d - _dt.timedelta(days=d.weekday())


def week_key(week_start: _dt.date) -> str:
    return week_start.isoformat()


def week_label(week_start: _dt.date, day_count: int) -> str:
    end = week_start + _dt.timedelta(days=max(day_count - 1, 0))
    return f"{week_start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"


_DAY_ABBREV = {
    "Pazartesi": "Pzt",
    "Salı": "Sal",
    "Çarşamba": "Çar",
    "Perşembe": "Per",
    "Cuma": "Cum",
    "Cumartesi": "Cmt",
    "Pazar": "Paz",
}


def day_abbrev(day_name: str) -> str:
    return _DAY_ABBREV.get(day_name, day_name[:3])


def natural_sort_key(text: str):
    """'10-A' sıralamada '9-A'dan sonra gelsin diye (metin sıralamasında
    '1' < '9' olduğundan '10-A' yanlışlıkla önce gelirdi)."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def short_teacher_name(name: str | None) -> str:
    """'Ahmet Yılmaz' -> 'A. Yılmaz' (dar hücrelerde yer kazanmak için)."""
    if not name:
        return ""
    parts = name.split()
    if len(parts) < 2:
        return name
    return f"{parts[0][0]}. {' '.join(parts[1:])}"


@dataclass
class BlockView:
    id: int
    type: str
    teacher_id: int | None
    teacher_name: str | None
    subject_id: int | None
    subject_name: str | None
    class_group_id: int | None
    class_name: str | None
    student_id: int | None
    student_name: str | None
    room_id: int | None
    room_name: str | None
    note: str
    day: int | None = None
    period: int | None = None
    student_class_group_id: int | None = None
    zumre_group_id: int | None = None

    def short_label(self) -> str:
        type_label = LESSON_TYPE_LABELS.get(self.type, self.type)
        parts = [type_label]
        if self.subject_name:
            parts.append(self.subject_name)
        if self.class_name:
            parts.append(self.class_name)
        if self.student_name:
            parts.append(self.student_name)
        if self.teacher_name:
            parts.append(self.teacher_name)
        return "\n".join(parts)

    def pool_label(self) -> str:
        type_label = LESSON_TYPE_LABELS.get(self.type, self.type)
        bits = [type_label]
        if self.class_name:
            bits.append(self.class_name)
        if self.student_name:
            bits.append(self.student_name)
        if self.subject_name:
            bits.append(self.subject_name)
        if self.teacher_name:
            bits.append(f"({self.teacher_name})")
        return " · ".join(bits)

    _TYPE_ABBREV = {
        TYPE_CLASS: "SD",
        TYPE_ONE_ON_ONE: "BB",
        TYPE_COACHING: "Koç",
        TYPE_DEPARTMENT: "Züm",
    }

    def pool_label_short(self) -> str:
        """Havuzda yer kazanmak için kısaltılmış etiket (tam metin tooltip'te)."""
        type_abbrev = self._TYPE_ABBREV.get(self.type, "SÇ")
        bits = [type_abbrev]
        if self.class_name:
            bits.append(self.class_name)
        if self.student_name:
            bits.append(self.student_name.split()[0])
        if self.subject_name:
            bits.append(self.subject_name[:4])
        if self.teacher_name:
            bits.append(short_teacher_name(self.teacher_name))
        return " · ".join(bits)

    def card_lines(self) -> tuple[str, str, str]:
        """Renkli hücre kartında gösterilecek 3 satır: (başlık, alt, öğretmen)."""
        if self.type == TYPE_CLASS:
            return self.subject_name or "Sınıf Dersi", self.class_name or "", self.teacher_name or ""
        if self.type == TYPE_ONE_ON_ONE:
            return self.subject_name or "Birebir", self.student_name or "", self.teacher_name or ""
        if self.type == TYPE_COACHING:
            return "Öğrenci Koçluk", self.student_name or "", self.teacher_name or ""
        if self.type == TYPE_DEPARTMENT:
            return "Zümre", self.subject_name or "", self.teacher_name or ""
        return "Soru Çözümü", self.subject_name or "", self.teacher_name or ""

    def class_row_lines(self) -> tuple[str, str]:
        """Sınıfın kendi haftalık programında gösterilecek iki satır:
        ders adı ve öğretmen adı (sınıf adı zaten belli, tekrar edilmez)."""
        if self.type == TYPE_CLASS:
            return self.subject_name or "Sınıf Dersi", self.teacher_name or ""
        label = LESSON_TYPE_LABELS.get(self.type, self.type)
        if self.subject_name:
            label = f"{label} · {self.subject_name}"
        return label, self.teacher_name or ""

    def teacher_row_lines(self) -> tuple[str, str]:
        """Öğretmenin kendi haftalık programında (ve önizlemesinde)
        gösterilecek iki satır: sınıf/öğrenci adı ve branş - öğretmen adı
        zaten belli olduğu için branş yerine kiminle olduğu öne çıkar."""
        if self.type == TYPE_CLASS:
            return self.class_name or "Sınıf Dersi", self.subject_name or ""
        if self.type == TYPE_ONE_ON_ONE:
            return self.student_name or "Birebir", self.subject_name or ""
        if self.type == TYPE_COACHING:
            return "Öğrenci Koçluk", self.student_name or ""
        if self.type == TYPE_DEPARTMENT:
            return "Zümre", self.subject_name or ""
        return "Soru Çözümü", self.subject_name or ""

    def student_row_lines(self) -> tuple[str, str]:
        """Öğrencinin kendi haftalık programında (ve önizlemesinde)
        gösterilecek iki satır: ders/tür adı ve öğretmen adı - öğrenci adı
        zaten belli olduğu için tekrar edilmez (bkz. scheduling.
        student_effective_blocks - burada hem öğrencinin kişisel bloğu hem
        de sınıfının ortak ders bloğu aynı satırda görünebilir)."""
        if self.type == TYPE_COACHING:
            return "Öğrenci Koçluk", self.teacher_name or ""
        if self.type == TYPE_DEPARTMENT:
            return "Zümre", self.teacher_name or ""
        label = self.subject_name or LESSON_TYPE_LABELS.get(self.type, self.type)
        return label, self.teacher_name or ""

    def dense_lines(self, row_mode: str) -> tuple[str, str]:
        """Kurum geneli ızgarada (satır=sınıf/öğretmen/öğrenci) hücrede
        gösterilecek iki kısa satır. Satırın kendisi zaten kim olduğunu
        belli ettiği için o bilgi tekrar edilmez."""
        if row_mode == "class":
            return self.subject_name or "Ders", short_teacher_name(self.teacher_name)
        if row_mode == "student":
            if self.type == TYPE_COACHING:
                return "Koçluk", short_teacher_name(self.teacher_name)
            if self.type == TYPE_DEPARTMENT:
                return "Zümre", short_teacher_name(self.teacher_name)
            return self.subject_name or "Ders", short_teacher_name(self.teacher_name)
        if self.type == TYPE_CLASS:
            return self.class_name or "Ders", self.subject_name or ""
        if self.type == TYPE_ONE_ON_ONE:
            return self.student_name or "Birebir", self.subject_name or ""
        if self.type == TYPE_COACHING:
            return "Koçluk", self.student_name or ""
        if self.type == TYPE_DEPARTMENT:
            return "Zümre", self.subject_name or ""
        return "Soru Çöz.", self.subject_name or ""

    def group_key(self):
        """Aynı ihtiyaçtan gelen (ör. '9-A Matematik, X öğretmeni, haftada
        4 saat') blokları gruplamak için kullanılır; oto-atamada aynı
        gruptaki dersleri günlere yaymak için kullanılır."""
        return (self.type, self.teacher_id, self.class_group_id, self.student_id, self.subject_id)


def _row_to_blockview(row) -> BlockView:
    return BlockView(
        id=row["id"],
        type=row["type"],
        teacher_id=row["teacher_id"],
        teacher_name=row["teacher_name"],
        subject_id=row["subject_id"],
        subject_name=row["subject_name"],
        class_group_id=row["class_group_id"],
        class_name=row["class_name"],
        student_id=row["student_id"],
        student_name=row["student_name"],
        room_id=row["room_id"],
        room_name=row["room_name"],
        note=row["note"] or "",
        student_class_group_id=row["student_class_group_id"],
        zumre_group_id=row["zumre_group_id"],
    )


def get_week_view(db: Database, week_start: _dt.date) -> tuple[dict[tuple[int, int], list[BlockView]], list[BlockView]]:
    """Verilen haftanın efektif programını döner: (gün,saat) -> [BlockView,...]
    ve o hafta atanmamış (havuzdaki) blokların listesi."""
    wkey = week_key(week_start)
    exceptions = db.get_week_exceptions(wkey)
    all_blocks = db.list_lesson_blocks_detailed()

    schedule: dict[tuple[int, int], list[BlockView]] = {}
    pool: list[BlockView] = []

    for row in all_blocks:
        block = _row_to_blockview(row)
        if row["id"] in exceptions:
            day, period = exceptions[row["id"]]
        else:
            day, period = row["template_day"], row["template_period"]

        if day is None or period is None:
            pool.append(block)
        else:
            block.day, block.period = day, period
            schedule.setdefault((day, period), []).append(block)

    return schedule, pool


@dataclass
class UnavailableSlots:
    """Öğretmen/öğrenci/sınıfların kendi işaretledikleri 'müsait değil'
    saatlerin (o hafta için efektif) kümeleri; find_conflicts bunlara
    bakarak yerleştirmeyi engeller (bkz. get_teacher_availability vb.)."""

    teacher: set[tuple[int, int, int]] = field(default_factory=set)
    student: set[tuple[int, int, int]] = field(default_factory=set)
    class_: set[tuple[int, int, int]] = field(default_factory=set)

    @classmethod
    def compute(cls, db: Database, week_start: _dt.date) -> "UnavailableSlots":
        return cls(
            teacher=get_all_unavailable_slots(db, week_start),
            student=get_all_unavailable_student_slots(db, week_start),
            class_=get_all_unavailable_class_slots(db, week_start),
        )


def find_conflicts(
    schedule: dict[tuple[int, int], list[BlockView]],
    day: int,
    period: int,
    block: BlockView,
    unavailable: "UnavailableSlots | None" = None,
) -> list[str]:
    """Bir bloğu (day, period)'a koymanın doğuracağı çakışmaları
    insan-okunur mesajlar olarak döner. Boş liste = sorun yok."""
    reasons = []
    if unavailable:
        if block.teacher_id is not None and (block.teacher_id, day, period) in unavailable.teacher:
            reasons.append(f"{block.teacher_name} bu saatte müsait değil olarak işaretlenmiş")
        if block.student_id is not None and (block.student_id, day, period) in unavailable.student:
            reasons.append(f"{block.student_name} bu saatte müsait değil olarak işaretlenmiş")
        if block.class_group_id is not None and (block.class_group_id, day, period) in unavailable.class_:
            reasons.append(f"{block.class_name} bu saatte müsait değil olarak işaretlenmiş")
    for other in schedule.get((day, period), []):
        if other.id == block.id:
            continue
        if block.teacher_id is not None and other.teacher_id == block.teacher_id:
            reasons.append(f"{other.teacher_name} bu saatte zaten dolu")
        if block.class_group_id is not None and other.class_group_id == block.class_group_id:
            reasons.append(f"{other.class_name} bu saatte başka bir derste")
        if block.student_id is not None and other.student_id == block.student_id:
            reasons.append(f"{other.student_name} bu saatte başka bir derste")
        if block.room_id is not None and other.room_id is not None and other.room_id == block.room_id:
            reasons.append(f"{other.room_name} bu saatte dolu")
        # Bir öğrencinin birebir/koçluk dersi, kendi sınıfının o saatteki
        # sınıf dersiyle çakışmamalı (öğrenci fiziksel olarak iki yerde
        # birden olamaz).
        if (
            block.student_id is not None
            and block.student_class_group_id is not None
            and other.type == TYPE_CLASS
            and other.class_group_id == block.student_class_group_id
        ):
            reasons.append(f"{block.student_name}'in sınıfı ({other.class_name}) bu saatte ders var")
        if (
            block.type == TYPE_CLASS
            and other.student_id is not None
            and other.student_class_group_id == block.class_group_id
        ):
            reasons.append(f"{other.student_name} bu saatte kendi sınıfının ({block.class_name}) dersinde olmalı")
    return reasons


def find_group_conflicts(
    schedule: dict[tuple[int, int], list[BlockView]],
    day: int,
    period: int,
    blocks: list[BlockView],
    unavailable: "UnavailableSlots | None" = None,
) -> list[str]:
    """find_conflicts'ın bir grup (ör. bir zümre buluşmasındaki tüm
    öğretmen blokları) için toplu hali: gruptaki herhangi bir üyenin bu
    (day, period)'a yerleşmesi bir çakışma doğuruyorsa, o üyenin
    mesajları da sonuca eklenir - grup ancak HİÇBİR üye çakışmıyorsa
    yerleştirilebilir."""
    reasons: list[str] = []
    for block in blocks:
        reasons.extend(find_conflicts(schedule, day, period, block, unavailable))
    return reasons


def place_block(db: Database, week_start: _dt.date, block_id: int, day: int, period: int, scope: str) -> None:
    if scope == SCOPE_ALWAYS:
        db.set_lesson_block_template_position(block_id, day, period)
        db.clear_week_exception(week_key(week_start), block_id)
    else:
        db.set_week_exception(week_key(week_start), block_id, day, period)


def clear_block(db: Database, week_start: _dt.date, block_id: int, scope: str) -> None:
    if scope == SCOPE_ALWAYS:
        db.set_lesson_block_template_position(block_id, None, None)
        db.clear_week_exception(week_key(week_start), block_id)
    else:
        db.set_week_exception(week_key(week_start), block_id, None, None)


def get_teacher_availability(db: Database, teacher_id: int, week_start: _dt.date) -> dict[tuple[int, int], str]:
    """Bir öğretmenin o haftaki efektif müsaitlik durumunu döner:
    (day, period) -> 'available' | 'unavailable'. İşaretlenmemiş hücreler
    sözlükte yer almaz (durum yok = kısıtlama yok)."""
    result = dict(db.get_teacher_availability_template(teacher_id))
    exceptions = db.get_teacher_availability_exceptions(week_key(week_start))
    for (t_id, day, period), status in exceptions.items():
        if t_id != teacher_id:
            continue
        if status == "clear":
            result.pop((day, period), None)
        else:
            result[(day, period)] = status
    return result


def _compute_unavailable_slots(
    entity_ids: list[int],
    templates_by_entity: dict[int, dict[tuple[int, int], str]],
    exceptions_flat: dict[tuple[int, int, int], str],
) -> set[tuple[int, int, int]]:
    """get_all_unavailable_*_slots fonksiyonlarının ortak hesaplama
    mantığı: her varlık için şablon + o haftaki istisnaları birleştirip
    'müsait değil' olanları toplar.

    Önceden her varlık için ayrı ayrı get_..._availability_exceptions(week)
    çağrılıyordu - bu fonksiyon TÜM haftanın istisnalarını (zaten tek
    sorguda gelen exceptions_flat) tek seferde varlık bazında gruplar,
    böylece N varlık için veritabanına N kez gidilmesi gerekmez (bkz.
    get_all_teacher_availability_templates/get_teacher_availability_exceptions
    çağrıları - Ana Program'ı açarken 100 öğretmen/öğrenci/sınıf olduğunda
    bu N+1 sorgu deseni asıl takılma sebeplerinden biriydi)."""
    exceptions_by_entity: dict[int, dict[tuple[int, int], str]] = {}
    for (entity_id, day, period), status in exceptions_flat.items():
        exceptions_by_entity.setdefault(entity_id, {})[(day, period)] = status

    slots: set[tuple[int, int, int]] = set()
    for entity_id in entity_ids:
        merged = dict(templates_by_entity.get(entity_id, {}))
        for (day, period), status in exceptions_by_entity.get(entity_id, {}).items():
            if status == "clear":
                merged.pop((day, period), None)
            else:
                merged[(day, period)] = status
        for (day, period), status in merged.items():
            if status == "unavailable":
                slots.add((entity_id, day, period))
    return slots


def get_all_unavailable_slots(db: Database, week_start: _dt.date) -> set[tuple[int, int, int]]:
    """Tüm öğretmenler için o hafta 'müsait değil' işaretli
    (teacher_id, day, period) üçlülerinin kümesi."""
    entity_ids = [row["id"] for row in db.list_teachers()]
    templates = db.get_all_teacher_availability_templates()
    exceptions = db.get_teacher_availability_exceptions(week_key(week_start))
    return _compute_unavailable_slots(entity_ids, templates, exceptions)


def set_teacher_availability(
    db: Database, week_start: _dt.date, teacher_id: int, day: int, period: int, status: str | None, scope: str
) -> None:
    if scope == SCOPE_ALWAYS:
        db.set_teacher_availability_template(teacher_id, day, period, status)
        db.clear_teacher_availability_exception(week_key(week_start), teacher_id, day, period)
    else:
        db.set_teacher_availability_exception(week_key(week_start), teacher_id, day, period, status or "clear")


def get_student_availability(db: Database, student_id: int, week_start: _dt.date) -> dict[tuple[int, int], str]:
    result = dict(db.get_student_availability_template(student_id))
    exceptions = db.get_student_availability_exceptions(week_key(week_start))
    for (s_id, day, period), status in exceptions.items():
        if s_id != student_id:
            continue
        if status == "clear":
            result.pop((day, period), None)
        else:
            result[(day, period)] = status
    return result


def get_all_unavailable_student_slots(db: Database, week_start: _dt.date) -> set[tuple[int, int, int]]:
    entity_ids = [row["id"] for row in db.list_students()]
    templates = db.get_all_student_availability_templates()
    exceptions = db.get_student_availability_exceptions(week_key(week_start))
    return _compute_unavailable_slots(entity_ids, templates, exceptions)


def set_student_availability(
    db: Database, week_start: _dt.date, student_id: int, day: int, period: int, status: str | None, scope: str
) -> None:
    if scope == SCOPE_ALWAYS:
        db.set_student_availability_template(student_id, day, period, status)
        db.clear_student_availability_exception(week_key(week_start), student_id, day, period)
    else:
        db.set_student_availability_exception(week_key(week_start), student_id, day, period, status or "clear")


def get_class_availability(db: Database, class_group_id: int, week_start: _dt.date) -> dict[tuple[int, int], str]:
    result = dict(db.get_class_availability_template(class_group_id))
    exceptions = db.get_class_availability_exceptions(week_key(week_start))
    for (c_id, day, period), status in exceptions.items():
        if c_id != class_group_id:
            continue
        if status == "clear":
            result.pop((day, period), None)
        else:
            result[(day, period)] = status
    return result


def get_all_unavailable_class_slots(db: Database, week_start: _dt.date) -> set[tuple[int, int, int]]:
    entity_ids = [row["id"] for row in db.list_class_groups()]
    templates = db.get_all_class_availability_templates()
    exceptions = db.get_class_availability_exceptions(week_key(week_start))
    return _compute_unavailable_slots(entity_ids, templates, exceptions)


def set_class_availability(
    db: Database, week_start: _dt.date, class_group_id: int, day: int, period: int, status: str | None, scope: str
) -> None:
    if scope == SCOPE_ALWAYS:
        db.set_class_availability_template(class_group_id, day, period, status)
        db.clear_class_availability_exception(week_key(week_start), class_group_id, day, period)
    else:
        db.set_class_availability_exception(week_key(week_start), class_group_id, day, period, status or "clear")


@dataclass
class AutoAssignResult:
    placed: int
    warnings: list[str]
    placed_block_ids: list[int] = field(default_factory=list)


def _teacher_capacity_warnings(
    db: Database,
    pool: list[BlockView],
    schedule: dict[tuple[int, int], list[BlockView]],
    unavailable: "UnavailableSlots",
    day_count: int,
    period_count: int,
) -> list[str]:
    """Oto ata çalışmadan ÖNCE, en bariz imkansızlık türünü (bir
    öğretmenin haftalık boş kapasitesinden fazla ders istenmesi) ucuz bir
    sayımla tespit eder - ör. 'Ahmet Yılmaz: 8 saat boş kapasitesi var ama
    10 saat ders bekliyor'. Bu, tek başına diğer kısıtları (sınıf/derslik/
    öğrenci çakışmaları, art arda/bitişiklik kuralı) hesaba katmaz - o
    yüzden daha ince imkansızlıklar (bkz. _shortfall_warnings) çözücünün
    kendisinden gelir; burası sadece en açık/erken uyarıyı verir."""
    demand_by_teacher: dict[int, int] = {}
    for b in pool:
        if b.teacher_id is not None:
            demand_by_teacher[b.teacher_id] = demand_by_teacher.get(b.teacher_id, 0) + 1
    if not demand_by_teacher:
        return []

    total_slots = day_count * period_count
    occupied_by_teacher: dict[int, int] = {}
    for blocks in schedule.values():
        for b in blocks:
            if b.teacher_id is not None:
                occupied_by_teacher[b.teacher_id] = occupied_by_teacher.get(b.teacher_id, 0) + 1
    unavailable_by_teacher: dict[int, int] = {}
    for (tid, _d, _p) in unavailable.teacher:
        unavailable_by_teacher[tid] = unavailable_by_teacher.get(tid, 0) + 1

    teacher_names = {t["id"]: t["name"] for t in db.list_teachers()}
    warnings: list[str] = []
    for tid, demand in demand_by_teacher.items():
        occupied = occupied_by_teacher.get(tid, 0)
        blocked = unavailable_by_teacher.get(tid, 0)
        capacity = max(0, total_slots - occupied - blocked)
        if demand > capacity:
            name = teacher_names.get(tid, f"Öğretmen #{tid}")
            warnings.append(
                f"{name}: bu hafta {capacity} saat boş kapasitesi var ama havuzda {demand} saat ders "
                f"bekliyor ({demand - capacity} saat matematiksel olarak sığmaz) - müsaitliğini gözden "
                "geçirin ya da bu derslerin bir kısmını başka bir öğretmene aktarın."
            )
    return warnings


def auto_assign(
    db: Database,
    week_start: _dt.date,
    max_consecutive: int = 2,
    time_limit_seconds: float = 120.0,
    quality_time_limit_seconds: float = 180.0,
    progress_callback=None,
    include_types: set[str] | None = None,
) -> AutoAssignResult:
    """Atanmamış dersleri (havuzu) bir kısıt çözücü (Google OR-Tools CP-SAT)
    ile, ÇAKIŞMASIZ ve mümkün olan en fazla ders sayısını yerleştirecek
    şekilde otomatik yerleştirir. Zaten elle/önceden yerleştirilmiş dersler
    (schedule) SABİT kabul edilir, sadece havuzdakiler için karar verilir.

    Önceki (açgözlü/sırayla dene) yöntem, hoca/sınıf sayısı arttıkça
    "erken yerleşen kolay dersler yüzünden zor bir ders için hiç yer
    kalmaması" durumuna düşebiliyordu. CP-SAT tüm dersleri BİRLİKTE
    değerlendirip, mümkünse hepsini, değilse mümkün olan en fazlasını
    çakışmasız yerleştirecek bir çözüm arar - tek tek sırayla denemekten
    çok daha güvenilir, özellikle çok sayıda öğretmen/sınıf olduğunda.

    Kısıtlar find_conflicts/find_group_conflicts ile birebir aynı mantığı
    kullanır (aynı öğretmen/sınıf/öğrenci/derslik aynı anda iki yerde
    olamaz, öğrenci kendi sınıfının dersiyle çakışamaz, müsait-değil
    işaretli saatlere girilemez, zümre grubundaki tüm hocalar aynı anda
    boş olmalı). Ayrıca aynı ihtiyaçtan gelen (ör. '9-A Matematik haftada
    4 saat') dersler bir günde en fazla `max_consecutive` saat art arda
    olacak şekilde SERT bir kısıtla sınırlanır (üstüne, mümkünse tek güne
    yığılmak yerine birden fazla güne de yayılması hafifçe ödüllendirilir).

    Yerleştirme HER HAFTA için kalıcıdır (SCOPE_ALWAYS), ama uygunluk
    kontrolü sadece bu haftanın müsaitlik durumuna bakar. Bu yüzden bir
    öğretmen bu haftaki (day, period) için müsaitse ama BAŞKA bir hafta
    için o saati özellikle 'müsait değil' işaretlemişse, kalıcı
    yerleştirme o haftayla çelişebilir; bu durumlar uyarı olarak
    döndürülür ki kullanıcı isterse o haftaları elle kontrol etsin.

    Atanmamış ders bırakmak yerine ("hız için" bir dersi havuzda bırakmak)
    ARAMA İKİ AŞAMADA yapılır: önce (time_limit_seconds bütçesiyle) SADECE
    kaç dersin yerleşebileceği maksimize edilir - bu daha basit bir hedef
    olduğu için genelde optimal'e (kanıtlanmış en iyi sonuca) hızlı ulaşır.
    Eğer bu aşama optimal'i KANITLAYIP hâlâ bazı dersleri yerleştiremiyorsa,
    bu gerçekten matematiksel bir imkansızlıktır (ör. bir öğretmenin
    müsaitliği/çakışmaları o kadar saati kaldıramıyor) ve ayrıntılı bir
    uyarı olarak döndürülür - "hız yetmedi" ile "gerçekten imkansız"
    birbirine karıştırılmaz. İkinci aşamada (quality_time_limit_seconds
    bütçesiyle) yerleştirme sayısı asla düşürülmeden (sert bir alt sınır
    olarak sabitlenir) kalan süre blok bütünlüğü/çeşitlilik/gün yayma
    tercihlerini iyileştirmek için kullanılır.

    `progress_callback`, verilirse `(yüzde: int, mesaj: str)` ile art arda
    çağrılır (ör. bir ilerleme diyaloğunu güncellemek için) - uzun süren
    aramalarda kullanıcıya "ne yapıldığı" hakkında geri bildirim vermek
    içindir, sonucu etkilemez.

    `include_types` verilirse (ör. {TYPE_CLASS, TYPE_COACHING}), havuzdaki
    SADECE bu türden dersler bu çalıştırmada değerlendirilir - diğer
    türdeki dersler dokunulmadan havuzda kalır. Varsayılan (None) tüm
    havuzu işler."""
    from ortools.sat.python import cp_model

    def report(pct: int, msg: str) -> None:
        if progress_callback is not None:
            progress_callback(min(100, max(0, pct)), msg)

    report(0, "Program verileri okunuyor...")

    day_count = len(db.day_names)
    day_names = db.day_names
    period_count = db.period_count
    this_week_key = week_key(week_start)

    schedule, pool = get_week_view(db, week_start)
    if include_types is not None:
        pool = [b for b in pool if b.type in include_types]
    unavailable = UnavailableSlots.compute(db, week_start)
    warnings: list[str] = []

    def cross_week_warning(block: BlockView, d: int, p: int) -> None:
        if block.teacher_id is None:
            return
        other_weeks = [
            w for w in db.get_teacher_unavailable_exception_weeks(block.teacher_id, d, p)
            if w != this_week_key
        ]
        if other_weeks:
            dates = ", ".join(_dt.date.fromisoformat(w).strftime("%d.%m.%Y") for w in other_weeks)
            warnings.append(
                f"{block.teacher_name}: {day_abbrev(day_names[d])} {p}. saat kalıcı olarak "
                f"yerleştirildi, ama bu saat şu hafta(lar) için 'müsait değil' işaretli: {dates}"
            )

    if not pool:
        report(100, "Atanmamış ders yok.")
        return AutoAssignResult(placed=0, warnings=warnings)

    # En bariz imkansızlığı (bir öğretmenin haftalık boş kapasitesinden
    # fazla ders istenmesi) çözücüyü hiç çalıştırmadan tespit et - bkz.
    # _teacher_capacity_warnings docstring'i.
    warnings.extend(_teacher_capacity_warnings(db, pool, schedule, unavailable, day_count, period_count))

    report(5, f"{len(pool)} ders saati için uygun yerler hesaplanıyor...")

    # ---------- havuzdaki dersleri "yerleştirme birimleri"ne ayır ----------
    # Zümre grubundaki bloklar (aynı zumre_group_id) her zaman BİRLİKTE
    # yerleşmeli - tek bir birim olarak ele alınır. Diğer her blok kendi
    # başına bir birimdir.
    units: list[list[BlockView]] = []
    seen_zumre: set[int] = set()
    for block in pool:
        if block.type == TYPE_DEPARTMENT and block.zumre_group_id is not None:
            if block.zumre_group_id in seen_zumre:
                continue
            seen_zumre.add(block.zumre_group_id)
            units.append([b for b in pool if b.zumre_group_id == block.zumre_group_id])
        else:
            units.append([block])

    all_slots = [(d, p) for d in range(day_count) for p in range(1, period_count + 1)]

    # Her birim için, sabit (zaten yerleşmiş) derslerle çakışmayan ve
    # müsaitlik kurallarını ihlal etmeyen (day, period) adayları -
    # find_group_conflicts ile AYNI kontrol, tek doğru kaynak orası.
    domains: list[list[tuple[int, int]]] = [
        [(d, p) for (d, p) in all_slots if not find_group_conflicts(schedule, d, p, unit, unavailable)]
        for unit in units
    ]
    domain_sets: list[set[tuple[int, int]]] = [set(d) for d in domains]

    model = cp_model.CpModel()

    # x[(birim_no, gün, saat)] = 1  <=>  o birim o gün/saate yerleşti
    x: dict[tuple[int, int, int], "cp_model.IntVar"] = {}
    for ui, slots in enumerate(domains):
        for (d, p) in slots:
            x[(ui, d, p)] = model.NewBoolVar(f"x_{ui}_{d}_{p}")

    # Her birim en fazla bir kez yerleşsin (hiç yerleşmeyebilir de - o
    # zaman havuzda kalır, tıpkı eski yöntemde olduğu gibi).
    for ui, slots in enumerate(domains):
        unit_vars = [x[(ui, d, p)] for (d, p) in slots]
        if unit_vars:
            model.Add(sum(unit_vars) <= 1)

    def add_resource_constraint(key_fn) -> None:
        """Aynı kaynağı (öğretmen/sınıf/öğrenci/derslik) paylaşan
        birimlerin aynı (gün, saat)'e birden fazlası yerleşemez."""
        buckets: dict[tuple, dict[tuple[int, int], list[int]]] = {}
        for ui, unit in enumerate(units):
            for key in key_fn(unit):
                for (d, p) in domains[ui]:
                    buckets.setdefault(key, {}).setdefault((d, p), []).append(ui)
        for per_slot in buckets.values():
            for (d, p), uis in per_slot.items():
                if len(uis) > 1:
                    model.Add(sum(x[(ui, d, p)] for ui in uis) <= 1)

    add_resource_constraint(lambda unit: {b.teacher_id for b in unit if b.teacher_id is not None})
    add_resource_constraint(lambda unit: {b.class_group_id for b in unit if b.class_group_id is not None})
    add_resource_constraint(lambda unit: {b.student_id for b in unit if b.student_id is not None})
    add_resource_constraint(lambda unit: {b.room_id for b in unit if b.room_id is not None})

    # Bir öğrencinin birebir/koçluk dersi kendi sınıfının o saatteki sınıf
    # dersiyle çakışmasın (find_conflicts'taki çapraz kural) - ama iki
    # farklı öğrencinin birebir dersleri birbirini ETKİLEMEZ, bu yüzden
    # genel bir "kaynak" kovasına değil, sadece sınıf<->o sınıfın
    # öğrencisi çiftlerine uygulanır.
    class_slot_units: dict[int, dict[tuple[int, int], list[int]]] = {}
    personal_slot_units: dict[int, dict[tuple[int, int], list[int]]] = {}
    for ui, unit in enumerate(units):
        for b in unit:
            if b.type == TYPE_CLASS and b.class_group_id is not None:
                for (d, p) in domains[ui]:
                    class_slot_units.setdefault(b.class_group_id, {}).setdefault((d, p), []).append(ui)
            if b.student_id is not None and b.student_class_group_id is not None:
                for (d, p) in domains[ui]:
                    personal_slot_units.setdefault(b.student_class_group_id, {}).setdefault((d, p), []).append(ui)
    for class_id, class_by_slot in class_slot_units.items():
        personal_by_slot = personal_slot_units.get(class_id)
        if not personal_by_slot:
            continue
        for slot, class_uis in class_by_slot.items():
            personal_uis = personal_by_slot.get(slot)
            if not personal_uis:
                continue
            for cu in class_uis:
                for pu in personal_uis:
                    model.Add(x[(cu, *slot)] + x[(pu, *slot)] <= 1)

    # Aynı ihtiyaçtan gelen (aynı tip+öğretmen+sınıf+öğrenci+ders) dersler
    # tek bir grup sayılır - hem "art arda en fazla N saat" sert kısıtı hem
    # de aşağıdaki gün-yayma tercihi bu gruplamaya göre çalışır.
    group_units: dict[tuple, list[int]] = {}
    group_representative: dict[tuple, BlockView] = {}
    for ui, unit in enumerate(units):
        if len(unit) == 1 and unit[0].type != TYPE_DEPARTMENT:
            key = unit[0].group_key()
            group_units.setdefault(key, []).append(ui)
            group_representative.setdefault(key, unit[0])

    # Zaten yerleşmiş (elle ya da önceki bir oto-atamadan kalma) bloklardan
    # aynı gruptan olanların gün/saatleri - aşağıdaki "art arda en fazla N
    # saat" kısıtı bunları da SAYMAZSA, örn. manuel yerleştirilmiş 1 saatin
    # yanına oto-ata 2 saat daha eklerse (kısıt sadece YENİ kararları
    # sayıp zaten sabit olanı görmezden geldiği için) 3 saat üst üste
    # oluşabilir - kısıt bu yüzden sabit blokları da pencereye dahil eder.
    fixed_periods_by_group: dict[tuple, dict[int, set[int]]] = {}
    for blocks in schedule.values():
        for b in blocks:
            if b.type == TYPE_DEPARTMENT or b.day is None or b.period is None:
                continue
            fixed_periods_by_group.setdefault(b.group_key(), {}).setdefault(b.day, set()).add(b.period)

    # ---------- sert kısıt: bir günde en fazla `max_consecutive` saat, VE bitişik ----------
    # Aynı ihtiyaçtan (ör. "9-A Matematik, Hasan Bingöl") gelen dersler bir
    # günde en fazla `max_consecutive` (varsayılan 2) saat olabilir VE bu
    # saatler MUTLAKA bitişik olmalı - aynı öğretmen aynı sınıfa aynı gün
    # içinde iki AYRI girişte bulunamaz (ör. 1-2. saat + tekrar 5. saat
    # gibi bölünmüş bir yerleşim artık kesinlikle oluşmaz).
    #
    # Not: eski sürüm sadece `max_consecutive + 1` uzunluğundaki kayan
    # pencerelerde "üst üste en fazla N" diye bakıyordu - bu, GÜN İÇİNDE
    # TOPLAM sayıyı sınırlamıyordu (ör. 1-2. saat + 5. saat, hiçbir 3'lü
    # pencerenin içine birlikte düşmediği için sorunsuz sayılıyordu).
    # Şimdi hem günlük toplam hem de bitişiklik ayrı ayrı ve kesin olarak
    # zorunlu kılınıyor.
    if max_consecutive > 0:
        for group_key, uis in group_units.items():
            fixed_days = fixed_periods_by_group.get(group_key, {})
            if len(uis) <= 1 and not fixed_days:
                continue
            for d in range(day_count):
                fixed_set = fixed_days.get(d, set())
                var_by_period: dict[int, list] = {}
                for ui in uis:
                    for (dd, p) in domains[ui]:
                        if dd == d:
                            var_by_period.setdefault(p, []).append(x[(ui, dd, p)])
                candidate_periods = set(fixed_set) | set(var_by_period.keys())
                if not candidate_periods:
                    continue

                # (1) o gün bu gruptan toplam en fazla max_consecutive saat.
                day_terms = [v for p in candidate_periods for v in var_by_period.get(p, [])]
                if day_terms:
                    model.Add(sum(day_terms) <= max(0, max_consecutive - len(fixed_set)))

                # (2) kullanılan saatler bitişik olmalı: aralarında boşluk
                # olan (ardışık olmayan) herhangi iki saat birlikte
                # DOLU olamaz.
                sorted_periods = sorted(candidate_periods)
                for i in range(len(sorted_periods)):
                    for j in range(i + 1, len(sorted_periods)):
                        p, q = sorted_periods[i], sorted_periods[j]
                        if q - p < 2:
                            continue
                        terms = list(var_by_period.get(p, [])) + list(var_by_period.get(q, []))
                        fixed_count = (1 if p in fixed_set else 0) + (1 if q in fixed_set else 0)
                        if not terms:
                            continue
                        model.Add(sum(terms) <= max(0, 1 - fixed_count))

    # ---------- hafif tercih: aynı ihtiyaçtan gelen dersleri günlere yay ----------
    # Zorunlu değil (yerleştirme sayısını asla düşürmez, sadece eşit
    # kalitede birden fazla çözüm varsa aralarında seçim yapar).
    spread_bonus_terms = []
    for gi, uis in enumerate(group_units.values()):
        if len(uis) < 2:
            continue
        for d in range(day_count):
            day_vars = [x[(ui, d, p)] for ui in uis for (dd, p) in domains[ui] if dd == d]
            if not day_vars:
                continue
            used = model.NewBoolVar(f"day_used_{gi}_{d}")
            model.AddMaxEquality(used, day_vars)
            spread_bonus_terms.append(used)

    # ---------- hafif tercih: aynı ihtiyaçtan gelen saatleri BLOK halinde tut ----------
    # Örn. "9-A Tarih (Zülal), haftada 4 saat" dersi mümkünse aynı gün
    # içinde başka bir dersle bölünmeden art arda (2+2 gibi) yerleşsin -
    # öğretmen bir saat gelip başka derse yer açıp sonra tekrar gelmiş
    # gibi olmasın. Zorunlu değil (yerleştirme sayısını asla düşürmez).
    adjacency_bonus_terms = []
    for gi, uis in enumerate(group_units.values()):
        if len(uis) < 2:
            continue
        for d in range(day_count):
            for p in range(1, period_count):
                occ_p = [x[(ui, d, p)] for ui in uis if (d, p) in domain_sets[ui]]
                occ_p1 = [x[(ui, d, p + 1)] for ui in uis if (d, p + 1) in domain_sets[ui]]
                if not occ_p or not occ_p1:
                    continue
                bonus = model.NewBoolVar(f"adjacent_{gi}_{d}_{p}")
                model.Add(bonus <= sum(occ_p))
                model.Add(bonus <= sum(occ_p1))
                adjacency_bonus_terms.append(bonus)

    # ---------- hafif tercih: aynı sınıfın art arda saatlerinde ders çeşitliliği ----------
    # Aynı dersi (ör. Matematik) FARKLI öğretmenlerden art arda görmek
    # (öğretmen değişse bile) tekdüze/garip görünüyor - mümkünse aynı gün
    # art arda saatlerde farklı dersler olsun (zorunlu değil, sadece bir
    # tercih; aynı öğretmenin kendi bloğu içindeki bitişiklik yukarıdaki
    # blok tercihiyle zaten ayrıca ödüllendiriliyor, burada CEZALANDIRILMAZ
    # çünkü sadece FARKLI grupların bitişikliğine bakılıyor).
    subject_class_groups: dict[tuple[int, int], list[tuple]] = {}
    for group_key, uis in group_units.items():
        g_type, _teacher_id, g_class_id, _student_id, g_subject_id = group_key
        if g_type != TYPE_CLASS or g_class_id is None or g_subject_id is None:
            continue
        subject_class_groups.setdefault((g_class_id, g_subject_id), []).append(group_key)

    diversity_penalty_terms = []
    for groups in subject_class_groups.values():
        if len(groups) < 2:
            continue
        for gi in range(len(groups)):
            for gj in range(gi + 1, len(groups)):
                uis_a = group_units[groups[gi]]
                uis_b = group_units[groups[gj]]
                for d in range(day_count):
                    for p in range(1, period_count):
                        occ_a_p = [x[(ui, d, p)] for ui in uis_a if (d, p) in domain_sets[ui]]
                        occ_b_p1 = [x[(ui, d, p + 1)] for ui in uis_b if (d, p + 1) in domain_sets[ui]]
                        if occ_a_p and occ_b_p1:
                            penalty = model.NewBoolVar(f"same_subject_adj_{d}_{p}_{gi}_{gj}_a")
                            model.Add(penalty <= sum(occ_a_p))
                            model.Add(penalty <= sum(occ_b_p1))
                            diversity_penalty_terms.append(penalty)
                        occ_b_p = [x[(ui, d, p)] for ui in uis_b if (d, p) in domain_sets[ui]]
                        occ_a_p1 = [x[(ui, d, p + 1)] for ui in uis_a if (d, p + 1) in domain_sets[ui]]
                        if occ_b_p and occ_a_p1:
                            penalty = model.NewBoolVar(f"same_subject_adj_{d}_{p}_{gi}_{gj}_b")
                            model.Add(penalty <= sum(occ_b_p))
                            model.Add(penalty <= sum(occ_a_p1))
                            diversity_penalty_terms.append(penalty)

    placed_terms = list(x.values())
    # Blok bütünlüğü (adjacency), ders çeşitliliğinden (diversity), o da
    # gün yaymadan (spread) daha öncelikli tercih - ama YERLEŞTİRME SAYISI
    # bunların hepsinden önce gelir; bu artık tek bir ağırlıklı toplamla
    # "umulur" değil, aşağıdaki 1. aşamada SERT bir alt sınır olarak
    # garanti edilir (bkz. fonksiyon docstring'i).
    ADJACENCY_WEIGHT = 4
    DIVERSITY_WEIGHT = 2
    SPREAD_WEIGHT = 1

    class _ProgressReporter(cp_model.CpSolverSolutionCallback):
        """CP-SAT her iyileştirilmiş çözüm bulduğunda (aramanın süresi
        boyunca birkaç kez) tetiklenir - o ana kadar kaç dersin
        yerleştiği bilgisini ilerleme çubuğuna yansıtmak için."""

        def __init__(self, placed_vars, total_units, time_limit, pct_start, pct_span, label):
            super().__init__()
            self._placed_vars = placed_vars
            self._total_units = total_units
            self._time_limit = time_limit
            self._pct_start = pct_start
            self._pct_span = pct_span
            self._label = label

        def on_solution_callback(self) -> None:
            placed_now = sum(1 for v in self._placed_vars if self.Value(v))
            pct = self._pct_start + int(self._pct_span * min(1.0, self.WallTime() / max(self._time_limit, 0.1)))
            report(pct, f"{self._label} (şu an {placed_now}/{self._total_units} ders yerleşti)")

    # ---------- 1. aşama: SADECE yerleştirme sayısını maksimize et ----------
    # Daha basit bir hedef olduğu için genelde optimal'i (kanıtlanmış en
    # iyi sonucu) yumuşak tercihli birleşik hedeften çok daha hızlı bulur -
    # bu da "gerçekten imkansız mı yoksa arama daha süremi buldu mu"
    # ayrımını güvenilir kılar (bkz. docstring).
    report(15, f"En fazla kaç ders yerleşebileceği hesaplanıyor ({len(units)} ders saati için)...")
    model.Maximize(sum(placed_terms))
    solver1 = cp_model.CpSolver()
    solver1.parameters.max_time_in_seconds = time_limit_seconds
    solver1.parameters.num_search_workers = 8
    reporter1 = _ProgressReporter(
        placed_terms, len(units), time_limit_seconds, 15, 40, "En fazla kaç ders yerleşebileceği hesaplanıyor..."
    )
    status1 = solver1.Solve(model, reporter1)

    if status1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        report(100, "Uygun bir yerleşim bulunamadı.")
        return AutoAssignResult(placed=0, warnings=warnings)

    max_placed = sum(1 for v in placed_terms if solver1.Value(v))
    proven_optimal = status1 == cp_model.OPTIMAL

    if max_placed < len(units):
        if proven_optimal:
            warnings.extend(
                _shortfall_warnings(units, domains, group_units, group_representative, x, solver1)
            )
        else:
            warnings.append(
                f"{len(units) - max_placed} ders saati için (bu çalıştırmada) uygun bir yer bulunamadı - "
                "arama süresi yetmemiş olabilir, 'Oto Ata'yı tekrar çalıştırmayı deneyebilirsiniz."
            )

    # ---------- 2. aşama: yerleştirme sayısını SABİT tutup (asla düşürmeden)
    # kalan bütçede blok bütünlüğü/çeşitlilik/gün yayma tercihlerini iyileştir ----------
    model.Add(sum(placed_terms) >= max_placed)
    model.Maximize(
        cp_model.LinearExpr.WeightedSum(
            adjacency_bonus_terms + spread_bonus_terms + diversity_penalty_terms,
            [ADJACENCY_WEIGHT] * len(adjacency_bonus_terms)
            + [SPREAD_WEIGHT] * len(spread_bonus_terms)
            + [-DIVERSITY_WEIGHT] * len(diversity_penalty_terms),
        )
    )
    # 1. aşamanın bulduğu çözümü "ipucu" olarak veriyoruz - böylece 2.
    # aşama sıfırdan aramaya başlamıyor, en kötü ihtimalle 1. aşamanın
    # yerleştirme sayısını hemen garantiliyor (kalite tercihleri için
    # zaman yetmese bile yerleştirme sayısı asla geriye düşmüyor).
    for var in x.values():
        model.AddHint(var, solver1.Value(var))

    report(55, "Program inceltiliyor (blok bütünlüğü/çeşitlilik/gün yayma)...")
    solver2 = cp_model.CpSolver()
    solver2.parameters.max_time_in_seconds = quality_time_limit_seconds
    solver2.parameters.num_search_workers = 8
    reporter2 = _ProgressReporter(
        placed_terms, len(units), quality_time_limit_seconds, 55, 40,
        "Program inceltiliyor (blok bütünlüğü/çeşitlilik/gün yayma)...",
    )
    status2 = solver2.Solve(model, reporter2)

    # solver2, kendi süre bütçesi içinde HİÇBİR çözüm bulamamışsa (status
    # OPTIMAL/FEASIBLE değilse) .Value() çağrısı istisna FIRLATMAZ, rastgele
    # (uninitialized) değerler döner - bu sessizce yanlış bir program
    # yazmaya yol açardı. Böyle bir durumda 1. aşamanın zaten doğrulanmış
    # (tüm sert kısıtları sağlayan) çözümüne geri dönülür - kalite tercihleri
    # için zaman yetmese bile ASLA çakışmalı/geçersiz bir sonuç yazılmaz.
    final_solver = solver2 if status2 in (cp_model.OPTIMAL, cp_model.FEASIBLE) else solver1

    report(96, "Sonuçlar kaydediliyor...")

    placed = 0
    placed_block_ids: list[int] = []
    for ui, unit in enumerate(units):
        chosen = None
        for (d, p) in domains[ui]:
            if final_solver.Value(x[(ui, d, p)]):
                chosen = (d, p)
                break
        if chosen is None:
            continue
        d, p = chosen
        for block in unit:
            place_block(db, week_start, block.id, d, p, SCOPE_ALWAYS)
            schedule.setdefault((d, p), []).append(block)
            block.day, block.period = d, p
            cross_week_warning(block, d, p)
            placed += 1
            placed_block_ids.append(block.id)

    report(100, f"Tamamlandı: {placed} ders yerleştirildi.")
    return AutoAssignResult(placed=placed, warnings=warnings, placed_block_ids=placed_block_ids)


def _lesson_label(rep: BlockView) -> str:
    name_bits = [n for n in (rep.teacher_name, rep.class_name, rep.subject_name) if n]
    return " · ".join(name_bits) or rep.pool_label()


def _shortfall_warnings(
    units: list[list[BlockView]],
    domains: list[list[tuple[int, int]]],
    group_units: dict[tuple, list[int]],
    group_representative: dict[tuple, BlockView],
    x: dict,
    solver,
) -> list[str]:
    """1. aşama OPTIMAL'i kanıtladığı halde bazı dersler yerleşemediyse,
    bu GERÇEKTEN matematiksel bir imkansızlıktır - hangi ihtiyacın (ör.
    '9-A Matematik, Ahmet Yılmaz') kaç saat eksik kaldığını insan-okunur
    bir uyarıya çevirir."""
    warnings: list[str] = []
    for group_key, uis in group_units.items():
        total = len(uis)
        placed_count = sum(
            1 for ui in uis if any(solver.Value(x[(ui, d, p)]) for (d, p) in domains[ui])
        )
        if placed_count >= total:
            continue
        rep = group_representative[group_key]
        label = _lesson_label(rep)
        missing = total - placed_count
        warnings.append(
            f"{label}: {total} saat isteniyor, çakışmasız/müsait şekilde en fazla {placed_count} saat "
            f"yerleştirilebiliyor ({missing} saat matematiksel olarak sığmıyor - öğretmenin/sınıfın "
            "müsaitlik ya da çakışma durumunu gözden geçirin)."
        )

    # Zümre grupları (birden fazla bloklu birimler) group_units'e dahil
    # değil - onlar için de aynı kontrolü ayrıca yap.
    grouped_uis = {ui for uis in group_units.values() for ui in uis}
    for ui, unit in enumerate(units):
        if ui in grouped_uis or len(unit) <= 1:
            continue
        placed = any(solver.Value(x[(ui, d, p)]) for (d, p) in domains[ui])
        if placed:
            continue
        rep = unit[0]
        names = ", ".join(sorted(m.teacher_name or "" for m in unit))
        warnings.append(
            f"Zümre toplantısı ({rep.subject_name or '-'}, {names}): tüm öğretmenlerin birlikte "
            "müsait olduğu çakışmasız bir saat bulunamadı - müsaitlik durumlarını gözden geçirin."
        )
    return warnings


def explain_unplaced_lessons(
    db: Database, week_start: _dt.date, max_consecutive: int = 2,
) -> list[dict]:
    """Havuzdaki (atanmamış) HER ihtiyaç için, haftanın her gününün neden
    uygun/uygun olmadığını tek tek açıklayan bir döküm döner. Oto Ata'nın
    tek satırlık "X saat sığmıyor" uyarısının aksine, kullanıcının TAM
    OLARAK hangi günü neyin (çakışma, müsaitlik, ya da günlük sınır/
    bitişiklik kuralı) engellediğini görüp veriyi buna göre düzeltebilmesi
    içindir - özellikle manuel olarak bazı günlere kuralı çiğneyip 3 saat
    yerleştirilmiş durumlarda, o günün ARTIK o ihtiyaç için neden kapalı
    olduğunu açıkça gösterir.

    CP-SAT çözücüsünü ÇALIŞTIRMAZ (statik/anlık bir analizdir, anında
    sonuç verir); bu yüzden "hiç uygun saat yok" (gerçek imkansızlık) ile
    "uygun saat var ama başka derslerle rekabet ediyor olabilir" (Oto
    Ata'yı tekrar çalıştırmak faydalı olabilir) durumlarını ayırt eder,
    ama tam nedensellik iddia etmez (birden fazla eşit-iyi çözüm olabilir)."""
    day_count = len(db.day_names)
    period_count = db.period_count
    schedule, pool = get_week_view(db, week_start)
    unavailable = UnavailableSlots.compute(db, week_start)

    seen_zumre: set[int] = set()
    zumre_units: list[list[BlockView]] = []
    grouped: dict[tuple, list[BlockView]] = {}
    for block in pool:
        if block.type == TYPE_DEPARTMENT and block.zumre_group_id is not None:
            if block.zumre_group_id in seen_zumre:
                continue
            seen_zumre.add(block.zumre_group_id)
            zumre_units.append([b for b in pool if b.zumre_group_id == block.zumre_group_id])
        else:
            grouped.setdefault(block.group_key(), []).append(block)

    fixed_periods_by_group: dict[tuple, dict[int, set[int]]] = {}
    for blocks in schedule.values():
        for b in blocks:
            if b.type == TYPE_DEPARTMENT or b.day is None or b.period is None:
                continue
            fixed_periods_by_group.setdefault(b.group_key(), {}).setdefault(b.day, set()).add(b.period)

    def analyze(unit: list[BlockView], group_key) -> dict:
        rep = min(unit, key=lambda b: b.id)
        fixed_days = fixed_periods_by_group.get(group_key, {}) if group_key else {}
        slot_notes: list[dict] = []
        open_slots: list[tuple[int, int]] = []
        for d in range(day_count):
            existing = fixed_days.get(d, set())
            for p in range(1, period_count + 1):
                conflicts = find_group_conflicts(schedule, d, p, unit, unavailable)
                if conflicts:
                    slot_notes.append({"day": d, "period": p, "open": False, "reason": conflicts[0]})
                    continue
                if group_key and max_consecutive > 0 and p not in existing:
                    if len(existing) >= max_consecutive:
                        hours = ", ".join(str(h) for h in sorted(existing))
                        slot_notes.append({
                            "day": d, "period": p, "open": False,
                            "reason": f"o gün için günlük sınır ({max_consecutive} saat) zaten dolu ({hours}. saat kullanılıyor)",
                        })
                        continue
                    if existing:
                        candidate = existing | {p}
                        if max(candidate) - min(candidate) + 1 != len(candidate):
                            hours = ", ".join(str(h) for h in sorted(existing))
                            slot_notes.append({
                                "day": d, "period": p, "open": False,
                                "reason": f"o gün kullanılan {hours}. saat(ler)e bitişik değil",
                            })
                            continue
                slot_notes.append({"day": d, "period": p, "open": True, "reason": ""})
                open_slots.append((d, p))

        day_summary: list[dict] = []
        for d in range(day_count):
            day_notes = [n for n in slot_notes if n["day"] == d]
            opens = [n["period"] for n in day_notes if n["open"]]
            if opens:
                day_summary.append({
                    "open": True,
                    "text": f"{len(opens)} saat açık ({', '.join(str(p) for p in opens)}. saat)",
                })
            else:
                reasons = [n["reason"] for n in day_notes if n["reason"]]
                reason = max(set(reasons), key=reasons.count) if reasons else "uygun saat yok"
                day_summary.append({"open": False, "text": f"kapalı - {reason}"})

        return {
            "label": _lesson_label(rep),
            "hours_needed": 1,
            "open_slots": open_slots,
            "day_summary": day_summary,
        }

    reports: list[dict] = []
    for group_key, blocks in grouped.items():
        entry = analyze([blocks[0]], group_key)
        entry["hours_needed"] = len(blocks)
        reports.append(entry)
    for unit in zumre_units:
        reports.append(analyze(unit, None))

    reports.sort(key=lambda e: (len(e["open_slots"]) > 0, e["label"]))
    return reports


# ---------- özet / analiz ----------

def summarize_hours(db: Database, week_start: _dt.date, *, teacher_id: int | None = None,
                     student_id: int | None = None, class_group_id: int | None = None) -> dict[str, int]:
    """Belirtilen kişi/sınıf için, o haftaki ders tipine göre saat sayısı özeti."""
    schedule, _pool = get_week_view(db, week_start)
    totals: dict[str, int] = {t: 0 for t in LESSON_TYPE_LABELS}
    for blocks in schedule.values():
        for block in blocks:
            if teacher_id is not None and block.teacher_id != teacher_id:
                continue
            if student_id is not None and block.student_id != student_id:
                continue
            if class_group_id is not None and block.class_group_id != class_group_id:
                continue
            totals[block.type] = totals.get(block.type, 0) + 1
    return totals


def student_effective_blocks(
    db: Database, week_start: _dt.date, student_id: int, class_group_id: int | None
) -> dict[tuple[int, int], list[BlockView]]:
    """Bir öğrencinin haftalık programı: kendi kişisel (birebir/koçluk)
    blokları + (bir sınıfa atalıysa) o sınıfın tüm sınıf dersleri
    birleşik olarak - öğrenci kendi sınıfının derslerine de katılır."""
    schedule, _pool = get_week_view(db, week_start)
    filtered: dict[tuple[int, int], list[BlockView]] = {}
    for cell, blocks in schedule.items():
        matched = [
            b for b in blocks
            if b.student_id == student_id
            or (class_group_id is not None and b.type == TYPE_CLASS and b.class_group_id == class_group_id)
        ]
        if matched:
            filtered[cell] = matched
    return filtered


def summarize_student_hours(
    db: Database, week_start: _dt.date, student_id: int, class_group_id: int | None
) -> dict[str, int]:
    """summarize_hours(student_id=...) ile aynı ama öğrencinin sınıfının
    dersleri de dahil edilir (bkz. student_effective_blocks)."""
    filtered = student_effective_blocks(db, week_start, student_id, class_group_id)
    totals: dict[str, int] = {t: 0 for t in LESSON_TYPE_LABELS}
    for blocks in filtered.values():
        for block in blocks:
            totals[block.type] = totals.get(block.type, 0) + 1
    return totals


def compute_one_on_one_ledger(db: Database, student_id: int, as_of: _dt.date | None = None) -> dict[str, float]:
    """Bir öğrencinin birebir PAKET durumunu anlık tarihe göre hesaplar
    (bkz. db.students.one_on_one_package_hours, lesson_blocks.created_at).

    Öğrencinin programda AN İTİBARIYLE yeri olan (template_day dolu) her
    birebir ders bloğu için, o blok ilk eklendiği tarihten (created_at)
    bugüne kadar geçen her hafta gerçekten oluşmuş mu (o hafta için bir
    istisna bloğu havuza düşürmüş/gizlemiş mi) bakılıp kaç "saat" fiilen
    yapılmış sayılacağı bulunur. Bu toplam (yapılan) paket saatinden
    düşülür: karşılığı olan kısım "ödenmiş", aşan kısım "borçlu" olur.

    NOT: Havuzdan branş ayrımı yapılmaz (kullanıcı tercihi: öğrenci
    başına TEK toplam havuz) ve bu ALTER TABLE ile sonradan eklenen
    created_at nedeniyle güncellemeden ÖNCE var olan bloklarda geçmişe
    dönük sayım yapılamaz (o bloklar için sayaç güncellemenin kurulduğu
    günden itibaren işler)."""
    today = as_of or _dt.date.today()
    rows = db.list_lesson_blocks_detailed(
        where="WHERE lb.type=? AND lb.student_id=?", params=(TYPE_ONE_ON_ONE, student_id)
    )
    active = [r for r in rows if r["template_day"] is not None and r["template_period"] is not None]

    occurred = 0
    if active:
        start_dates = [_dt.date.fromisoformat(r["created_at"]) for r in active if r["created_at"]]
        if start_dates:
            week = monday_of(min(start_dates))
            last_week = monday_of(today)
            while week <= last_week:
                exceptions = db.get_week_exceptions(week_key(week))
                for r in active:
                    created = _dt.date.fromisoformat(r["created_at"]) if r["created_at"] else today
                    if created > week + _dt.timedelta(days=6):
                        continue  # bu blok o hafta henüz eklenmemişti
                    if r["id"] in exceptions:
                        day, period = exceptions[r["id"]]
                    else:
                        day, period = r["template_day"], r["template_period"]
                    if day is None or period is None:
                        continue  # o hafta istisnayla havuza düşmüş/gizlenmiş
                    occurrence_date = week + _dt.timedelta(days=day)
                    if created <= occurrence_date <= today:
                        occurred += 1
                week += _dt.timedelta(days=7)

    student = db.get_student(student_id)
    package = float(student["one_on_one_package_hours"]) if student is not None else 0.0
    paid = min(occurred, package)
    return {
        "package_hours": package,
        "occurred_hours": float(occurred),
        "paid_hours": paid,
        "remaining_hours": max(package - occurred, 0.0),
        "debt_hours": max(occurred - package, 0.0),
    }


def summarize_hours_range(
    db: Database,
    start_date: _dt.date,
    end_date: _dt.date,
    *,
    teacher_id: int | None = None,
    student_id: int | None = None,
) -> dict[str, int]:
    """start_date - end_date arasındaki HER HAFTA için o haftanın efektif
    programını hesaplayıp toplar (şablon + istisnalar dahil)."""
    totals: dict[str, int] = {t: 0 for t in LESSON_TYPE_LABELS}
    week = monday_of(start_date)
    last_week = monday_of(end_date)
    while week <= last_week:
        week_totals = summarize_hours(db, week, teacher_id=teacher_id, student_id=student_id)
        for k, v in week_totals.items():
            totals[k] += v
        week += _dt.timedelta(days=7)
    return totals
