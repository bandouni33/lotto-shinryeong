"""7단계 — 출시전 체크리스트 1번: 정식 출시 때 회원 적립금을 신규가입 보너스(500P)로 맞추는 1회성 스크립트.

[대상 조건 — 2026-10-11 변경(사용자 결정)] **실결제 기록이 없는 모든 회원**(탈퇴 회원 제외)을 500P 로.
아래 10-02·10-09 설명은 '실결제 판정' 규칙으로 그대로 유효하다(그 회원들은 제외). 정확한 조건은 select_targets.

[대상 조건 — 2026-10-02 확정] **Mock 충전(pg:mock:) 기록이 있는 회원**이면서
**실결제 기록(pg:toss: / pg:gplay:)이 없는 회원**만 리셋한다. 2026-09-20 재검토에서
"잔액 != 신규가입 보너스"로 대상을 잡으면 안 된다는 것이 확인됐다 — 그중 대다수는
Mock 충전과 무관하게 가입 보너스를 정상적으로 써서 잔액이 줄어든 일반 사용자라,
그들을 보너스로 "되돌리면" 오히려 부당하게 다시 채워준다(당시 잔액≠500P 96명 중
92명이 그런 경우였다. 라이브 실측 2026-10-02: 진짜 대상은 105·61 두 명).

[2026-10-09 보완] 라이선스 테스터(테스터 23명 전원)의 구글 결제는 실제 청구가 없는 **테스트 결제**인데도
pg:gplay: 기록을 남긴다 — 예전 조건으로는 결제 시험 기간에 테스트 결제를 한 테스터가 "실결제자"로 빠져
테스트 적립금이 그대로 남았다. 이제 실결제 판정은 gplay_purchases.is_test=0 인 구글 결제와 토스 결제만이고,
**테스트 결제만 한 회원도 초기화 대상**이다(Mock 기록이 없어도). gplay_purchases 에 행이 없는 옛 pg:gplay:
기록은 테스트 여부를 알 수 없어 안전하게 실결제로 본다.

[출시 순서 — 2026-10-09 확정] ① Play 콘솔 라이선스 테스트를 본인만 든 새 목록으로 교체 → ② 이 스크립트
미리보기 → --confirm → ③ 결제 스위치 켜기·테스트 충전 끄기(wallet_ui). ①을 먼저 하는 이유: 그 뒤로는
테스터의 결제가 실제 결제가 되므로, 초기화 이후 새로 생기는 테스트 적립금이 없다.

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
REAL_PAYMENT_PREFIXES = ("pg:toss:", "pg:gplay:")  # 참고용 — 구글은 is_test 로 다시 가른다(select_targets)
MOCK_CHARGE_PREFIX = "pg:mock:"


def _members_with_prefix(conn, prefix: str) -> set[int]:
    rows = conn.execute(
        "SELECT DISTINCT member_id FROM pg_charges WHERE pg_ref_id LIKE ?",
        (prefix + "%",),
    ).fetchall()
    return {int(r["member_id"]) for r in rows}


def _gplay_members(conn) -> tuple[set[int], set[int]]:
    """(실결제 구글 회원, 테스트 결제만 있는 구글 회원). 행 없는 옛 pg:gplay: 기록은 실결제로 본다."""
    real: set[int] = set()
    test: set[int] = set()
    tracked: set[str] = set()
    try:
        for r in conn.execute("SELECT purchase_token, member_id, is_test FROM gplay_purchases").fetchall():
            tracked.add(wallet_db.gplay_ref(r["purchase_token"]))
            (test if int(r["is_test"] or 0) else real).add(int(r["member_id"]))
    except Exception:
        pass  # 표가 없는 옛 DB — 아래 pg_charges 기준만 남는다
    for r in conn.execute(
        "SELECT member_id, pg_ref_id FROM pg_charges WHERE pg_ref_id LIKE ? AND pg_ref_id NOT LIKE ?",
        (wallet_db.GPLAY_REF_PREFIX + "%", wallet_db.GPLAY_VOID_REF_PREFIX + "%"),
    ).fetchall():
        if r["pg_ref_id"] not in tracked:
            real.add(int(r["member_id"]))
    return real, test - real


def select_targets(conn, *, verbose: bool = True) -> list[tuple[int, int]]:
    """초기화 대상 [(member_id, 현재 잔액)].

    2026-10-11(사용자 결정 — "정식 출시되면 기존·신규 이용자 모두 적립금 500P"): **실결제 기록이 없는
    모든 회원**의 잔액을 신규가입 보너스(500P)로 맞춘다 — 보너스를 써서 줄어든 회원은 다시 채워지고,
    500P 를 넘는 회원(테스트 충전·테스트 결제·운영 지급 등)은 500P 로 내려간다. 예전(10-02~10-09)엔
    테스트 충전·테스트 결제 기록이 있는 회원만 골랐다.
    제외: ① 실결제 회원(토스, 구글·애플 is_test=0, 테스트 여부를 모르는 옛 pg:gplay: 기록) — 산 적립금을
    건드리지 않는다 ② 탈퇴(익명화) 회원 ③ 이미 500P 인 회원."""
    log = print if verbose else (lambda *a, **k: None)
    mock_members = _members_with_prefix(conn, MOCK_CHARGE_PREFIX)
    gplay_real, gplay_test_only = _gplay_members(conn)
    protected = _members_with_prefix(conn, "pg:toss:") | gplay_real
    if protected:
        log(f"실결제(토스·구글·애플) 기록이 있는 회원 {len(protected)}명은 자동 제외: {sorted(protected)}")
    log(f"참고: Mock 충전 기록 {len(mock_members)}명, 테스트 결제만 {len(gplay_test_only)}명(둘 다 대상에 포함)")

    rows = conn.execute(
        """
        SELECT w.member_id, w.balance FROM wallets w
        JOIN members m ON m.id = w.member_id
        WHERE w.balance != ? AND m.deleted_at IS NULL AND m.provider != 'deleted'
        """,
        (wallet_db.SIGNUP_BONUS,),
    ).fetchall()
    targets = [
        (int(r["member_id"]), int(r["balance"]))
        for r in sorted(rows, key=lambda r: int(r["member_id"]))
        if int(r["member_id"]) not in protected
    ]
    up = sum(1 for _, b in targets if b < wallet_db.SIGNUP_BONUS)
    log(
        f"대상 {len(targets)}명 — {wallet_db.SIGNUP_BONUS}P 미만이라 채워지는 회원 {up}명, "
        f"넘어서 내려가는 회원 {len(targets) - up}명(실결제·탈퇴·이미 {wallet_db.SIGNUP_BONUS}P 회원 제외)."
    )
    return targets


def main() -> None:
    confirm = "--confirm" in sys.argv

    wallet_db.init_wallet_tables()
    conn = wallet_db._connect()

    targets = select_targets(conn)

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
