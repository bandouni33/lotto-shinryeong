"""관리자 비밀번호 무차별 대입 방어 — 프로세스 전역 상태(모든 세션 공유).

user_page.py는 st.Page로 로드되어 매 rerun마다 새 모듈 네임스페이스로 실행되므로,
그 안의 top-level 변수는 rerun 간에 유지되지 않는다. 반면 이 모듈은 일반적인
Python import로 로드되어 sys.modules에 캐시되므로, 아래 _state는 서버 프로세스가
살아있는 한(=모든 세션이 공유) 유지된다.
"""

from __future__ import annotations

import time

_state = {"fail_count": 0, "locked_until": 0.0}
_download_state = {"timestamps": []}


def seconds_locked_remaining() -> float:
    return _state["locked_until"] - time.time()


def _log_security_event(event_type: str, detail: str) -> None:
    """침입 흔적 기록 — 실패해도 로그인 잠금 등 실제 방어 동작에 영향 주면 안 되므로
    항상 무시 가능한 실패로 처리한다."""
    try:
        import security_log

        security_log.log_event(event_type, detail)
    except Exception:
        pass


def record_failure(max_attempts: int = 5, lockout_seconds: int = 300) -> int:
    """실패 기록. max_attempts 도달 시 lockout_seconds 만큼 잠그고 카운트를 리셋한다."""
    _state["fail_count"] += 1
    _log_security_event("admin_login_fail", f"관리자 비밀번호 오류 (연속 {_state['fail_count']}회째)")
    if _state["fail_count"] >= max_attempts:
        _state["locked_until"] = time.time() + lockout_seconds
        _log_security_event("admin_lockout", f"{max_attempts}회 연속 실패로 {lockout_seconds}초 잠금")
        _state["fail_count"] = 0
    return _state["fail_count"]


def record_success() -> None:
    _state["fail_count"] = 0
    _state["locked_until"] = 0.0


# ────────────────────────────────────────────────
# 조합 대량 다운로드 rate limit — 관리자 비밀번호를 뚫었거나 세션을 탈취한 뒤
# 스크립트로 조합저장본을 반복 요청해 긁어가는 걸 막기 위한 창구.
# 로그인 잠금과 동일하게 프로세스 전역(모든 세션 공유) 상태로 관리한다.
# ────────────────────────────────────────────────


def _prune_download_window(window_seconds: int) -> None:
    now = time.time()
    _download_state["timestamps"] = [
        t for t in _download_state["timestamps"] if now - t < window_seconds
    ]


def downloads_remaining(max_downloads: int, window_seconds: int) -> int:
    """지금 이 창(window_seconds) 안에서 몇 번 더 다운로드할 수 있는지."""
    _prune_download_window(window_seconds)
    return max(0, max_downloads - len(_download_state["timestamps"]))


def seconds_until_download_slot(window_seconds: int) -> float:
    """다음 다운로드가 허용되기까지 남은 대기 시간(초). 이미 허용 중이면 0."""
    _prune_download_window(window_seconds)
    if not _download_state["timestamps"]:
        return 0.0
    return max(0.0, window_seconds - (time.time() - _download_state["timestamps"][0]))


def record_download() -> None:
    _download_state["timestamps"].append(time.time())
