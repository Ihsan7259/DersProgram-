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
    note TEXT DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
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
    zumre_group_id INTEGER,
    curriculum_id INTEGER REFERENCES class_curriculum(id) ON DELETE SET NULL,
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

-- Bir öğretmenin kalıcı (dönem boyunca) haftalık müsaitlik durumu.
-- Sadece işaretlenmiş (müsait/müsait değil) hücreler burada satır olarak
-- bulunur; hiç işaretlenmemiş hücreler için satır yoktur.
CREATE TABLE IF NOT EXISTS teacher_availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    period INTEGER NOT NULL,
    status TEXT NOT NULL,
    UNIQUE(teacher_id, day, period)
);

-- Belirli bir haftaya özel müsaitlik istisnası: o hafta kalıcı durumun
-- yerine burada belirtilen durum geçerlidir. status='clear' ise o hafta
-- hiç işaretlenmemiş gibi davranılır (kalıcı durum o hafta için gizlenir).
CREATE TABLE IF NOT EXISTS teacher_availability_exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    period INTEGER NOT NULL,
    status TEXT NOT NULL,
    UNIQUE(week_start, teacher_id, day, period)
);

-- Sınıfın haftalık ders hedefi: "9-A'da Matematik, Ahmet Yılmaz ile
-- haftada 5 saat". Kaydedilince weekly_hours kadar ders bloğu üretilir ve
-- bunlar curriculum_id ile bu hedefe bağlanır; böylece havuzdan bir ders
-- silinirse "hedef 5, programda 4" farkı Sınıflar sekmesinde görünür.
CREATE TABLE IF NOT EXISTS class_curriculum (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_group_id INTEGER NOT NULL REFERENCES class_groups(id) ON DELETE CASCADE,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
    room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
    weekly_hours INTEGER NOT NULL DEFAULT 1
);

-- Öğrenci ve sınıf müsaitliği: teacher_availability(_exceptions) ile
-- birebir aynı şablon+istisna deseni, sadece ilgili kişi/sınıfa bağlı.
CREATE TABLE IF NOT EXISTS student_availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    period INTEGER NOT NULL,
    status TEXT NOT NULL,
    UNIQUE(student_id, day, period)
);

CREATE TABLE IF NOT EXISTS student_availability_exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    period INTEGER NOT NULL,
    status TEXT NOT NULL,
    UNIQUE(week_start, student_id, day, period)
);

CREATE TABLE IF NOT EXISTS class_availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_group_id INTEGER NOT NULL REFERENCES class_groups(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    period INTEGER NOT NULL,
    status TEXT NOT NULL,
    UNIQUE(class_group_id, day, period)
);

CREATE TABLE IF NOT EXISTS class_availability_exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,
    class_group_id INTEGER NOT NULL REFERENCES class_groups(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    period INTEGER NOT NULL,
    status TEXT NOT NULL,
    UNIQUE(week_start, class_group_id, day, period)
);
"""

DEFAULT_SETTINGS = {
    "day_names": ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"],
    "period_count": 8,
    "theme": "light",
    "term_start": None,
    "term_end": None,
}


def default_db_path() -> Path:
    data_dir = Path.home() / "DersProgrami"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "veri.db"


# Geliştirme sürecinde SCHEMA'ya sonradan eklenen sütunlar burada listelenir.
# "CREATE TABLE IF NOT EXISTS" var olan bir tabloyu asla değiştirmediği için,
# programın önceki bir sürümüyle oluşturulmuş bir veritabanı dosyasında bu
# sütunlar eksik kalabilir (ör. "table teachers has no column named
# subject_area" hatası). Her açılışta eksik sütunlar burada tamamlanır.
MIGRATION_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "teachers": [
        ("subject_area", "TEXT DEFAULT ''"),
        ("note", "TEXT DEFAULT ''"),
    ],
    "subjects": [("note", "TEXT DEFAULT ''")],
    "class_groups": [("note", "TEXT DEFAULT ''"), ("sort_order", "INTEGER NOT NULL DEFAULT 0")],
    "rooms": [("note", "TEXT DEFAULT ''")],
    "students": [
        ("class_group_id", "INTEGER REFERENCES class_groups(id) ON DELETE SET NULL"),
        ("coach_teacher_id", "INTEGER REFERENCES teachers(id) ON DELETE SET NULL"),
        ("total_program_fee", "REAL NOT NULL DEFAULT 0"),
        ("total_one_on_one_fee", "REAL NOT NULL DEFAULT 0"),
        ("note", "TEXT DEFAULT ''"),
    ],
    "lesson_blocks": [
        ("teacher_id", "INTEGER REFERENCES teachers(id) ON DELETE CASCADE"),
        ("subject_id", "INTEGER REFERENCES subjects(id) ON DELETE SET NULL"),
        ("class_group_id", "INTEGER REFERENCES class_groups(id) ON DELETE CASCADE"),
        ("student_id", "INTEGER REFERENCES students(id) ON DELETE CASCADE"),
        ("room_id", "INTEGER REFERENCES rooms(id) ON DELETE SET NULL"),
        ("zumre_group_id", "INTEGER"),
        ("curriculum_id", "INTEGER"),
        ("template_day", "INTEGER"),
        ("template_period", "INTEGER"),
        ("note", "TEXT DEFAULT ''"),
    ],
    "payments": [("note", "TEXT DEFAULT ''")],
}


class Database:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_db_path()
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._migrate_schema()
        self._init_settings()

    def _migrate_schema(self) -> None:
        for table, columns in MIGRATION_COLUMNS.items():
            existing = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
            for column_name, column_def in columns:
                if column_name not in existing:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_def}")
        self.conn.commit()

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

    @property
    def theme(self) -> str:
        return self.get_setting("theme") or "light"

    @property
    def term_start(self) -> str | None:
        return self.get_setting("term_start")

    @property
    def term_end(self) -> str | None:
        return self.get_setting("term_end")

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

    # ---------- sınıflar (elle sıralanabilir) ----------
    def list_class_groups(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM class_groups ORDER BY sort_order, name").fetchall()

    def add_class_group(self, name: str, note: str = "") -> int:
        row = self.conn.execute("SELECT COALESCE(MAX(sort_order), -1) AS m FROM class_groups").fetchone()
        next_order = row["m"] + 1
        cur = self.conn.execute(
            "INSERT INTO class_groups(name, note, sort_order) VALUES (?, ?, ?)", (name, note, next_order)
        )
        self.conn.commit()
        return cur.lastrowid

    def move_class_group(self, class_id: int, direction: int) -> None:
        """direction: -1 (yukarı) ya da +1 (aşağı). Görüntülenen sıradaki
        komşusuyla yer değiştirir; sıralamayı her seferinde 0..N-1 olarak
        yeniden numaralandırır (eski/eksik sort_order değerlerinde de
        güvenli çalışır)."""
        ids = [row["id"] for row in self.list_class_groups()]
        if class_id not in ids:
            return
        idx = ids.index(class_id)
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(ids):
            return
        ids[idx], ids[new_idx] = ids[new_idx], ids[idx]
        self.conn.executemany(
            "UPDATE class_groups SET sort_order=? WHERE id=?",
            [(position, cid) for position, cid in enumerate(ids)],
        )
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

    def add_zumre_group(
        self,
        teacher_ids: list[int],
        subject_id: int | None = None,
        room_id: int | None = None,
        note: str = "",
    ) -> list[int]:
        """Bir zümre 'buluşması' = seçilen tüm öğretmenler için, ortak bir
        zumre_group_id ile birbirine bağlı birer blok. Ana Program'da bu
        grup tek bir atanmamış ders olarak görünür; herhangi bir üyenin
        satırına sürüklenip bırakıldığında tüm grup aynı gün/saate
        yerleştirilir (bkz. scheduling.find_group_conflicts,
        schedule_tab.ScheduleTab._group_members)."""
        ids = []
        for teacher_id in teacher_ids:
            cur = self.conn.execute(
                """
                INSERT INTO lesson_blocks(type, teacher_id, subject_id, room_id, note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (TYPE_DEPARTMENT, teacher_id, subject_id, room_id, note),
            )
            ids.append(cur.lastrowid)
        group_id = min(ids)
        self.conn.executemany(
            "UPDATE lesson_blocks SET zumre_group_id=? WHERE id=?",
            [(group_id, i) for i in ids],
        )
        self.conn.commit()
        return ids

    # ---------- sınıf ders hedefleri (müfredat) ----------
    def list_class_curriculum(self, class_group_id: int) -> list[sqlite3.Row]:
        """Sınıfın ders hedefleri + her hedef için gerçekte kaç blok var
        (planned) ve kaçı programa yerleşmiş (placed)."""
        return self.conn.execute(
            """
            SELECT cc.*, s.name AS subject_name, t.name AS teacher_name, r.name AS room_name,
                   (SELECT COUNT(*) FROM lesson_blocks lb WHERE lb.curriculum_id = cc.id) AS planned_hours,
                   (SELECT COUNT(*) FROM lesson_blocks lb WHERE lb.curriculum_id = cc.id
                        AND lb.template_day IS NOT NULL) AS placed_hours
            FROM class_curriculum cc
            LEFT JOIN subjects s ON s.id = cc.subject_id
            LEFT JOIN teachers t ON t.id = cc.teacher_id
            LEFT JOIN rooms r ON r.id = cc.room_id
            WHERE cc.class_group_id = ?
            ORDER BY s.name, t.name
            """,
            (class_group_id,),
        ).fetchall()

    def add_class_curriculum(
        self,
        class_group_id: int,
        subject_id: int | None,
        teacher_id: int | None,
        weekly_hours: int,
        room_id: int | None = None,
    ) -> int:
        """Hedefi kaydeder ve weekly_hours kadar ders bloğu üretip havuza
        (atanmamış dersler) düşürür."""
        cur = self.conn.execute(
            """
            INSERT INTO class_curriculum(class_group_id, subject_id, teacher_id, room_id, weekly_hours)
            VALUES (?, ?, ?, ?, ?)
            """,
            (class_group_id, subject_id, teacher_id, room_id, weekly_hours),
        )
        curriculum_id = cur.lastrowid
        for _ in range(weekly_hours):
            self.conn.execute(
                """
                INSERT INTO lesson_blocks(type, teacher_id, subject_id, class_group_id, room_id, curriculum_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (TYPE_CLASS, teacher_id, subject_id, class_group_id, room_id, curriculum_id),
            )
        self.conn.commit()
        return curriculum_id

    def delete_class_curriculum(self, curriculum_id: int) -> None:
        """Hedefi ve ona bağlı tüm ders bloklarını siler."""
        self.conn.execute("DELETE FROM lesson_blocks WHERE curriculum_id=?", (curriculum_id,))
        self.conn.execute("DELETE FROM class_curriculum WHERE id=?", (curriculum_id,))
        self.conn.commit()

    def restore_curriculum_blocks(self, curriculum_id: int) -> int:
        """Hedefteki saat sayısına göre eksik kalan blokları yeniden
        oluşturur (havuzdan silinenleri geri getirmek için). Kaç blok
        eklendiğini döner."""
        row = self.conn.execute(
            "SELECT * FROM class_curriculum WHERE id=?", (curriculum_id,)
        ).fetchone()
        if row is None:
            return 0
        existing = self.conn.execute(
            "SELECT COUNT(*) AS c FROM lesson_blocks WHERE curriculum_id=?", (curriculum_id,)
        ).fetchone()["c"]
        missing = max(0, row["weekly_hours"] - existing)
        for _ in range(missing):
            self.conn.execute(
                """
                INSERT INTO lesson_blocks(type, teacher_id, subject_id, class_group_id, room_id, curriculum_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (TYPE_CLASS, row["teacher_id"], row["subject_id"], row["class_group_id"],
                 row["room_id"], curriculum_id),
            )
        self.conn.commit()
        return missing

    def list_teachers_by_subject_area(self, subject_name: str) -> list[sqlite3.Row]:
        """Branşı verilen derse eşit olan öğretmenler (Sınıflar sekmesinde
        ders seçilince öğretmen listesini süzmek için)."""
        return self.conn.execute(
            "SELECT * FROM teachers WHERE subject_area = ? ORDER BY name", (subject_name,)
        ).fetchall()

    def delete_lesson_block(self, block_id: int) -> None:
        self.conn.execute("DELETE FROM lesson_blocks WHERE id=?", (block_id,))
        self.conn.commit()

    def list_lesson_blocks_detailed(self, where: str = "", params: tuple = ()) -> list[sqlite3.Row]:
        query = f"""
            SELECT lb.*, t.name AS teacher_name, s.name AS subject_name,
                   cg.name AS class_name, st.name AS student_name, r.name AS room_name,
                   st.class_group_id AS student_class_group_id
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

    # ---------- müsaitlik (öğretmen/öğrenci/sınıf ortak deseni) ----------
    # Üç varlık türü de aynı "şablon (kalıcı) + haftalık istisna" desenini
    # kullanır; SQL burada tek yerde yazılır, aşağıdaki teacher_*/student_*/
    # class_* metodları sadece ilgili tabloyu/sütunu seçen ince sarmalayıcılardır.
    def _get_availability_template(self, table: str, id_column: str, entity_id: int) -> dict[tuple[int, int], str]:
        rows = self.conn.execute(
            f"SELECT day, period, status FROM {table} WHERE {id_column}=?",
            (entity_id,),
        ).fetchall()
        return {(row["day"], row["period"]): row["status"] for row in rows}

    def _set_availability_template(self, table: str, id_column: str, entity_id: int, day: int, period: int, status: str | None) -> None:
        if status is None:
            self.conn.execute(
                f"DELETE FROM {table} WHERE {id_column}=? AND day=? AND period=?",
                (entity_id, day, period),
            )
        else:
            self.conn.execute(
                f"""
                INSERT INTO {table}({id_column}, day, period, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT({id_column}, day, period) DO UPDATE SET status=excluded.status
                """,
                (entity_id, day, period, status),
            )
        self.conn.commit()

    def _get_availability_exceptions(self, table: str, id_column: str, week_start: str) -> dict[tuple[int, int, int], str]:
        rows = self.conn.execute(
            f"SELECT {id_column} AS eid, day, period, status FROM {table} WHERE week_start=?",
            (week_start,),
        ).fetchall()
        return {(row["eid"], row["day"], row["period"]): row["status"] for row in rows}

    def _set_availability_exception(self, table: str, id_column: str, week_start: str, entity_id: int, day: int, period: int, status: str) -> None:
        self.conn.execute(
            f"""
            INSERT INTO {table}(week_start, {id_column}, day, period, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(week_start, {id_column}, day, period) DO UPDATE SET status=excluded.status
            """,
            (week_start, entity_id, day, period, status),
        )
        self.conn.commit()

    def _clear_availability_exception(self, table: str, id_column: str, week_start: str, entity_id: int, day: int, period: int) -> None:
        self.conn.execute(
            f"DELETE FROM {table} WHERE week_start=? AND {id_column}=? AND day=? AND period=?",
            (week_start, entity_id, day, period),
        )
        self.conn.commit()

    # ---------- öğretmen müsaitliği ----------
    def get_teacher_availability_template(self, teacher_id: int) -> dict[tuple[int, int], str]:
        return self._get_availability_template("teacher_availability", "teacher_id", teacher_id)

    def set_teacher_availability_template(self, teacher_id: int, day: int, period: int, status: str | None) -> None:
        self._set_availability_template("teacher_availability", "teacher_id", teacher_id, day, period, status)

    def get_teacher_availability_exceptions(self, week_start: str) -> dict[tuple[int, int, int], str]:
        return self._get_availability_exceptions("teacher_availability_exceptions", "teacher_id", week_start)

    def set_teacher_availability_exception(self, week_start: str, teacher_id: int, day: int, period: int, status: str) -> None:
        self._set_availability_exception("teacher_availability_exceptions", "teacher_id", week_start, teacher_id, day, period, status)

    def clear_teacher_availability_exception(self, week_start: str, teacher_id: int, day: int, period: int) -> None:
        self._clear_availability_exception("teacher_availability_exceptions", "teacher_id", week_start, teacher_id, day, period)

    def get_teacher_unavailable_exception_weeks(self, teacher_id: int, day: int, period: int) -> list[str]:
        """Bu öğretmenin bu (gün, saat) için 'müsait değil' olarak
        işaretlediği tüm haftaların (week_start) listesi - kalıcı bir
        yerleştirmenin başka bir haftadaki istisnayla çelişip
        çelişmediğini kontrol etmek için kullanılır."""
        rows = self.conn.execute(
            """
            SELECT DISTINCT week_start FROM teacher_availability_exceptions
            WHERE teacher_id=? AND day=? AND period=? AND status='unavailable'
            ORDER BY week_start
            """,
            (teacher_id, day, period),
        ).fetchall()
        return [row["week_start"] for row in rows]

    # ---------- öğrenci müsaitliği ----------
    def get_student_availability_template(self, student_id: int) -> dict[tuple[int, int], str]:
        return self._get_availability_template("student_availability", "student_id", student_id)

    def set_student_availability_template(self, student_id: int, day: int, period: int, status: str | None) -> None:
        self._set_availability_template("student_availability", "student_id", student_id, day, period, status)

    def get_student_availability_exceptions(self, week_start: str) -> dict[tuple[int, int, int], str]:
        return self._get_availability_exceptions("student_availability_exceptions", "student_id", week_start)

    def set_student_availability_exception(self, week_start: str, student_id: int, day: int, period: int, status: str) -> None:
        self._set_availability_exception("student_availability_exceptions", "student_id", week_start, student_id, day, period, status)

    def clear_student_availability_exception(self, week_start: str, student_id: int, day: int, period: int) -> None:
        self._clear_availability_exception("student_availability_exceptions", "student_id", week_start, student_id, day, period)

    # ---------- sınıf müsaitliği ----------
    def get_class_availability_template(self, class_group_id: int) -> dict[tuple[int, int], str]:
        return self._get_availability_template("class_availability", "class_group_id", class_group_id)

    def set_class_availability_template(self, class_group_id: int, day: int, period: int, status: str | None) -> None:
        self._set_availability_template("class_availability", "class_group_id", class_group_id, day, period, status)

    def get_class_availability_exceptions(self, week_start: str) -> dict[tuple[int, int, int], str]:
        return self._get_availability_exceptions("class_availability_exceptions", "class_group_id", week_start)

    def set_class_availability_exception(self, week_start: str, class_group_id: int, day: int, period: int, status: str) -> None:
        self._set_availability_exception("class_availability_exceptions", "class_group_id", week_start, class_group_id, day, period, status)

    def clear_class_availability_exception(self, week_start: str, class_group_id: int, day: int, period: int) -> None:
        self._clear_availability_exception("class_availability_exceptions", "class_group_id", week_start, class_group_id, day, period)

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
