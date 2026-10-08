"""원격 DB 조회 결과를 프로세스 안에서 잠깐(몇 초~몇 분) 재사용하는 공용 캐시.

2026-10-08(운영 실측 — 로딩 시간): Cloud 서버에서 Turso 왕복 1회가 평균 약 100ms(최대 260ms)이고,
화면 한 번에 8~12회씩 순차 왕복해 서버 처리의 90% 이상이 DB 대기였다(render_timing). 그중
관리자 설정·회차 키·이벤트 회차·주간 통계처럼 "자주 안 바뀌는데 매 화면 읽는 값"만 여기서
짧게 재사용한다. 회원·지갑·로그인처럼 즉시 정확해야 하는 값은 이 캐시를 쓰지 않는다.

- 키에는 지금 쓰는 DB 연결 함수(db_turso.connect)의 정체를 함께 넣는다 — 테스트가 격리 DB로
  바꿔 끼우면(tests/_db_isolation.py) 자동으로 다른 칸을 써서 운영 값과 섞이지 않는다.
- 값을 쓰는 쪽(set_setting 등)은 invalidate(prefix)로 바로 비운다(같은 프로세스 안에서는 즉시 반영).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

_LOCK = threading.Lock()
_STORE: dict[tuple, tuple[float, Any]] = {}


def _db_identity() -> int:
    try:
        import db_turso

        return id(db_turso.connect)
    except Exception:
        return 0


def cached(name: str, ttl_seconds: float, loader: Callable[[], Any], *args: Any) -> Any:
    """name+args 로 ttl_seconds 동안 loader() 결과를 재사용한다. loader 가 예외를 내면 저장하지 않고 그대로 올린다."""
    key = (_db_identity(), name, args)
    now = time.monotonic()
    with _LOCK:
        hit = _STORE.get(key)
        if hit is not None and now - hit[0] < ttl_seconds:
            return hit[1]
    value = loader()
    with _LOCK:
        _STORE[key] = (time.monotonic(), value)
    return value


def invalidate(prefix: str = "") -> None:
    """name 이 prefix 로 시작하는 칸을 모두 비운다(빈 문자열이면 전부)."""
    with _LOCK:
        for key in [k for k in _STORE if str(k[1]).startswith(prefix)]:
            _STORE.pop(key, None)
