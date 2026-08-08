"""앱 전역 설정(키-값) — Turso 저장. 업데이트 안내 배너 등 관리자가 코드 배포 없이 바꿀 값."""

from __future__ import annotations

import db_turso

UPDATE_VERSION_KEY = "latest_app_version"
UPDATE_URL_KEY = "update_url"
UPDATE_MESSAGE_KEY = "update_message"


def _connect():
    return db_turso.connect()


def init_settings_table() -> None:
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
    """{'version': str, 'url': str, 'message': str} — version이 비어있으면 배너 비활성."""
    init_settings_table()
    return {
        "version": get_setting(UPDATE_VERSION_KEY, ""),
        "url": get_setting(UPDATE_URL_KEY, ""),
        "message": get_setting(UPDATE_MESSAGE_KEY, "새 버전이 있습니다."),
    }


def set_update_notice(version: str, url: str, message: str) -> None:
    init_settings_table()
    set_setting(UPDATE_VERSION_KEY, version.strip())
    set_setting(UPDATE_URL_KEY, url.strip())
    set_setting(UPDATE_MESSAGE_KEY, message.strip())
