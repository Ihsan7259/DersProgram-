"""SQLite veritabanı erişim katmanı.

Tüm sorgular burada toplanır; arayüz (UI) katmanı SQL bilmeden bu
fonksiyonları çağırır.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schedule_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_group_id INTEGER NOT NULL REFERENCES class_groups(id) ON DELETE CASCADE,
    day INTEGER NOT NULL,
    period INTEGER NOT NULL,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
    teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL,
    room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
    UNIQUE(class_group_id, day, period)
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

    # ---------- basit tablolar (öğretmen, ders, sınıf, derslik) ----------
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

    # ---------- program (schedule) ----------
    def get_class_schedule(self, class_group_id: int) -> dict[tuple[int, int], sqlite3.Row]:
        rows = self.conn.execute(
            """
            SELECT se.*, s.name AS subject_name, t.name AS teacher_name, r.name AS room_name
            FROM schedule_entries se
            LEFT JOIN subjects s ON s.id = se.subject_id
            LEFT JOIN teachers t ON t.id = se.teacher_id
            LEFT JOIN rooms r ON r.id = se.room_id
            WHERE se.class_group_id = ?
            """,
            (class_group_id,),
        ).fetchall()
        return {(row["day"], row["period"]): row for row in rows}

    def set_schedule_cell(
        self,
        class_group_id: int,
        day: int,
        period: int,
        subject_id: int | None,
        teacher_id: int | None,
        room_id: int | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO schedule_entries(class_group_id, day, period, subject_id, teacher_id, room_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(class_group_id, day, period) DO UPDATE SET
                subject_id=excluded.subject_id,
                teacher_id=excluded.teacher_id,
                room_id=excluded.room_id
            """,
            (class_group_id, day, period, subject_id, teacher_id, room_id),
        )
        self.conn.commit()

    def clear_schedule_cell(self, class_group_id: int, day: int, period: int) -> None:
        self.conn.execute(
            "DELETE FROM schedule_entries WHERE class_group_id=? AND day=? AND period=?",
            (class_group_id, day, period),
        )
        self.conn.commit()

    def find_conflicts(
        self, class_group_id: int, day: int, period: int, teacher_id: int | None, room_id: int | None
    ) -> list[sqlite3.Row]:
        """Aynı gün/saatte aynı öğretmen ya da derslik başka bir sınıfa
        atanmış mı diye bakar (kendi sınıfı hariç)."""
        conflicts: list[sqlite3.Row] = []
        if teacher_id is not None:
            conflicts += self.conn.execute(
                """
                SELECT se.*, cg.name AS class_name
                FROM schedule_entries se
                JOIN class_groups cg ON cg.id = se.class_group_id
                WHERE se.day=? AND se.period=? AND se.teacher_id=? AND se.class_group_id != ?
                """,
                (day, period, teacher_id, class_group_id),
            ).fetchall()
        if room_id is not None:
            conflicts += self.conn.execute(
                """
                SELECT se.*, cg.name AS class_name
                FROM schedule_entries se
                JOIN class_groups cg ON cg.id = se.class_group_id
                WHERE se.day=? AND se.period=? AND se.room_id=? AND se.class_group_id != ?
                """,
                (day, period, room_id, class_group_id),
            ).fetchall()
        return conflicts

    def all_conflicting_cells_for_teacher_room(self) -> set[tuple[int, int, int]]:
        """Tüm veritabanındaki çakışan (class_group_id, day, period) hücrelerini döner."""
        rows = self.conn.execute(
            "SELECT id, class_group_id, day, period, teacher_id, room_id FROM schedule_entries"
        ).fetchall()
        conflicting: set[tuple[int, int, int]] = set()
        by_teacher_slot: dict[tuple[int, int, int], list[sqlite3.Row]] = {}
        by_room_slot: dict[tuple[int, int, int], list[sqlite3.Row]] = {}
        for row in rows:
            if row["teacher_id"] is not None:
                key = (row["teacher_id"], row["day"], row["period"])
                by_teacher_slot.setdefault(key, []).append(row)
            if row["room_id"] is not None:
                key = (row["room_id"], row["day"], row["period"])
                by_room_slot.setdefault(key, []).append(row)
        for group in list(by_teacher_slot.values()) + list(by_room_slot.values()):
            if len(group) > 1:
                for row in group:
                    conflicting.add((row["class_group_id"], row["day"], row["period"]))
        return conflicting

    def close(self) -> None:
        self.conn.close()
