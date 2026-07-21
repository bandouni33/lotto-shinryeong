"""
Zero-Phone 익명 회원 DB — 전화번호·실명 등 PII 미수집.

카카오 채널 메시지 발송은 msg_queue.user_id 기준 (phone 컬럼 없음).
앱 내 마이페이지 조회가 1차, 채널 메시지가 2차 알림 경로.

────────────────────────────────────────
[향후 연결 예정] 포인트 차감 비즈니스 규칙 (아직 UI·버튼 미연결)
────────────────────────────────────────
규칙 1 — 자동구매: 5개 조합당 1,000점 / 10개 2,000점 (15→3,000 / 20→4,000)
규칙 2 — 번개조합: 5개 조합당 1,000점 / 10개 2,000점
규칙 3 — 고급필터: 월간 구독 15,000점 차감 + is_premium = True
공통 — 현금 결제 불가, 모든 서비스는 point_balance 확인 후 차감만 허용
공통 — 조합·결과 생성 성공 후 차감 (실패·0건 시 미차감)
────────────────────────────────────────
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = "lotto.db"
SIGNUP_BONUS = 5000
TEST_USER_ID = "test_user_01"

PURCHASE_TYPES = frozenset({"정기구독", "일반구매"})
SEND_STATUSES = frozenset({"WAIT", "SENT"})

KST = timezone(timedelta(hours=9))


def _now_iso() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S.%f")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_zero_phone_tables() -> None:
    """users · msg_queue 테이블 생성 (phone 컬럼 없음)."""
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            point_balance INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            is_premium INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS msg_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            purchase_type TEXT NOT NULL,
            send_status TEXT NOT NULL DEFAULT 'WAIT',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_msg_queue_status
            ON msg_queue(send_status, created_at);
        CREATE INDEX IF NOT EXISTS idx_msg_queue_user
            ON msg_queue(user_id, created_at);
        """
    )
    conn.commit()
    conn.close()


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    return {
        "user_id": str(row["user_id"]),
        "point_balance": int(row["point_balance"]),
        "created_at": str(row["created_at"]),
        "is_premium": bool(int(row["is_premium"])),
    }


def get_user(user_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT user_id, point_balance, created_at, is_premium FROM users WHERE user_id = ?",
        (str(user_id).strip(),),
    ).fetchone()
    conn.close()
    return _row_to_dict(row)


def get_or_create_user(user_id: str) -> tuple[dict, bool]:
    """(user dict, is_new). 신규 가입 시 SIGNUP_BONUS 지급."""
    uid = str(user_id).strip()
    if not uid:
        raise ValueError("user_id is required")

    conn = _connect()
    row = conn.execute(
        "SELECT user_id, point_balance, created_at, is_premium FROM users WHERE user_id = ?",
        (uid,),
    ).fetchone()
    if row:
        conn.close()
        return _row_to_dict(row), False

    now = _now_iso()
    conn.execute(
        """
        INSERT INTO users (user_id, point_balance, created_at, is_premium)
        VALUES (?, ?, ?, 0)
        """,
        (uid, SIGNUP_BONUS, now),
    )
    conn.commit()
    new_row = conn.execute(
        "SELECT user_id, point_balance, created_at, is_premium FROM users WHERE user_id = ?",
        (uid,),
    ).fetchone()
    conn.close()
    return _row_to_dict(new_row), True


def login_test_user(user_id: str = TEST_USER_ID) -> tuple[dict, bool]:
    """테스트 로그인 — 신규면 5,000점 자동 지급."""
    return get_or_create_user(user_id)


def enqueue_msg(
    user_id: str,
    purchase_type: str,
    send_status: str = "WAIT",
) -> int:
    """카카오 채널 메시지 대기열 (user_id만, phone 없음)."""
    uid = str(user_id).strip()
    ptype = str(purchase_type).strip()
    status = str(send_status).strip().upper()

    if not uid:
        raise ValueError("user_id is required")
    if ptype not in PURCHASE_TYPES:
        raise ValueError("purchase_type은 '정기구독' 또는 '일반구매'만 허용")
    if status not in SEND_STATUSES:
        raise ValueError("send_status는 'WAIT' 또는 'SENT'만 허용")

    if get_user(uid) is None:
        raise ValueError(f"unknown user_id: {uid}")

    conn = _connect()
    cur = conn.execute(
        """
        INSERT INTO msg_queue (user_id, purchase_type, send_status, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (uid, ptype, status, _now_iso()),
    )
    row_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return row_id
