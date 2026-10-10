"""고급필터 세팅 회원별 영구 저장 (2026-10-10 사용자 승인).

배경: 고급필터 세팅(1단계 패턴·범위·총합, 2단계 K-295 규칙표)은 서버 안의 파일
(data/users/member_<id>/…)에만 저장됐다. Streamlit Cloud 는 재부팅·재배포 때 그 파일을
지우므로 재접속하면 세팅이 사라졌고, 1단계 세팅은 '세팅완료 저장'을 눌러야만 저장됐다.
이 표는 회원별로 DB 에 두어 재부팅에도 남는다.

  draft_json  : 화면의 1단계 세팅 '지금 상태'(바뀔 때마다 자동 저장 — 재접속하면 이 값으로 채운다)
  saved_json  : 마지막으로 '세팅완료 저장'(또는 1단계 실행)한 세팅 — 저장 여부 표시용
  k295_json   : 2단계 K-295 규칙표(records)

계정 삭제 때 account_deletion.delete_account 가 delete_member_settings 로 지운다.
"""

from __future__ import annotations

import json
from datetime import datetime

import db_turso

_TABLE_READY = False


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_af_settings_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:
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
    _TABLE_READY = True


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
    _TABLE_READY = False
    init_af_settings_table()
    conn = db_turso.connect()
    cur = conn.execute("DELETE FROM af_user_settings WHERE member_id = ?", (int(member_id),))
    n = int(getattr(cur, "rowcount", 0) or 0)
    conn.commit()
    conn.close()
    return n
