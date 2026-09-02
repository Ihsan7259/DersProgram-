"""Program motoru: hafta hesaplama, şablon+istisna birleştirme, yerleştirme,
çakışma kontrolü ve oto-atama.

Bu modül db.py'nin ham CRUD fonksiyonlarını kullanarak "bu hafta ekranda
ne görünmeli" sorusuna cevap verir.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass

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

    def dense_lines(self, row_mode: str) -> tuple[str, str]:
        """Kurum geneli ızgarada (satır=sınıf ya da öğretmen) hücrede
        gösterilecek iki kısa satır. Satırın kendisi zaten hangi sınıf/
        öğretmen olduğunu belli ettiği için o bilgi tekrar edilmez."""
        if row_mode == "class":
            return self.subject_name or "Ders", short_teacher_name(self.teacher_name)
        if self.type == TYPE_CLASS:
            return self.subject_name or "Ders", self.class_name or ""
        if self.type == TYPE_ONE_ON_ONE:
            return self.subject_name or "Birebir", self.student_name or ""
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


def find_conflicts(
    schedule: dict[tuple[int, int], list[BlockView]],
    day: int,
    period: int,
    block: BlockView,
) -> list[str]:
    """Bir bloğu (day, period)'a koymanın doğuracağı çakışmaları
    insan-okunur mesajlar olarak döner. Boş liste = sorun yok."""
    reasons = []
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


def auto_assign(db: Database, week_start: _dt.date, max_consecutive: int = 2) -> int:
    """Atanmamış dersleri, çakışma olmayan ve mümkün olduğunca dengeli
    dağılan (aynı grup art arda en fazla `max_consecutive` saat) uygun
    slotlara otomatik yerleştirir. Kaç ders yerleştirildiğini döner."""
    day_count = len(db.day_names)
    period_count = db.period_count

    schedule, pool = get_week_view(db, week_start)

    groups: dict[tuple, list[BlockView]] = {}
    for block in pool:
        groups.setdefault(block.group_key(), []).append(block)

    # basit günlük yük sayacı: (gün) -> o gün kaç blok var
    day_load = [0] * day_count
    for (d, _p), blocks in schedule.items():
        day_load[d] += len(blocks)

    placed = 0
    for group_key, blocks in groups.items():
        group_days_used: dict[int, int] = {}
        for block in blocks:
            best = None
            day_order = sorted(
                range(day_count),
                key=lambda d: (group_days_used.get(d, 0), day_load[d]),
            )
            for d in day_order:
                for p in range(1, period_count + 1):
                    if find_conflicts(schedule, d, p, block):
                        continue
                    # aynı gruptan art arda kaç saat oluşacağını kontrol et
                    consecutive = 1
                    pp = p - 1
                    while pp >= 1 and any(b.group_key() == group_key for b in schedule.get((d, pp), [])):
                        consecutive += 1
                        pp -= 1
                    pp = p + 1
                    while pp <= period_count and any(b.group_key() == group_key for b in schedule.get((d, pp), [])):
                        consecutive += 1
                        pp += 1
                    if consecutive > max_consecutive:
                        continue
                    best = (d, p)
                    break
                if best:
                    break
            if best is None:
                continue
            d, p = best
            place_block(db, week_start, block.id, d, p, SCOPE_ALWAYS)
            schedule.setdefault((d, p), []).append(block)
            block.day, block.period = d, p
            day_load[d] += 1
            group_days_used[d] = group_days_used.get(d, 0) + 1
            placed += 1

    return placed


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
