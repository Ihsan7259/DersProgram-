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
    placed_block_ids: list[int] = field(default_factory=list)


def auto_assign(
    db: Database,
    week_start: _dt.date,
    max_consecutive: int = 2,
    time_limit_seconds: float = 20.0,
    progress_callback=None,
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

    `progress_callback`, verilirse `(yüzde: int, mesaj: str)` ile art arda
    çağrılır (ör. bir ilerleme diyaloğunu güncellemek için) - uzun süren
    aramalarda kullanıcıya "ne yapıldığı" hakkında geri bildirim vermek
    içindir, sonucu etkilemez."""
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
    for ui, unit in enumerate(units):
        if len(unit) == 1 and unit[0].type != TYPE_DEPARTMENT:
            group_units.setdefault(unit[0].group_key(), []).append(ui)

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
    # Yerleştirilen ders sayısı her zaman diğer tüm tercihlerden ağır
    # basar - "daha iyi dağılsın/bloklansın diye bir dersi havuzda bırak"
    # asla olmaz. Blok bütünlüğü (adjacency), ders çeşitliliğinden
    # (diversity), o da gün yaymadan (spread) daha öncelikli tercih.
    ADJACENCY_WEIGHT = 4
    DIVERSITY_WEIGHT = 2
    SPREAD_WEIGHT = 1
    place_weight = (
        ADJACENCY_WEIGHT * len(adjacency_bonus_terms)
        + DIVERSITY_WEIGHT * len(diversity_penalty_terms)
        + SPREAD_WEIGHT * len(spread_bonus_terms)
        + 1
    )
    model.Maximize(
        cp_model.LinearExpr.WeightedSum(
            placed_terms + adjacency_bonus_terms + spread_bonus_terms + diversity_penalty_terms,
            [place_weight] * len(placed_terms)
            + [ADJACENCY_WEIGHT] * len(adjacency_bonus_terms)
            + [SPREAD_WEIGHT] * len(spread_bonus_terms)
            + [-DIVERSITY_WEIGHT] * len(diversity_penalty_terms),
        )
    )

    report(15, f"En uygun program aranıyor ({len(units)} ders saati için)...")

    class _ProgressReporter(cp_model.CpSolverSolutionCallback):
        """CP-SAT her iyileştirilmiş çözüm bulduğunda (aramanın süresi
        boyunca birkaç kez) tetiklenir - o ana kadar kaç dersin
        yerleştiği bilgisini ilerleme çubuğuna yansıtmak için."""

        def __init__(self, placed_vars, total_units, time_limit):
            super().__init__()
            self._placed_vars = placed_vars
            self._total_units = total_units
            self._time_limit = time_limit

        def on_solution_callback(self) -> None:
            placed_now = sum(1 for v in self._placed_vars if self.Value(v))
            pct = 15 + int(80 * min(1.0, self.WallTime() / max(self._time_limit, 0.1)))
            report(pct, f"En uygun program aranıyor... (şu an {placed_now}/{self._total_units} ders yerleşti)")

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 8
    reporter = _ProgressReporter(placed_terms, len(units), time_limit_seconds)
    solver.Solve(model, reporter)

    report(96, "Sonuçlar kaydediliyor...")

    placed = 0
    placed_block_ids: list[int] = []
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
            placed_block_ids.append(block.id)

    report(100, f"Tamamlandı: {placed} ders yerleştirildi.")
    return AutoAssignResult(placed=placed, warnings=warnings, placed_block_ids=placed_block_ids)


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
