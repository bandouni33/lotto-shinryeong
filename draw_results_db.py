"""당첨번호(회차별 6개+보너스) — Turso DB 저장.

2026-09-01: "로또최근당첨내역.xlsb"를 관리자가 로컬에서 손으로 고치고
git 커밋·푸시해야만 반영되던 걸(주간 완전자동화의 마지막 걸림돌), 관리자
대시보드에서 번호만 입력하면 즉시 반영되는 이 테이블로 옮긴다. pyxlsb는
읽기 전용이라 기존 xlsb 파일에 자동으로 다시 써넣을 방법이 없어서(이번
세션에 이미 확인됨), xlsb는 "과거 이력을 1회 이관해오는 시드 데이터"로만
쓰고, 이후 신규 회차는 전부 이 테이블에만 쌓인다.
"""

from __future__ import annotations

import db_turso

_TABLE_READY = False


def _connect():
    return db_turso.connect()


def init_draw_results_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS draw_results (
            draw_round INTEGER PRIMARY KEY,
            num1 INTEGER NOT NULL,
            num2 INTEGER NOT NULL,
            num3 INTEGER NOT NULL,
            num4 INTEGER NOT NULL,
            num5 INTEGER NOT NULL,
            num6 INTEGER NOT NULL,
            bonus INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    _TABLE_READY = True


def upsert_draw_result(draw_round: int, numbers: list[int], bonus: int) -> None:
    """회차 하나를 등록/수정한다. numbers는 정확히 6개, 오름차순 여부는
    호출부에서 정렬해서 넘겨야 한다(여기서도 방어적으로 한 번 더 정렬)."""
    from datetime import datetime

    nums = sorted(int(n) for n in numbers)
    if len(nums) != 6 or len(set(nums)) != 6 or any(n < 1 or n > 45 for n in nums):
        raise ValueError("번호는 1~45 범위의 서로 다른 6개여야 합니다.")
    bonus = int(bonus)
    if bonus < 1 or bonus > 45:
        raise ValueError("보너스 번호는 1~45 범위여야 합니다.")

    conn = _connect()
    conn.execute(
        """
        INSERT INTO draw_results
            (draw_round, num1, num2, num3, num4, num5, num6, bonus, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(draw_round) DO UPDATE SET
            num1 = excluded.num1, num2 = excluded.num2, num3 = excluded.num3,
            num4 = excluded.num4, num5 = excluded.num5, num6 = excluded.num6,
            bonus = excluded.bonus, updated_at = excluded.updated_at
        """,
        (int(draw_round), *nums, bonus, datetime.now().isoformat()),
    )
    conn.commit()


def get_all_draw_results() -> list[dict]:
    """전체 회차를 draw_round 내림차순(최신 먼저)으로 반환 — 기존
    load_lotto_data()가 xlsb에서 만들던 순서와 동일하게 맞춘다."""
    conn = _connect()
    import sqlite3

    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT draw_round, num1, num2, num3, num4, num5, num6, bonus
        FROM draw_results
        ORDER BY draw_round DESC
        """
    ).fetchall()
    return [
        {
            "draw_round": int(r["draw_round"]),
            "numbers": [
                int(r["num1"]), int(r["num2"]), int(r["num3"]),
                int(r["num4"]), int(r["num5"]), int(r["num6"]),
            ],
            "bonus": int(r["bonus"]),
        }
        for r in rows
    ]


def get_draw_results_count() -> int:
    conn = _connect()
    row = conn.execute("SELECT COUNT(*) FROM draw_results").fetchone()
    return int(row[0]) if row else 0


def get_latest_draw_round() -> int | None:
    conn = _connect()
    row = conn.execute("SELECT MAX(draw_round) FROM draw_results").fetchone()
    val = row[0] if row else None
    return int(val) if val is not None else None


# 2026-09-01: 사용자가 "동행복권 사이트에서 왜 직접 못 가져오냐" 질문 — 실제로
# 가능한 걸 확인했다. 동행복권 사이트(SPA로 리뉴얼됨) 로또6/45 소개 페이지가
# 내부적으로 부르는 이 엔드포인트가 인증·세션 없이도 최신 회차 당첨번호를
# 그대로 JSON으로 돌려준다(브라우저 네트워크 탭에서 실측 확인, 2026-09-01
# 기준 정상 동작). 이걸로 "관리자가 매주 번호를 입력"할 필요 자체가 없어진다
# — 이 함수가 주기적으로 확인해서 새 회차가 나온 순간 자동으로 채워 넣는다.
_DHLOTTERY_LATEST_URL = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do"


def fetch_latest_from_dhlottery() -> dict | None:
    """동행복권 공식 사이트에서 가장 최근 회차 당첨번호를 가져온다.
    실패(네트워크 문제·응답 형식 변경 등)해도 예외를 던지지 않고 None을
    반환 — 이 기능이 죽어도 앱 전체(기존 xlsb/DB 데이터로 계속 동작)에는
    영향이 없어야 한다."""
    import requests

    try:
        resp = requests.get(_DHLOTTERY_LATEST_URL, timeout=8)
        resp.raise_for_status()
        item = resp.json()["data"]["list"][0]
        numbers = [
            int(item["tm1WnNo"]), int(item["tm2WnNo"]), int(item["tm3WnNo"]),
            int(item["tm4WnNo"]), int(item["tm5WnNo"]), int(item["tm6WnNo"]),
        ]
        return {
            "draw_round": int(item["ltEpsd"]),
            "numbers": numbers,
            "bonus": int(item["bnsWnNo"]),
        }
    except Exception:
        return None


def sync_latest_from_dhlottery() -> int | None:
    """DB의 최신 회차보다 동행복권 사이트의 최신 회차가 더 크면(=새로 추첨됨)
    자동으로 채워 넣는다. 새로 채운 회차 번호를 반환(없으면 None) — 실패해도
    조용히 넘어간다(위 fetch_latest_from_dhlottery와 동일한 이유)."""
    try:
        latest_remote = fetch_latest_from_dhlottery()
        if latest_remote is None:
            return None
        latest_local = get_latest_draw_round()
        if latest_local is not None and latest_remote["draw_round"] <= latest_local:
            return None
        upsert_draw_result(
            latest_remote["draw_round"], latest_remote["numbers"], latest_remote["bonus"]
        )
        return latest_remote["draw_round"]
    except Exception:
        return None


def get_cache_key() -> tuple[int, int]:
    """load_lotto_data() 캐시 무효화용 — (전체 건수, 최신 회차)가 바뀌면
    새 데이터로 간주한다(신규 등록·수정 둘 다 최신 회차나 건수를 움직이므로
    충분히 민감한 키)."""
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(draw_round), 0) FROM draw_results"
    ).fetchone()
    return (int(row[0]), int(row[1])) if row else (0, 0)
