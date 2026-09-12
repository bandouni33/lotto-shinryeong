"""앱 전역 설정(키-값) — Turso 저장. 업데이트 안내 배너 등 관리자가 코드 배포 없이 바꿀 값."""

from __future__ import annotations

import db_turso

UPDATE_VERSION_KEY = "latest_app_version"
UPDATE_URL_KEY = "update_url"
UPDATE_MESSAGE_KEY = "update_message"
MAX_CONCURRENT_SESSIONS_KEY = "max_concurrent_sessions"


def _connect():
    return db_turso.connect()


_SETTINGS_TABLE_READY = False


def init_settings_table() -> None:
    """CREATE TABLE IF NOT EXISTS라 멱등이지만, get_update_notice()가 거의 모든 페이지
    렌더마다 호출해서 원격 DB 왕복이 반복되던 걸 막기 위해(zero_phone_db와 동일한 방식)
    최초 1회 이후로는 스킵한다."""
    global _SETTINGS_TABLE_READY
    if _SETTINGS_TABLE_READY:
        return
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    _SETTINGS_TABLE_READY = True


def get_setting(key: str, default: str = "") -> str:
    conn = _connect()
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return str(row["value"]) if row else default


def set_setting(key: str, value: str) -> None:
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect()
    conn.execute(
        """
        INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, now),
    )
    conn.commit()
    conn.close()


def get_update_notice() -> dict:
    """{'version': str, 'url': str, 'message': str} — version이 비어있으면 배너 비활성.

    2026-09-12 수정: 예전엔 get_setting()을 3번 따로 불러 원격 DB를 순차로
    3번 왕복했다. 호출부(user_page.py)도 결과를 메인 화면에서만 쓰면서
    정작 이 함수는 모든 화면 렌더마다 불려서, 화면을 옮길 때마다 안 쓰이는
    조회가 3번씩 쌓이고 있었다(호출부는 main 화면에서만 부르도록 별도로
    옮김). 여기서는 한 번의 IN 쿼리로 합쳐 왕복을 1회로 줄인다."""
    init_settings_table()
    keys = (UPDATE_VERSION_KEY, UPDATE_URL_KEY, UPDATE_MESSAGE_KEY)
    conn = _connect()
    placeholders = ",".join("?" for _ in keys)
    rows = conn.execute(
        f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})", keys
    ).fetchall()
    conn.close()
    values = {row["key"]: row["value"] for row in rows}
    return {
        "version": values.get(UPDATE_VERSION_KEY, ""),
        "url": values.get(UPDATE_URL_KEY, ""),
        "message": values.get(UPDATE_MESSAGE_KEY, "새 버전이 있습니다."),
    }


def set_update_notice(version: str, url: str, message: str) -> None:
    init_settings_table()
    set_setting(UPDATE_VERSION_KEY, version.strip())
    set_setting(UPDATE_URL_KEY, url.strip())
    set_setting(UPDATE_MESSAGE_KEY, message.strip())


def get_max_concurrent_sessions(default: int) -> int:
    """운영자가 저장한 값이 있으면 그걸, 없으면(최초 배포 등) default를 반환."""
    init_settings_table()
    raw = get_setting(MAX_CONCURRENT_SESSIONS_KEY, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def set_max_concurrent_sessions(value: int) -> None:
    init_settings_table()
    set_setting(MAX_CONCURRENT_SESSIONS_KEY, str(int(value)))


def save_blob_setting(key: str, raw_bytes: bytes) -> None:
    """임의 바이너리(pickle 등)를 base64로 인코딩해 TEXT 컬럼에 저장.
    로컬 파일(saved_filters.pkl 등)이 Streamlit Cloud 재배포마다 사라지는 문제의
    영속화 대책(2026-08-22) — 로컬 파일은 그대로 쓰되, 여기에도 미러링해둔다."""
    import base64

    init_settings_table()
    set_setting(key, base64.b64encode(raw_bytes).decode("ascii"))


def load_blob_setting(key: str) -> bytes | None:
    import base64

    init_settings_table()
    raw = get_setting(key, "")
    if not raw:
        return None
    return base64.b64decode(raw)
