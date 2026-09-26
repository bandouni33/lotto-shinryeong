"""다이얼로그 열기·재개의 **단일 기준점** (2026-09-26).

왜 필요한가
  로그인이 필요한 버튼은 "로그인을 마친 뒤 이 창을 다시 열어라"라는 의도를 resume
  이름으로 남기는데, 그 이름→동작 매핑이 세 곳에 흩어져 있었다:
    ① `wallet_ui._resume_after_auth()`의 if/elif 사슬(11개)
    ② `user_scope._LOGOUT_EXACT_KEYS`(로그아웃 시 지울 세션키 손목록)
    ③ `wallet_ui._PN_TRIGGER_FLAGS`(적립금 안내창 X닫기 시 함께 지울 플래그)
  그래서 한쪽만 고치면 조용히 재개가 안 되고(실제 사고: 고급필터 구독창
  `af_show_subscribe`가 ①에 없어 로그인 후 창이 열리지 않았다 — 2026-09-26 보완),
  반대로 아무도 호출하지 않는 이름이 남아 죽은 분기가 쌓였다
  (`af_show_step1_points`·`af_show_step2_points`: 호출부도 소비부도 없어 제거).

규칙 — `tests/test_dialog_registry.py`가 강제한다
  1. 새 다이얼로그를 추가할 때는 **이 파일에만** 항목을 추가한다.
  2. 화면은 세션 플래그를 쓸 때 `flag_key(name)`을, 로그인 재개 요청에는
     `DIALOGS[name].name`을 쓴다(문자열 리터럴을 새로 만들지 않는다).
  3. spec에 적은 `consumer`·`resume_caller` 파일이 실제로 그 이름/플래그를 쓰고
     있어야 한다 — 어긋나면 테스트가 실패한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DialogSpec:
    """다이얼로그 하나의 계약."""

    name: str
    """resume 파라미터로 오갔다 오는 이름(로그인 재개의 키)."""
    flag: str
    """열림/재개 상태로 쓰는 session_state 키."""
    data: tuple[tuple[str, str], ...] = ()
    """(세션 키, resume_data 키) — 로그인 왕복에서 함께 넘어와야 하는 값."""
    consumer: str = ""
    """이 플래그를 읽어 실제로 창을 띄우는 파일(없으면 죽은 항목)."""
    resume_caller: str = ""
    """resume=이름으로 로그인 재개를 요청하는 파일. 빈 값이면 '재개 요청 없음'이
    정상인 경우(페이지 전체 로그인 게이트를 이미 통과한 뒤에만 열리는 창 등)."""
    points_notice_trigger: bool = False
    """적립금 안내창을 X로 닫았을 때 함께 지워야 하는 플래그인지."""
    note: str = ""


DIALOGS: dict[str, DialogSpec] = {
    "open_thunder_dialog": DialogSpec(
        name="open_thunder_dialog",
        flag="open_thunder_dialog",
        data=(("open_thunder_dialog_games", "games"),),
        consumer="page_thunder.py",
        resume_caller="page_thunder.py",
        points_notice_trigger=True,
    ),
    "open_hedge_dialog": DialogSpec(
        name="open_hedge_dialog",
        flag="open_hedge_dialog",
        data=(("hedge_pending_lines", "lines"), ("hedge_pending_count", "count")),
        consumer="page_hedge.py",
        resume_caller="page_hedge.py",
        points_notice_trigger=True,
    ),
    "open_hedge_qr_scan": DialogSpec(
        name="open_hedge_qr_scan",
        flag="hedge_qr_request",
        consumer="page_hedge.py",
        resume_caller="page_hedge.py",
        note="QR 스캐너 트리거 — 페이지가 한 번 집어가고 스스로 지운다.",
    ),
    "auto_show_points": DialogSpec(
        name="auto_show_points",
        flag="auto_show_points",
        consumer="page_auto.py",
        resume_caller="page_auto.py",
        points_notice_trigger=True,
    ),
    "af_show_subscribe": DialogSpec(
        name="af_show_subscribe",
        flag="af_show_subscribe",
        consumer="admin_filter.py",
        resume_caller="admin_filter.py",
        note="2026-09-26 누락 보완 — 이 항목이 없어서 로그인 후 구독창이 안 열렸다.",
    ),
    "my_info_dialog": DialogSpec(
        name="my_info_dialog",
        flag="my_info_dialog_open",
        consumer="wallet_ui.py",
        resume_caller="wallet_ui.py",
    ),
    "wallet_show_charge": DialogSpec(
        name="wallet_show_charge",
        flag="wallet_show_charge",
        consumer="wallet_ui.py",
        note="내정보 안에서만 열린다(이미 로그인 상태) → 재개 요청 없음이 정상.",
    ),
    "open_tarot_dialog": DialogSpec(
        name="open_tarot_dialog",
        flag="open_tarot_dialog",
        consumer="tarot/tarot_page.py",
        points_notice_trigger=True,
        note=(
            "타로 페이지 전체가 로그인 게이트를 통과한 뒤에만 도달한다 → 재개 요청 없음. "
            "2026-09-26 실기기 신고 대응: 적립금 안내창을 여는 화면인데 points_notice_trigger가 "
            "빠져 있어 X로 닫아도 플래그가 남아 창이 곧바로 다시 떴다(자동구매는 지워짐) — "
            "안내창을 여는 네 화면은 전부 여기에 등록한다."
        ),
    ),
}


def names() -> tuple[str, ...]:
    """등록된 재개 이름 전체(테스트·문서가 이걸 기준으로 검사한다)."""
    return tuple(DIALOGS)


def flag_key(name: str) -> str:
    """이 다이얼로그의 session_state 키 — 화면 코드는 이 함수만 쓴다."""
    return spec(name).flag


def spec(name: str) -> DialogSpec:
    try:
        return DIALOGS[name]
    except KeyError:
        raise KeyError(
            f"등록되지 않은 다이얼로그 이름: {name!r} — dialog_registry.DIALOGS에 먼저 추가할 것"
        ) from None


def apply(name: str | None, data: dict | None = None) -> bool:
    """로그인을 마친 직후 재개 의도를 실제 상태로 바꾼다(예전 _resume_after_auth 몫).

    등록되지 않은 이름이면 아무 것도 하지 않고 False — 세션에 남은 낡은 resume으로
    엉뚱한 창이 열리는 사고를 막는다(2026-09-12 묵은 resume 사고와 같은 취지)."""
    if not name or name not in DIALOGS:
        return False
    target = DIALOGS[name]
    st_state = _session_state()
    if st_state is None:
        return False
    st_state[target.flag] = True
    payload = data or {}
    for session_key, data_key in target.data:
        if data_key in payload:
            st_state[session_key] = payload[data_key]
    return True


def logout_keys() -> frozenset[str]:
    """로그아웃 시 함께 지워야 하는 세션키 — 플래그 + 재개 데이터 키 전부.

    user_scope._LOGOUT_EXACT_KEYS가 이 값을 합쳐 쓴다(손목록을 따로 관리하지 않는다)."""
    keys: set[str] = set()
    for target in DIALOGS.values():
        keys.add(target.flag)
        keys.update(session_key for session_key, _ in target.data)
    return frozenset(keys)


def points_notice_trigger_flags() -> tuple[str, ...]:
    """적립금 안내창을 X로 닫았을 때 함께 지워야 하는 플래그들."""
    return tuple(target.flag for target in DIALOGS.values() if target.points_notice_trigger)


def _session_state():
    """streamlit을 쓰는 곳에서만 import(이 모듈은 테스트·문서에서도 읽히므로
    streamlit이 없는 환경에서 import 자체가 실패하면 안 된다)."""
    try:
        import streamlit as st
    except Exception:
        return None
    return st.session_state
