import sqlite3
from datetime import datetime

DB_PATH = "lotto.db"


def init_birthday_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS userBirthdays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM userBirthdays WHERE user_id = ? ORDER BY slot",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def upsert_birthday(user_id, slot, label, mmdd):
    if slot < 1 or slot > 4:
        raise ValueError("슬롯 번호는 1~4 사이여야 합니다")
    
    conn = sqlite3.connect(DB_PATH)
    existing = conn.execute(
        "SELECT id FROM userBirthdays WHERE user_id = ? AND slot = ?",
        (user_id, slot)
    ).fetchone()
    
    now = datetime.now().isoformat()
    
    if existing:
        conn.execute(
            "UPDATE userBirthdays SET label = ?, mmdd = ?, updated_at = ? WHERE user_id = ? AND slot = ?",
            (label, mmdd, now, user_id, slot)
        )
    else:
        conn.execute(
            "INSERT INTO userBirthdays (user_id, slot, label, mmdd, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, slot, label, mmdd, now, now)
        )
    
    conn.commit()
    conn.close()


def delete_birthday(user_id, slot):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "DELETE FROM userBirthdays WHERE user_id = ? AND slot = ?",
        (user_id, slot)
    )
    conn.commit()
    conn.close()
