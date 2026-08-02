"""자동구매 — 관리자 저장 6조합 배포·SMS·적립금 차감."""

from __future__ import annotations

import uuid

from marketing_db import (
    InsufficientCombinationsError,
    allocate_lotto_combinations,
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


def check_next_draw_pool_ready() -> dict:
    """
    추첨 완료된 최신 회차 N → 배포 대상은 N+1.
    N+1 회차 조합이 DB에 없으면 배포 불가.
    """
    init_marketing_tables()
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

    phone = str(phone).strip()
    if not phone:
        return {"ok": False, "error": "phone_required"}

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
        allocated = allocate_lotto_combinations(draw_round, int(quantity), order_id)
        allocated_ids = [item["id"] for item in allocated]
        combo_count = len(allocated)

        sms_message = build_purchase_sms_message(draw_round, purchase_type, allocated)
        sms_id = dispatch_purchase_sms(phone, purchase_type, sms_message)

        if not deduct_points(member_id, cost, f"auto:{quantity}qty", ref):
            release_lotto_combination_allocation(allocated_ids)
            fail_auto_order(order_id)
            return {"ok": False, "error": "deduct_failed", "order_id": order_id}

        complete_auto_order(order_id, sms_id, draw_round, combo_count)
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
