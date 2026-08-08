"""관리자 비밀번호 무차별 대입 방어 — 프로세스 전역 상태(모든 세션 공유).

user_page.py는 st.Page로 로드되어 매 rerun마다 새 모듈 네임스페이스로 실행되므로,
그 안의 top-level 변수는 rerun 간에 유지되지 않는다. 반면 이 모듈은 일반적인
Python import로 로드되어 sys.modules에 캐시되므로, 아래 _state는 서버 프로세스가
살아있는 한(=모든 세션이 공유) 유지된다.
"""

from __future__ import annotations

import time

_state = {"fail_count": 0, "locked_until": 0.0}


def seconds_locked_remaining() -> float:
    return _state["locked_until"] - time.time()


def record_failure(max_attempts: int = 5, lockout_seconds: int = 300) -> int:
    """실패 기록. max_attempts 도달 시 lockout_seconds 만큼 잠그고 카운트를 리셋한다."""
    _state["fail_count"] += 1
    if _state["fail_count"] >= max_attempts:
        _state["locked_until"] = time.time() + lockout_seconds
        _state["fail_count"] = 0
    return _state["fail_count"]


def record_success() -> None:
    _state["fail_count"] = 0
    _state["locked_until"] = 0.0
