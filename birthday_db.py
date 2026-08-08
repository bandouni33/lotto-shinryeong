import sqlite3
import db_turso
from datetime import datetime

from lucky_numbers import validate_mmdd

DB_PATH = "lotto.db"


def _normalize_scope(user_id) -> str:
    return str(user_id).strip()


def init_birthday_table():
    conn = db_turso.connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS userBirthdays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            slot INTEGER NOT NULL,
            label TEXT NOT NULL,
            mmdd TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_slot 
        ON userBirthdays(user_id, slot)
    """)
    conn.commit()
    conn.close()


def get_user_birthdays(user_id):
    init_birthday_table()
    scope = _normalize_scope(user_id)
    conn = db_turso.connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM userBirthdays WHERE user_id = ? ORDER BY slot",
        (scope,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def upsert_birthday(user_id, slot, label, mmdd):
    init_birthday_table()
    scope = _normalize_scope(user_id)
    if slot < 1 or slot > 4:
        raise ValueError("슬롯 번호는 1~4 사이여야 합니다")

    ok, err = validate_mmdd(mmdd)
    if not ok:
        raise ValueError(err or "월일 형식이 올바르지 않습니다")

    conn = db_turso.connect()
    existing = conn.execute(
        "SELECT id FROM userBirthdays WHERE user_id = ? AND slot = ?",
        (scope, slot),
    ).fetchone()

    now = datetime.now().isoformat()

    if existing:
        conn.execute(
            "UPDATE userBirthdays SET label = ?, mmdd = ?, updated_at = ? WHERE user_id = ? AND slot = ?",
            (label, mmdd, now, scope, slot),
        )
    else:
        conn.execute(
            "INSERT INTO userBirthdays (user_id, slot, label, mmdd, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (scope, slot, label, mmdd, now, now),
        )

    conn.commit()
    conn.close()


def delete_birthday(user_id, slot):
    init_birthday_table()
    scope = _normalize_scope(user_id)
    conn = db_turso.connect()
    conn.execute(
        "DELETE FROM userBirthdays WHERE user_id = ? AND slot = ?",
        (scope, slot),
    )
    conn.commit()
    conn.close()
