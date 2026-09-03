"""Örnek/demo veri oluşturma. Kullanıcı tek tek veri girmeden programı
gezebilsin diye: ilk açılışta veritabanı tamamen boşsa otomatik, ya da
Ayarlar sekmesindeki düğmeyle istendiğinde çalışır."""
from __future__ import annotations

import datetime as _dt

from .db import (
    Database,
    TYPE_CLASS,
    TYPE_ONE_ON_ONE,
    TYPE_DEPARTMENT,
    TYPE_PROBLEM_SOLVING,
)
from . import scheduling


def is_empty(db: Database) -> bool:
    """Veritabanında hiç öğretmen/sınıf/ders tanımı yoksa 'boş' kabul edilir."""
    return (
        not db.list_teachers()
        and not db.list_rows("class_groups")
        and not db.list_rows("subjects")
    )


def seed_demo_data(db: Database) -> None:
    week = scheduling.monday_of(_dt.date.today())

    t_ahmet = db.add_teacher("Ahmet Yılmaz", "Matematik")
    t_ayse = db.add_teacher("Ayşe Demir", "Fizik")
    t_mehmet = db.add_teacher("Mehmet Kaya", "Matematik")
    t_elif = db.add_teacher("Elif Ak", "Türkçe")
    t_canan = db.add_teacher("Canan Öz", "Kimya")
    db.add_teacher("Burak Şen", "Tarih")

    s_mat = db.add_row("subjects", "Matematik")
    s_fizik = db.add_row("subjects", "Fizik")
    s_kimya = db.add_row("subjects", "Kimya")
    s_turkce = db.add_row("subjects", "Türkçe")
    db.add_row("subjects", "Tarih")
    db.add_row("subjects", "Biyoloji")

    c_9a = db.add_class_group("9-A")
    c_9b = db.add_class_group("9-B")
    c_10a = db.add_class_group("10-A")
    c_10b = db.add_class_group("10-B")

    r1 = db.add_row("rooms", "Derslik 101")
    r2 = db.add_row("rooms", "Derslik 102")
    r3 = db.add_row("rooms", "Laboratuvar")

    st_zeynep = db.add_student("Zeynep Yıldız", c_9a, t_ahmet, total_program_fee=8000, total_one_on_one_fee=3000)
    db.add_student("Can Demir", c_9a, t_elif, total_program_fee=8000, total_one_on_one_fee=0)
    db.add_student("Elif Su", c_9b, None, total_program_fee=7500, total_one_on_one_fee=0)
    st_berk = db.add_student("Berk Aydın", c_10a, t_mehmet, total_program_fee=8500, total_one_on_one_fee=2000)
    db.add_student("Naz Çelik", c_10b, None, total_program_fee=7500, total_one_on_one_fee=0)

    db.add_payment(st_zeynep, 4000, week.isoformat(), "1. taksit")

    def place_class(teacher, subject, class_group, room, day, period):
        ids = db.add_lesson_blocks(TYPE_CLASS, 1, teacher_id=teacher, subject_id=subject, class_group_id=class_group, room_id=room)
        scheduling.place_block(db, week, ids[0], day=day, period=period, scope=scheduling.SCOPE_ALWAYS)

    place_class(t_ahmet, s_mat, c_9a, r1, 0, 1)
    place_class(t_elif, s_turkce, c_9a, r1, 0, 2)
    place_class(t_ayse, s_fizik, c_9a, r2, 2, 3)
    place_class(t_mehmet, s_mat, c_9b, r2, 0, 1)
    place_class(t_canan, s_kimya, c_9b, r3, 1, 1)
    place_class(t_elif, s_turkce, c_9b, r1, 2, 4)
    place_class(t_ayse, s_fizik, c_10a, r2, 0, 3)
    place_class(t_ahmet, s_mat, c_10a, r1, 1, 5)
    place_class(t_canan, s_kimya, c_10b, r3, 0, 2)
    place_class(t_elif, s_turkce, c_10b, r1, 3, 1)

    def place(type_, teacher, subject, day, period, room=None, student=None):
        ids = db.add_lesson_blocks(type_, 1, teacher_id=teacher, subject_id=subject, room_id=room, student_id=student)
        scheduling.place_block(db, week, ids[0], day=day, period=period, scope=scheduling.SCOPE_ALWAYS)

    place(TYPE_ONE_ON_ONE, t_ayse, s_fizik, 1, 2, room=r2, student=st_zeynep)
    place(TYPE_ONE_ON_ONE, t_mehmet, s_mat, 2, 1, room=r1, student=st_berk)
    place(TYPE_PROBLEM_SOLVING, t_ayse, s_fizik, 4, 2)

    # Zümre: aynı buluşmadaki tüm öğretmenler ortak bir zumre_group_id ile
    # bağlanır ki Ana Program'da tek bir ders olarak görünsün ve birine
    # sürüklenince hepsi aynı gün/saate yerleşsin (bkz. db.add_zumre_group).
    zumre1_ids = db.add_zumre_group([t_ahmet, t_mehmet], subject_id=s_mat)
    scheduling.place_block(db, week, zumre1_ids[0], day=4, period=1, scope=scheduling.SCOPE_ALWAYS)
    for other_id in zumre1_ids[1:]:
        scheduling.place_block(db, week, other_id, day=4, period=1, scope=scheduling.SCOPE_ALWAYS)
    # ikinci bir zümre bilinçli olarak atanmamış bırakılıyor - "birine
    # sürükleyince hepsi dolsun" akışını denemek için.
    db.add_zumre_group([t_ayse, t_canan, t_elif], subject_id=None)

    # Zeynep'in otomatik oluşan koçluk bloğunu yerleştir; diğer koçluk
    # blokları (Can/Berk) ve aşağıdaki dersler bilinçli olarak atanmamış
    # havuzunda bırakılıyor - sürükle-bırak akışını denemek için.
    kocluk_blocks = db.list_lesson_blocks_detailed("WHERE lb.student_id=?", (st_zeynep,))
    for row in kocluk_blocks:
        if row["type"] == "kocluk":
            scheduling.place_block(db, week, row["id"], day=3, period=2, scope=scheduling.SCOPE_ALWAYS)

    db.add_lesson_blocks(TYPE_CLASS, 1, teacher_id=t_ahmet, subject_id=s_mat, class_group_id=c_10a, room_id=r1)
    db.add_lesson_blocks(TYPE_CLASS, 1, teacher_id=t_ayse, subject_id=s_fizik, class_group_id=c_10b, room_id=r2)
    db.add_lesson_blocks(TYPE_PROBLEM_SOLVING, 1, teacher_id=t_canan, subject_id=s_kimya)
