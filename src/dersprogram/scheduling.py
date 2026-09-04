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

    def dense_lines(self, row_mode: str) -> tuple[str, str]:
        """Kurum geneli ızgarada (satır=sınıf ya da öğretmen) hücrede
        gösterilecek iki kısa satır. Satırın kendisi zaten hangi sınıf/
        öğretmen olduğunu belli ettiği için o bilgi tekrar edilmez."""
        if row_mode == "class":
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


def get_all_unavailable_slots(db: Database, week_start: _dt.date) -> set[tuple[int, int, int]]:
    """Tüm öğretmenler için o hafta 'müsait değil' işaretli
    (teacher_id, day, period) üçlülerinin kümesi."""
    slots: set[tuple[int, int, int]] = set()
    for teacher in db.list_teachers():
        avail = get_teacher_availability(db, teacher["id"], week_start)
        for (day, period), status in avail.items():
            if status == "unavailable":
                slots.add((teacher["id"], day, period))
    return slots


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
    slots: set[tuple[int, int, int]] = set()
    for student in db.list_students():
        avail = get_student_availability(db, student["id"], week_start)
        for (day, period), status in avail.items():
            if status == "unavailable":
                slots.add((student["id"], day, period))
    return slots


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
    slots: set[tuple[int, int, int]] = set()
    for class_group in db.list_class_groups():
        avail = get_class_availability(db, class_group["id"], week_start)
        for (day, period), status in avail.items():
            if status == "unavailable":
                slots.add((class_group["id"], day, period))
    return slots


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


def auto_assign(
    db: Database, week_start: _dt.date, max_consecutive: int = 2, time_limit_seconds: float = 20.0
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
    döndürülür ki kullanıcı isterse o haftaları elle kontrol etsin."""
    from ortools.sat.python import cp_model

    day_count = len(db.day_names)
    day_names = db.day_names
    period_count = db.period_count
    this_week_key = week_key(week_start)

    schedule, pool = get_week_view(db, week_start)
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
        return AutoAssignResult(placed=0, warnings=warnings)

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
    for ui, unit in enumerate(units):
        if len(unit) == 1 and unit[0].type != TYPE_DEPARTMENT:
            group_units.setdefault(unit[0].group_key(), []).append(ui)

    # ---------- sert kısıt: bir günde art arda en fazla `max_consecutive` saat ----------
    # Her `max_consecutive + 1` uzunluğundaki ardışık saat penceresinde bu
    # gruptan en fazla `max_consecutive` tanesi seçilebilir - bu, 3 (ya da
    # kaç ayarlanmışsa) saatin üst üste gelmesini KESİN olarak engeller,
    # ama HANGİ saatlerin seçileceğini serbest bırakır (çözücü en uygununu
    # bulur, ör. 2+2+1 ya da 2+1+2 gibi farklı dağılımlar da olabilir).
    if max_consecutive > 0:
        window_size = max_consecutive + 1
        for uis in group_units.values():
            if len(uis) <= max_consecutive:
                continue
            for d in range(day_count):
                var_by_period: dict[int, list] = {}
                for ui in uis:
                    for (dd, p) in domains[ui]:
                        if dd == d:
                            var_by_period.setdefault(p, []).append(x[(ui, dd, p)])
                for start in range(1, period_count - window_size + 2):
                    window_vars = [
                        v for p in range(start, start + window_size) for v in var_by_period.get(p, [])
                    ]
                    if window_vars:
                        model.Add(sum(window_vars) <= max_consecutive)

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

    placed_terms = list(x.values())
    # Yerleştirilen ders sayısı her zaman gün-yayma tercihinden ağır
    # basar - "daha iyi dağılsın diye bir dersi havuzda bırak" asla olmaz.
    place_weight = len(spread_bonus_terms) + 1
    model.Maximize(
        cp_model.LinearExpr.WeightedSum(
            placed_terms + spread_bonus_terms,
            [place_weight] * len(placed_terms) + [1] * len(spread_bonus_terms),
        )
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    solver.Solve(model)

    placed = 0
    for ui, unit in enumerate(units):
        chosen = None
        for (d, p) in domains[ui]:
            if solver.Value(x[(ui, d, p)]):
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

    return AutoAssignResult(placed=placed, warnings=warnings)


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
