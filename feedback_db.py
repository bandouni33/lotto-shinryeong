"""테스트 기간 개선 요구사항 수집 (SQLite)."""

from __future__ import annotations

import sqlite3
import db_turso
from datetime import datetime

DB_PATH = "lotto.db"

FEEDBACK_CATEGORIES = ("UI/화면", "기능", "버그", "속도", "기타")

# 2026-09-19: "고객불만/개선요구사항" 처리상태 관리 추가 — 운영자가 대시보드에서
# 어디까지 처리했는지 표시·필터링할 수 있게 한다. 새로 들어오는 건 항상 대기부터
# 시작(DEFAULT '대기').
FEEDBACK_STATUSES = ("대기", "처리중", "완료")
DEFAULT_FEEDBACK_STATUS = "대기"


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


_FEEDBACK_TABLES_READY = False


def init_feedback_tables() -> None:
    """CREATE TABLE/INDEX IF NOT EXISTS라 멱등이지만, user_page.py가 거의 모든 페이지
    렌더마다 호출해서 원격 DB 왕복이 반복되던 걸 막기 위해(zero_phone_db와 동일한 방식)
    최초 1회 이후로는 스킵한다."""
    global _FEEDBACK_TABLES_READY
    if _FEEDBACK_TABLES_READY:
        return
    conn = db_turso.connect()
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
    # 2026-09-19: 기존 DB 호환 ALTER — wallet_db.init_wallet_tables와 동일한 패턴
    # (PRAGMA table_info로 이미 있는지 확인 후에만 추가). 기존 행은 전부 DEFAULT
    # '대기'로 채워지며, 이미 실제로 처리됐던 과거 건까지 자동으로 다시 '대기'로
    # 보이는 건 어쩔 수 없다(운영자가 필요하면 수동으로 넘기면 됨).
    cols = {row[1] for row in conn.execute("PRAGMA table_info(improvement_feedback)")}
    if "status" not in cols:
        conn.execute(
            f"ALTER TABLE improvement_feedback ADD COLUMN status TEXT NOT NULL DEFAULT '{DEFAULT_FEEDBACK_STATUS}'"
        )
    conn.commit()
    conn.close()
    _FEEDBACK_TABLES_READY = True


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

    conn = db_turso.connect()
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


def list_feedback(limit: int = 500, status: str | None = None) -> list[dict]:
    """status를 주면 그 상태만 필터링(운영자 대시보드 탭용). None이면 전체."""
    conn = db_turso.connect()
    conn.row_factory = sqlite3.Row
    if status:
        rows = conn.execute(
            """
            SELECT id, nickname, category, body, member_id, status, created_at
            FROM improvement_feedback
            WHERE status = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (status, int(limit)),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, nickname, category, body, member_id, status, created_at
            FROM improvement_feedback
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def count_feedback(status: str | None = None) -> int:
    conn = db_turso.connect()
    if status:
        row = conn.execute(
            "SELECT COUNT(*) FROM improvement_feedback WHERE status = ?", (status,)
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) FROM improvement_feedback").fetchone()
    conn.close()
    return int(row[0]) if row else 0


def update_feedback_status(feedback_id: int, status: str) -> None:
    if status not in FEEDBACK_STATUSES:
        raise ValueError(f"알 수 없는 상태: {status}")
    conn = db_turso.connect()
    conn.execute(
        "UPDATE improvement_feedback SET status = ? WHERE id = ?",
        (status, int(feedback_id)),
    )
    conn.commit()
    conn.close()
