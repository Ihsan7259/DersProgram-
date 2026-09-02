"""SQLite veritabanı erişim katmanı.

Tüm SQL sorguları burada toplanır; arayüz (UI) katmanı SQL bilmeden bu
fonksiyonları çağırır. Program yerleştirme/çakışma mantığı için bkz.
scheduling.py (bu modül sadece ham veri okuma/yazmadan sorumlu).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

# Ders tipleri
TYPE_CLASS = "sinif"        # normal sınıf dersi
TYPE_ONE_ON_ONE = "birebir"  # birebir ders
TYPE_COACHING = "kocluk"     # öğrenci koçluk
TYPE_DEPARTMENT = "zumre"    # zümre toplantısı
TYPE_PROBLEM_SOLVING = "soru_cozum"  # soru çözümü

LESSON_TYPES = [TYPE_CLASS, TYPE_ONE_ON_ONE, TYPE_COACHING, TYPE_DEPARTMENT, TYPE_PROBLEM_SOLVING]

LESSON_TYPE_LABELS = {
    TYPE_CLASS: "Sınıf Dersi",
    TYPE_ONE_ON_ONE: "Birebir Ders",
    TYPE_COACHING: "Öğrenci Koçluk",
    TYPE_DEPARTMENT: "Zümre",
    TYPE_PROBLEM_SOLVING: "Soru Çözümü",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    subject_area TEXT DEFAULT '',
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS class_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    class_group_id INTEGER REFERENCES class_groups(id) ON DELETE SET NULL,
    coach_teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
    total_program_fee REAL NOT NULL DEFAULT 0,
    total_one_on_one_fee REAL NOT NULL DEFAULT 0,
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Bir "ders bloğu" = haftada tekrar eden 1 saatlik bir ders ihtiyacı.
-- template_day/template_period doluysa bu, her hafta o hücrede görünür
-- (o haftaya özel bir istisna yoksa). Boşsa, blok "atanmamış dersler"
-- havuzunda bekler.
CREATE TABLE IF NOT EXISTS lesson_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE CASCADE,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    class_group_id INTEGER REFERENCES class_groups(id) ON DELETE CASCADE,
    student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
    room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
    template_day INTEGER,
    template_period INTEGER,
    note TEXT DEFAULT ''
);

-- Belirli bir haftaya özel istisna: o blok o hafta template'teki yerinde
-- DEĞİL, burada belirtilen gün/saatte görünür. day/period NULL ise o
-- hafta hiç görünmez (havuza geri düşer).
CREATE TABLE IF NOT EXISTS week_exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    lesson_block_id INTEGER NOT NULL REFERENCES lesson_blocks(id) ON DELETE CASCADE,
    day INTEGER,
    period INTEGER,
    UNIQUE(week_start, lesson_block_id)
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    amount REAL NOT NULL,
    payment_date TEXT NOT NULL,
    note TEXT DEFAULT ''
);
"""

DEFAULT_SETTINGS = {
    "day_names": ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"],
    "period_count": 8,
}


def default_db_path() -> Path:
    data_dir = Path.home() / "DersProgrami"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "veri.db"


class Database:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_db_path()
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._init_settings()

    # ---------- ayarlar ----------
    def _init_settings(self) -> None:
        for key, value in DEFAULT_SETTINGS.items():
            cur = self.conn.execute("SELECT 1 FROM settings WHERE key=?", (key,))
            if cur.fetchone() is None:
                self.conn.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?)",
                    (key, json.dumps(value, ensure_ascii=False)),
                )
        self.conn.commit()

    def get_setting(self, key: str):
        cur = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        if row is None:
            return DEFAULT_SETTINGS.get(key)
        return json.loads(row["value"])

    def set_setting(self, key: str, value) -> None:
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self.conn.commit()

    @property
    def day_names(self) -> list[str]:
        return self.get_setting("day_names")

    @property
    def period_count(self) -> int:
        return self.get_setting("period_count")

    # ---------- basit tablolar (ders, sınıf, derslik) ----------
    def list_rows(self, table: str) -> list[sqlite3.Row]:
        return self.conn.execute(f"SELECT * FROM {table} ORDER BY name").fetchall()

    def add_row(self, table: str, name: str, note: str = "") -> int:
        cur = self.conn.execute(
            f"INSERT INTO {table}(name, note) VALUES (?, ?)", (name, note)
        )
        self.conn.commit()
        return cur.lastrowid

    def update_row(self, table: str, row_id: int, name: str, note: str = "") -> None:
        self.conn.execute(
            f"UPDATE {table} SET name=?, note=? WHERE id=?", (name, note, row_id)
        )
        self.conn.commit()

    def delete_row(self, table: str, row_id: int) -> None:
        self.conn.execute(f"DELETE FROM {table} WHERE id=?", (row_id,))
        self.conn.commit()

    # ---------- öğretmenler ----------
    def list_teachers(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM teachers ORDER BY name").fetchall()

    def add_teacher(self, name: str, subject_area: str = "", note: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO teachers(name, subject_area, note) VALUES (?, ?, ?)",
            (name, subject_area, note),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_teacher(self, teacher_id: int, name: str, subject_area: str = "", note: str = "") -> None:
        self.conn.execute(
            "UPDATE teachers SET name=?, subject_area=?, note=? WHERE id=?",
            (name, subject_area, note, teacher_id),
        )
        self.conn.commit()

    def delete_teacher(self, teacher_id: int) -> None:
        self.conn.execute("DELETE FROM teachers WHERE id=?", (teacher_id,))
        self.conn.commit()

    # ---------- öğrenciler ----------
    def list_students(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT st.*, cg.name AS class_name, t.name AS coach_name
            FROM students st
            LEFT JOIN class_groups cg ON cg.id = st.class_group_id
            LEFT JOIN teachers t ON t.id = st.coach_teacher_id
            ORDER BY st.name
            """
        ).fetchall()

    def get_student(self, student_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()

    def add_student(
        self,
        name: str,
        class_group_id: int | None,
        coach_teacher_id: int | None,
        total_program_fee: float = 0,
        total_one_on_one_fee: float = 0,
        note: str = "",
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO students(name, class_group_id, coach_teacher_id, total_program_fee, total_one_on_one_fee, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, class_group_id, coach_teacher_id, total_program_fee, total_one_on_one_fee, note),
        )
        self.conn.commit()
        student_id = cur.lastrowid
        self._ensure_coaching_block(student_id, coach_teacher_id)
        return student_id

    def update_student(
        self,
        student_id: int,
        name: str,
        class_group_id: int | None,
        coach_teacher_id: int | None,
        total_program_fee: float = 0,
        total_one_on_one_fee: float = 0,
        note: str = "",
    ) -> None:
        self.conn.execute(
            """
            UPDATE students SET name=?, class_group_id=?, coach_teacher_id=?,
                total_program_fee=?, total_one_on_one_fee=?, note=?
            WHERE id=?
            """,
            (name, class_group_id, coach_teacher_id, total_program_fee, total_one_on_one_fee, note, student_id),
        )
        self.conn.commit()
        self._ensure_coaching_block(student_id, coach_teacher_id)

    def delete_student(self, student_id: int) -> None:
        self.conn.execute("DELETE FROM students WHERE id=?", (student_id,))
        self.conn.commit()

    def _ensure_coaching_block(self, student_id: int, coach_teacher_id: int | None) -> None:
        """Öğrenciye bir koç atanmışsa, o öğrenci için tam olarak bir
        'koçluk' ders bloğu bulunmasını garanti eder (yoksa oluşturur,
        koç değiştiyse öğretmenini günceller)."""
        existing = self.conn.execute(
            "SELECT id FROM lesson_blocks WHERE type=? AND student_id=?",
            (TYPE_COACHING, student_id),
        ).fetchone()
        if coach_teacher_id is None:
            return
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO lesson_blocks(type, teacher_id, student_id, template_day, template_period)
                VALUES (?, ?, ?, NULL, NULL)
                """,
                (TYPE_COACHING, coach_teacher_id, student_id),
            )
        else:
            self.conn.execute(
                "UPDATE lesson_blocks SET teacher_id=? WHERE id=?",
                (coach_teacher_id, existing["id"]),
            )
        self.conn.commit()

    # ---------- ders blokları ----------
    def add_lesson_blocks(
        self,
        type_: str,
        count: int,
        teacher_id: int,
        subject_id: int | None = None,
        class_group_id: int | None = None,
        student_id: int | None = None,
        room_id: int | None = None,
        note: str = "",
    ) -> list[int]:
        ids = []
        for _ in range(count):
            cur = self.conn.execute(
                """
                INSERT INTO lesson_blocks(type, teacher_id, subject_id, class_group_id, student_id, room_id, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (type_, teacher_id, subject_id, class_group_id, student_id, room_id, note),
            )
            ids.append(cur.lastrowid)
        self.conn.commit()
        return ids

    def delete_lesson_block(self, block_id: int) -> None:
        self.conn.execute("DELETE FROM lesson_blocks WHERE id=?", (block_id,))
        self.conn.commit()

    def list_lesson_blocks_detailed(self, where: str = "", params: tuple = ()) -> list[sqlite3.Row]:
        query = f"""
            SELECT lb.*, t.name AS teacher_name, s.name AS subject_name,
                   cg.name AS class_name, st.name AS student_name, r.name AS room_name
            FROM lesson_blocks lb
            LEFT JOIN teachers t ON t.id = lb.teacher_id
            LEFT JOIN subjects s ON s.id = lb.subject_id
            LEFT JOIN class_groups cg ON cg.id = lb.class_group_id
            LEFT JOIN students st ON st.id = lb.student_id
            LEFT JOIN rooms r ON r.id = lb.room_id
            {where}
        """
        return self.conn.execute(query, params).fetchall()

    def set_lesson_block_template_position(self, block_id: int, day: int | None, period: int | None) -> None:
        self.conn.execute(
            "UPDATE lesson_blocks SET template_day=?, template_period=? WHERE id=?",
            (day, period, block_id),
        )
        self.conn.commit()

    # ---------- hafta istisnaları ----------
    def get_week_exceptions(self, week_start: str) -> dict[int, tuple[int | None, int | None]]:
        rows = self.conn.execute(
            "SELECT lesson_block_id, day, period FROM week_exceptions WHERE week_start=?",
            (week_start,),
        ).fetchall()
        return {row["lesson_block_id"]: (row["day"], row["period"]) for row in rows}

    def set_week_exception(self, week_start: str, block_id: int, day: int | None, period: int | None) -> None:
        self.conn.execute(
            """
            INSERT INTO week_exceptions(week_start, lesson_block_id, day, period)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(week_start, lesson_block_id) DO UPDATE SET day=excluded.day, period=excluded.period
            """,
            (week_start, block_id, day, period),
        )
        self.conn.commit()

    def clear_week_exception(self, week_start: str, block_id: int) -> None:
        self.conn.execute(
            "DELETE FROM week_exceptions WHERE week_start=? AND lesson_block_id=?",
            (week_start, block_id),
        )
        self.conn.commit()

    # ---------- ödemeler ----------
    def list_payments(self, student_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM payments WHERE student_id=? ORDER BY payment_date",
            (student_id,),
        ).fetchall()

    def add_payment(self, student_id: int, amount: float, payment_date: str, note: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO payments(student_id, amount, payment_date, note) VALUES (?, ?, ?, ?)",
            (student_id, amount, payment_date, note),
        )
        self.conn.commit()
        return cur.lastrowid

    def delete_payment(self, payment_id: int) -> None:
        self.conn.execute("DELETE FROM payments WHERE id=?", (payment_id,))
        self.conn.commit()

    def total_paid(self, student_id: int) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE student_id=?",
            (student_id,),
        ).fetchone()
        return row["total"]

    def close(self) -> None:
        self.conn.close()
