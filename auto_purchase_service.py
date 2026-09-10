"""자동구매 — 관리자 저장 6조합 배포·SMS·적립금 차감."""

from __future__ import annotations

import uuid

import streamlit as st

from marketing_db import (
    InsufficientCombinationsError,
    allocate_lotto_combinations_random_sequential,
    get_combination_count_by_draw,
    get_draw_extraction_stats,
    init_marketing_tables,
    release_lotto_combination_allocation,
)
from sms_sender import build_purchase_sms_message, dispatch_purchase_sms
from wallet_db import (
    calc_auto_cost,
    complete_auto_order,
    create_auto_order,
    deduct_points,
    fail_auto_order,
    get_balance,
    init_wallet_tables,
    refund_points,
)


def _next_draw_round() -> int:
    try:
        from lotto_stats import get_latest_draw_stats, load_lotto_data

        data = load_lotto_data()
        return int(get_latest_draw_stats(data)["draw_no"]) + 1
    except Exception:
        stats = get_draw_extraction_stats(limit=1)
        if stats:
            return int(stats[0]["draw_round"]) + 1
        return 1234


NEXT_DRAW_POOL_BANNER = "다음회차 조합생성이 완료된 후 이용 바랍니다"


class NextDrawPoolNotReadyError(Exception):
    """메인 최신 회차+1 에 관리자 저장 조합이 없음 (이전 회차 배포 방지)."""

    def __init__(self, draw_round: int, message: str = NEXT_DRAW_POOL_BANNER):
        self.draw_round = int(draw_round)
        self.message = message
        super().__init__(message)


@st.cache_data(ttl=60, show_spinner=False)
def check_next_draw_pool_ready() -> dict:
    """
    추첨 완료된 최신 회차 N → 배포 대상은 N+1.
    N+1 회차 조합이 DB에 없으면 배포 불가.

    자동구매 페이지가 렌더될 때마다(위젯 하나만 건드려도 Streamlit이 전체
    스크립트를 다시 실행) 이 함수가 매번 불려서, 캐싱 없이 매번 회차 풀
    COUNT(*) 쿼리를 새로 날리고 있었다 — 한 회차 풀이 수천 건이라 페이지를
    잠깐 조작하는 것만으로도 수만~수십만 행을 태워, Turso 무료 요금제
    쓰기/읽기 한도를 순식간에 소진시킨 주범이었다(2026-08-23). 60초 안의
    반복 호출은 이 캐시를 재사용한다 — 실제 배정(allocate_lotto_combinations_
    random_sequential)은 이 캐시와 별개로 매번 실시간 원자적 체크를 하므로,
    이 게이트 함수가 살짝 오래된 값을 반환해도 실제 조합이 중복 배정되는
    일은 없다.
    """
    init_marketing_tables()
    from marketing_db import ensure_marketing_pool_seeds

    ensure_marketing_pool_seeds()
    draw_round = _next_draw_round()
    total = get_combination_count_by_draw(draw_round)
    if total < 1:
        return {
            "ok": False,
            "draw_round": draw_round,
            "message": NEXT_DRAW_POOL_BANNER,
        }
    return {"ok": True, "draw_round": draw_round, "pool_count": total}


def process_auto_purchase(
    member_id: int,
    quantity: int,
    purchase_method: str,
    phone: str,
    sms_days: list[str] | None = None,
) -> dict:
    """
    1) 잔액 확인 → 2) 관리자 저장 미배포 조합 우선순위 배정
    → 3) SMS 큐 → 4) 적립금 차감.
    """
    init_wallet_tables()
    init_marketing_tables()

    pool = check_next_draw_pool_ready()
    if not pool["ok"]:
        return {
            "ok": False,
            "error": "next_draw_pool_missing",
            "message": pool["message"],
            "draw_round": pool["draw_round"],
        }

    # 2026-08-29: 수신 번호 입력칸을 화면에서 없앴다(당분간 SMS 미발송 확정,
    # 알리고 미연동) — 더 이상 phone을 필수로 요구하지 않는다. dispatch_purchase_sms는
    # SMS_ENABLED=False일 때 실제 발송 없이 로그만 남기므로 빈 값이어도 안전하다.
    phone = str(phone).strip()

    cost = calc_auto_cost(quantity)
    if get_balance(member_id) < cost:
        return {"ok": False, "error": "insufficient_balance", "cost": cost}

    purchase_type = "정기구독" if purchase_method == "월간구독" else "일반구매"
    sms_days_str = ",".join(sms_days or [])
    ref = f"auto:order:{member_id}:{uuid.uuid4().hex[:12]}"
    order_id = create_auto_order(
        member_id, quantity, purchase_type, phone, sms_days_str, ref
    )

    allocated_ids: list[int] = []
    try:
        draw_round = _next_draw_round()
        allocated = allocate_lotto_combinations_random_sequential(
            draw_round, int(quantity), order_id
        )
        allocated_ids = [item["id"] for item in allocated]
        combo_count = len(allocated)

        sms_message = build_purchase_sms_message(draw_round, purchase_type, allocated)
        sms_id = dispatch_purchase_sms(phone, purchase_type, sms_message)

        if not deduct_points(member_id, cost, f"auto:{quantity}qty", ref):
            release_lotto_combination_allocation(allocated_ids)
            fail_auto_order(order_id)
            return {"ok": False, "error": "deduct_failed", "order_id": order_id}

        try:
            complete_auto_order(order_id, sms_id, draw_round, combo_count)
        except Exception:
            # 2026-09-10(사용자 지시): 차감은 이미 성공했는데 주문 완료 처리가
            # 예외로 끊기면 "조합 배정은 취소되고 적립금만 빠진" 상태가 된다 —
            # 분쟁 위험이 커서 여기서 즉시 환불하고 배정도 되돌린다.
            refund_points(member_id, cost, f"auto:refund:{quantity}qty", f"{ref}:refund")
            release_lotto_combination_allocation(allocated_ids)
            fail_auto_order(order_id)
            return {"ok": False, "error": "complete_failed", "order_id": order_id, "refunded": True}
        return {
            "ok": True,
            "order_id": order_id,
            "combo_count": combo_count,
            "draw_round": draw_round,
            "cost": cost,
            "sms_id": sms_id,
            "combo_ids": allocated_ids,
            "allocated": allocated,
            "purchase_type": purchase_type,
            "purchase_method": purchase_method,
            "sms_days": list(sms_days or []),
            "phone": phone,
            "rotated": any(item.get("rotated") for item in allocated),
        }
    except InsufficientCombinationsError as exc:
        fail_auto_order(order_id)
        return {
            "ok": False,
            "error": "insufficient_combinations",
            "order_id": order_id,
            "draw_round": exc.draw_round,
            "requested": exc.requested,
            "available": exc.available,
        }
    except Exception:
        if allocated_ids:
            release_lotto_combination_allocation(allocated_ids)
        fail_auto_order(order_id)
        raise
