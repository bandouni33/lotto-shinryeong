"""외부 침입 시도(관리자 비밀번호 실패, 다운로드 남용 등) 기록 — 운영자 대시보드 알림용.

admin_auth_guard.py의 실패 카운터는 프로세스 메모리에만 있어서(서버 재시작하면
사라지고, 언제 몇 번 시도됐는지 이력도 안 남는다) 운영자가 나중에 돌아볼 수 있는
기록이 없었다. 이 모듈은 그 일들을 DB에 영속 기록해서, 대시보드에서 "누가 언제
얼마나 시도했는지" 확인할 수 있게 한다.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import db_turso

KST = timezone(timedelta(hours=9))

EVENT_LABELS = {
    "admin_login_fail": "관리자 비밀번호 실패",
    "admin_lockout": "관리자 로그인 잠금 발동",
    "download_rate_limited": "조합 다운로드 요청 과다",
    "cookie_reachable": "게스트 쿠키 서버 도달 여부(계측)",
    "guest_autologin_ua_mismatch": "게스트 자동로그인 UA 불일치 차단",
    "mock_charge_rate_limited": "Mock 결제(테스트 충전) 횟수 제한 도달",
    "toss_amount_mismatch": "토스 결제 콜백 금액 위·변조 의심(승인 거부)",
}

# 2026-09-19: cookie_reachable은 세션마다 정상적으로 매번 기록되는 순수 계측용
# 이벤트라, count_recent_events()가 그대로 세면 대시보드의 "🚨 침입 시도 의심"
# 배지가 정상 트래픽만으로 상시 빨간불이 된다(admin_dashboard.py의
# `_sec_recent_count > 0` 조건). 침입 의심 배지 집계에서는 제외하고,
# list_recent_events()의 상세 목록에는 그대로 남겨 계측 목적은 유지한다.
_NON_ALERTING_EVENT_TYPES = frozenset({"cookie_reachable"})


def _connect():
    return db_turso.connect()


_SECURITY_TABLES_READY = False


def init_security_tables() -> None:
    """CREATE TABLE/INDEX IF NOT EXISTS라 멱등이지만, 이벤트가 생길 때마다 호출되므로
    다른 모듈들과 동일한 패턴으로 최초 1회 이후엔 스킵한다."""
    global _SECURITY_TABLES_READY
    if _SECURITY_TABLES_READY:
        return
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            detail TEXT,
            ip_address TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_security_events_created
        ON security_events(created_at)
        """
    )
    conn.commit()
    conn.close()
    _SECURITY_TABLES_READY = True


def log_event(event_type: str, detail: str = "") -> None:
    """이벤트 하나를 기록한다. IP는 st.context.ip_address(스푸핑 가능, 참고용)를 쓴다.

    호출부(admin_auth_guard 등)의 실제 동작(잠금 처리 등)을 막으면 안 되므로,
    이 함수를 부르는 쪽에서 항상 try/except로 감싸서 실패해도 무시하도록 한다.
    """
    import streamlit as st

    init_security_tables()
    try:
        ip = st.context.ip_address
    except Exception:
        ip = None
    conn = _connect()
    conn.execute(
        """
        INSERT INTO security_events (event_type, detail, ip_address, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (event_type, detail, ip, datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def count_recent_events(hours: int = 24) -> int:
    """최근 N시간 안의 '침입 의심' 이벤트 수 — 대시보드 알림 배지용.
    순수 계측 이벤트(_NON_ALERTING_EVENT_TYPES)는 제외한다."""
    init_security_tables()
    conn = _connect()
    cutoff = (datetime.now(KST) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    placeholders = ",".join("?" for _ in _NON_ALERTING_EVENT_TYPES) or "''"
    row = conn.execute(
        f"SELECT COUNT(*) AS c FROM security_events WHERE created_at >= ? AND event_type NOT IN ({placeholders})",
        (cutoff, *_NON_ALERTING_EVENT_TYPES),
    ).fetchone()
    conn.close()
    return int(row[0]) if row else 0


def list_recent_events(limit: int = 50) -> list[dict]:
    """최신순 이벤트 목록 — 대시보드 표시용."""
    init_security_tables()
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT event_type, detail, ip_address, created_at
        FROM security_events
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
