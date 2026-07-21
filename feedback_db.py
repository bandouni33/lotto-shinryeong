"""테스트 기간 개선 요구사항 수집 (SQLite)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

DB_PATH = "lotto.db"

FEEDBACK_CATEGORIES = ("UI/화면", "기능", "버그", "속도", "기타")


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_feedback_tables() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS improvement_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL DEFAULT '익명',
            category TEXT NOT NULL DEFAULT '기타',
            body TEXT NOT NULL,
            member_id INTEGER,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_feedback_created
        ON improvement_feedback(created_at DESC)
        """
    )
    conn.commit()
    conn.close()


def save_feedback(
    body: str,
    *,
    nickname: str = "익명",
    category: str = "기타",
    member_id: int | None = None,
) -> int:
    text = (body or "").strip()
    if not text:
        raise ValueError("내용을 입력해 주세요.")
    if len(text) > 2000:
        raise ValueError("2000자 이내로 입력해 주세요.")

    nick = (nickname or "익명").strip() or "익명"
    cat = (category or "기타").strip() or "기타"
    if cat not in FEEDBACK_CATEGORIES:
        cat = "기타"

    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        """
        INSERT INTO improvement_feedback (nickname, category, body, member_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (nick[:40], cat, text, member_id, _now_iso()),
    )
    row_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return row_id


def list_feedback(limit: int = 500) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, nickname, category, body, member_id, created_at
        FROM improvement_feedback
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def count_feedback() -> int:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT COUNT(*) FROM improvement_feedback").fetchone()
    conn.close()
    return int(row[0]) if row else 0
