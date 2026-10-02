"""7단계 — 출시전 체크리스트 1번: Mock 결제로 충전됐던 테스터 잔액을
신규가입 보너스로 되돌리는 1회성 스크립트.

[대상 조건 — 2026-10-02 확정] **Mock 충전(pg:mock:) 기록이 있는 회원**이면서
**실결제 기록(pg:toss: / pg:gplay:)이 없는 회원**만 리셋한다. 2026-09-20 재검토에서
"잔액 != 신규가입 보너스"로 대상을 잡으면 안 된다는 것이 확인됐다 — 그중 대다수는
Mock 충전과 무관하게 가입 보너스를 정상적으로 써서 잔액이 줄어든 일반 사용자라,
그들을 보너스로 "되돌리면" 오히려 부당하게 다시 채워준다(당시 잔액≠500P 96명 중
92명이 그런 경우였다. 라이브 실측 2026-10-02: 진짜 대상은 105·61 두 명).

[시점] 구글플레이 실결제 스위치(wallet_ui.IAP_CHARGE_ENABLED)를 켜기 **직전**.
스위치를 켜는 순간부터 pg:gplay: 기록이 실결제로 쌓이므로 그 전에 끝내야 한다.
실행 직전 check_real_toss_charges.py 또는 scratch/_live_reset_scope_check.py로
실결제 0건을 다시 확인할 것(대상 조건이 그 기록을 근거로 삼는다).

로그인 연결(guest_member_links, kakao oauth_hash 등)은 전혀 건드리지
않는다 — wallets.balance만 바꾸고, 변경 내역은 기존 관례대로
wallet_ledger에 감사기록(reason='pre_launch_balance_reset')으로 남긴다.

기본은 DRY-RUN이다(미리보기만, DB에 아무것도 안 씀). 실제로 반영하려면
--confirm 옵션을 붙여 다시 실행해야 한다. ref_id가 "리셋 날짜+회원id"라
같은 날 두 번 실행해도 이미 처리된 회원은 건너뛴다(멱등).

실행 방법 (프로젝트 루트에서):
    python reset_tester_balances.py            # 미리보기만 (안전)
    python reset_tester_balances.py --confirm  # 실제 반영
"""

from __future__ import annotations

import sys

import env_loader

env_loader.load_dotenv_file()

import wallet_db  # noqa: E402

_RESET_REASON = "pre_launch_balance_reset"


# 실결제로 들어온 결제 기록의 접두어 — 하나라도 있으면 리셋 대상에서 제외한다.
# 토스는 웹(PC) 카드결제, gplay는 네이티브 구글플레이 인앱결제로, 둘 다 실제 돈이
# 오간 기록이다(2026-10-02: IAP 스위치를 켜면 gplay가 쌓이기 시작하므로 함께 본다).
REAL_PAYMENT_PREFIXES = ("pg:toss:", "pg:gplay:")
MOCK_CHARGE_PREFIX = "pg:mock:"


def _members_with_prefix(conn, prefix: str) -> set[int]:
    rows = conn.execute(
        "SELECT DISTINCT member_id FROM pg_charges WHERE pg_ref_id LIKE ?",
        (prefix + "%",),
    ).fetchall()
    return {int(r["member_id"]) for r in rows}


def main() -> None:
    confirm = "--confirm" in sys.argv

    wallet_db.init_wallet_tables()
    conn = wallet_db._connect()

    mock_members = _members_with_prefix(conn, MOCK_CHARGE_PREFIX)
    protected: set[int] = set()
    for prefix in REAL_PAYMENT_PREFIXES:
        found = _members_with_prefix(conn, prefix)
        if found:
            print(f"실결제({prefix}) 기록이 있는 회원 {len(found)}명은 자동 제외: {sorted(found)}")
        protected |= found
    print(
        f"Mock 충전({MOCK_CHARGE_PREFIX}) 기록이 있는 회원 {len(mock_members)}명: "
        f"{sorted(mock_members)}"
    )

    rows = conn.execute(
        "SELECT member_id, balance FROM wallets WHERE balance != ?",
        (wallet_db.SIGNUP_BONUS,),
    ).fetchall()
    balances = {int(r["member_id"]): int(r["balance"]) for r in rows}

    # 대상 = Mock 충전 기록이 있고(리셋의 근거) 실결제 기록이 없으며, 잔액이 이미
    # 보너스와 다른 회원. 그 밖에 잔액이 다른 사람들(정상 사용자)은 건드리지 않는다.
    targets = [
        (member_id, balances[member_id])
        for member_id in sorted(mock_members)
        if member_id not in protected
        and balances.get(member_id, wallet_db.SIGNUP_BONUS) != wallet_db.SIGNUP_BONUS
    ]
    print(
        f"참고: 잔액이 보너스와 다른 회원은 {len(balances)}명인데, "
        f"그중 Mock 충전 기록이 있어 대상이 된 사람은 {len(targets)}명이다(나머지는 정상 사용·실결제자)."
    )

    print(f"\n리셋 대상: {len(targets)}명 (전체 → 신규가입 보너스 {wallet_db.SIGNUP_BONUS}P)\n")
    for member_id, balance in targets:
        print(
            f"  member_id={member_id}: {balance}P -> {wallet_db.SIGNUP_BONUS}P "
            f"(변화: {wallet_db.SIGNUP_BONUS - balance:+d}P)"
        )

    if not targets:
        print("리셋할 대상이 없습니다.")
        conn.close()
        return

    if not confirm:
        print("\n=== 미리보기만 실행했습니다 (DB에 아무것도 반영 안 됨) ===")
        print("위 내용이 맞으면 --confirm을 붙여 다시 실행하세요:")
        print("  python reset_tester_balances.py --confirm")
        conn.close()
        return

    from datetime import datetime

    reset_tag = datetime.now(wallet_db.KST).strftime("%Y%m%d")

    print("\n실제로 반영합니다...")
    ok, skipped, failed = 0, 0, 0
    for member_id, balance in targets:
        ref_id = f"reset:{reset_tag}:{member_id}"
        dup = conn.execute(
            "SELECT 1 FROM wallet_ledger WHERE ref_id = ?", (ref_id,)
        ).fetchone()
        if dup:
            print(f"  member_id={member_id}: 이미 처리됨(건너뜀)")
            skipped += 1
            continue

        now = wallet_db._now_iso()
        results = wallet_db._batch_execute(
            conn,
            [
                (
                    """
                    INSERT INTO wallet_ledger
                        (member_id, delta, balance_after, reason, ref_id, created_at)
                    SELECT ?, (? - balance), ?, ?, ?, ?
                    FROM wallets WHERE member_id = ?
                    """,
                    (
                        member_id,
                        wallet_db.SIGNUP_BONUS,
                        wallet_db.SIGNUP_BONUS,
                        _RESET_REASON,
                        ref_id,
                        now,
                        member_id,
                    ),
                ),
                (
                    """
                    UPDATE wallets SET balance = ?
                    WHERE member_id = ? AND EXISTS (
                        SELECT 1 FROM wallet_ledger WHERE ref_id = ?
                    )
                    """,
                    (wallet_db.SIGNUP_BONUS, member_id, ref_id),
                ),
            ],
        )
        conn.commit()
        ledger_inserted = results[0].rowcount if results else 0
        if ledger_inserted:
            print(f"  member_id={member_id}: 완료 ({balance}P -> {wallet_db.SIGNUP_BONUS}P)")
            ok += 1
        else:
            print(f"  member_id={member_id}: 실패(해당 지갑 없음?)")
            failed += 1

    conn.close()
    print(f"\n=== 완료: 성공 {ok} / 건너뜀 {skipped} / 실패 {failed} (전체 {len(targets)}명) ===")


if __name__ == "__main__":
    main()
