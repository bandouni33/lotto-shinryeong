"""자동구매 — 관리자 저장 6조합 배포·SMS·적립금 차감."""

from __future__ import annotations

import uuid

from marketing_db import (
    InsufficientCombinationsError,
    allocate_lotto_combinations,
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
