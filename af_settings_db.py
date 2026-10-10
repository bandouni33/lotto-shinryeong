"""고급필터 세팅 회원별 영구 저장 (2026-10-10 사용자 승인).

배경: 고급필터 세팅(1단계 패턴·범위·총합, 2단계 K-295 규칙표)은 서버 안의 파일
(data/users/member_<id>/…)에만 저장됐다. Streamlit Cloud 는 재부팅·재배포 때 그 파일을
지우므로 재접속하면 세팅이 사라졌고, 1단계 세팅은 '세팅완료 저장'을 눌러야만 저장됐다.
이 표는 회원별로 DB 에 두어 재부팅에도 남는다.

  draft_json  : 화면의 1단계 세팅 '지금 상태'(바뀔 때마다 자동 저장 — 재접속하면 이 값으로 채운다)
  saved_json  : 마지막으로 '세팅완료 저장'(또는 1단계 실행)한 세팅 — 저장 여부 표시용
  k295_json   : 2단계 K-295 규칙표(records)

계정 삭제 때 account_deletion.delete_account 가 delete_member_settings 로 지운다.

2026-10-10(사용자 승인): 로그인 전(게스트) 세팅을 로그인 뒤에도 이어받는다 — 앱 로그인은 화면을 새로
불러와(새 세션) 게스트가 만지던 세팅이 사라졌다. 게스트의 '지금 상태'를 기기 식별값(guest_id)으로
af_guest_drafts 에 잠깐 두었다가, 같은 기기에서 로그인하면 회원 세팅으로 옮기고 지운다.
기본값에서 바꾼 적이 있을 때만 저장하고, GUEST_DRAFT_KEEP_DAYS 가 지난 행은 정리한다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import db_turso

# '표 만들었음' 표시 — DB 연결 함수별(id)로 둔다(시험용 격리 DB 로 바뀌면 다시 확인).
_TABLE_READY = 0
_GUEST_TABLE_READY = 0
GUEST_DRAFT_KEEP_DAYS = 7
# 로그인 때 옮겨 받는 게스트 세팅은 이 시간 안에 만진 것만(오래전 게스트 세팅이 회원 세팅을 덮지 않게).
GUEST_DRAFT_ADOPT_HOURS = 24
_LAST_GUEST_CLEANUP = 0.0


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_af_settings_table() -> None:
    global _TABLE_READY
    if _TABLE_READY == id(db_turso.connect):
        return
    conn = db_turso.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS af_user_settings (
            member_id INTEGER PRIMARY KEY,
            draft_json TEXT,
            saved_json TEXT,
            k295_json TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    _TABLE_READY = id(db_turso.connect)


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def get_member_settings(member_id: int) -> dict:
    """{'draft': dict|None, 'saved': dict|None, 'k295': list|None} — 없으면 전부 None."""
    init_af_settings_table()
    conn = db_turso.connect()
    row = conn.execute(
        "SELECT draft_json, saved_json, k295_json FROM af_user_settings WHERE member_id = ?",
        (int(member_id),),
    ).fetchone()
    conn.close()
    out = {"draft": None, "saved": None, "k295": None}
    if not row:
        return out
    for key, raw in zip(("draft", "saved", "k295"), (row[0], row[1], row[2])):
        if raw:
            try:
                out[key] = json.loads(raw)
            except Exception:
                out[key] = None
    return out


def _upsert(member_id: int, column: str, value) -> None:
    if column not in ("draft_json", "saved_json", "k295_json"):
        raise ValueError(column)
    init_af_settings_table()
    conn = db_turso.connect()
    conn.execute(
        f"""
        INSERT INTO af_user_settings (member_id, {column}, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(member_id) DO UPDATE SET {column} = excluded.{column}, updated_at = excluded.updated_at
        """,
        (int(member_id), None if value is None else _dumps(value), _now()),
    )
    conn.commit()
    conn.close()


def save_draft(member_id: int, settings: dict) -> None:
    _upsert(member_id, "draft_json", settings)


def save_saved(member_id: int, settings: dict) -> None:
    _upsert(member_id, "saved_json", settings)


def save_k295(member_id: int, records: list) -> None:
    _upsert(member_id, "k295_json", records)


def delete_member_settings(member_id: int) -> int:
    # 탈퇴는 드문 작업이라 '이미 만들었음' 표시를 믿지 않고 항상 표를 확인한다(DB 가 바뀐 경우 대비).
    global _TABLE_READY
    _TABLE_READY = 0
    init_af_settings_table()
    conn = db_turso.connect()
    cur = conn.execute("DELETE FROM af_user_settings WHERE member_id = ?", (int(member_id),))
    n = int(getattr(cur, "rowcount", 0) or 0)
    conn.commit()
    conn.close()
    return n


# ── 게스트(로그인 전) 세팅 — 로그인 뒤 이어받기용 ─────────────────────────────────────────
def init_af_guest_table() -> None:
    # '만들었음' 표시는 DB 연결 함수별로 둔다(시험용 격리 DB 로 바뀌어도 다시 확인).
    global _GUEST_TABLE_READY
    if _GUEST_TABLE_READY == id(db_turso.connect):
        return
    conn = db_turso.connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS af_guest_drafts (
            guest_id TEXT PRIMARY KEY,
            draft_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()
    _GUEST_TABLE_READY = id(db_turso.connect)


def _cleanup_old_guest_drafts(conn) -> None:
    """오래된 게스트 세팅 정리 — 프로세스당 1시간에 한 번만."""
    global _LAST_GUEST_CLEANUP
    import time as _t

    if _t.time() - _LAST_GUEST_CLEANUP < 3600:
        return
    _LAST_GUEST_CLEANUP = _t.time()
    cutoff = (datetime.now() - timedelta(days=GUEST_DRAFT_KEEP_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("DELETE FROM af_guest_drafts WHERE updated_at < ?", (cutoff,))


def save_guest_draft(guest_id: str, settings: dict) -> None:
    if not guest_id:
        return
    init_af_guest_table()
    conn = db_turso.connect()
    conn.execute(
        """
        INSERT INTO af_guest_drafts (guest_id, draft_json, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(guest_id) DO UPDATE SET draft_json = excluded.draft_json, updated_at = excluded.updated_at
        """,
        (str(guest_id), _dumps(settings), _now()),
    )
    _cleanup_old_guest_drafts(conn)
    conn.commit()
    conn.close()


def get_guest_draft(guest_id: str, max_age_hours: float | None = None):
    """(세팅 dict, updated_at 문자열) 또는 None. max_age_hours 가 있으면 그보다 오래된 것은 None."""
    if not guest_id:
        return None
    init_af_guest_table()
    conn = db_turso.connect()
    row = conn.execute(
        "SELECT draft_json, updated_at FROM af_guest_drafts WHERE guest_id = ?",
        (str(guest_id),),
    ).fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    if max_age_hours is not None:
        try:
            age = datetime.now() - datetime.strptime(str(row[1]), "%Y-%m-%d %H:%M:%S")
            if age > timedelta(hours=max_age_hours):
                return None
        except Exception:
            return None
    try:
        return json.loads(row[0]), str(row[1])
    except Exception:
        return None


def delete_guest_draft(guest_id: str) -> None:
    if not guest_id:
        return
    init_af_guest_table()
    conn = db_turso.connect()
    conn.execute("DELETE FROM af_guest_drafts WHERE guest_id = ?", (str(guest_id),))
    conn.commit()
    conn.close()


def member_settings_updated_at(member_id: int):
    init_af_settings_table()
    conn = db_turso.connect()
    row = conn.execute(
        "SELECT updated_at FROM af_user_settings WHERE member_id = ?", (int(member_id),)
    ).fetchone()
    conn.close()
    return str(row[0]) if row and row[0] else None

