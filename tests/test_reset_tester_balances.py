# -*- coding: utf-8 -*-
"""출시 전 적립금 초기화 대상 선정(reset_tester_balances.select_targets) — 2026-10-09, 10-11 정책 변경.

2026-10-11(사용자 결정): 정식 출시 때 **실결제 없는 모든 회원을 500P** 로 맞춘다(S6·S9 가 그 변경).
  S1 Mock 충전만 한 회원 → 대상(500P로)
  S2 구글 **테스트 결제**만 한 회원(라이선스 테스터) → 대상(Mock 기록이 없어도)
  S3 구글 실결제가 있는 회원 → 제외(Mock·테스트 결제가 함께 있어도)
  S4 토스 실결제 회원 → 제외
  S5 행 없는 옛 pg:gplay: 기록(테스트 여부 모름) → 실결제로 보고 제외
  S6 결제·충전 기록 없이 적립금을 쓴 일반 회원 → **대상**(500P로 다시 채움 — 10-11 변경)
  S7 잔액이 이미 500P면 대상에서 빠진다
  S8 --confirm 없이 실행하면 DB를 바꾸지 않는다(미리보기)
  S9 결제 기록 없이 500P 를 넘는 회원 → 대상(500P로 내림)
  S10 애플 샌드박스(심사관·TestFlight) 결제만 → 대상 / 애플 실결제 → 제외
  S11 탈퇴(익명화) 회원 → 제외

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_reset_tester_balances.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _p in (str(ROOT), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _db_isolation  # noqa: E402
import wallet_db as wdb  # noqa: E402


def _member(handle: str, balance: int) -> int:
    mid, _ = wdb.get_or_create_member("kakao", handle)
    conn = sqlite3.connect(_db_isolation.current_path())
    conn.execute("INSERT OR IGNORE INTO wallets (member_id, balance) VALUES (?, 0)", (mid,))
    conn.execute("UPDATE wallets SET balance = ? WHERE member_id = ?", (balance, mid))
    conn.commit()
    conn.close()
    return int(mid)


def _charge_marker(mid: int, ref: str) -> None:
    conn = sqlite3.connect(_db_isolation.current_path())
    conn.execute(
        "INSERT INTO pg_charges (member_id, amount, pg_ref_id, status, created_at) VALUES (?, 1000, ?, 'completed', 'x')",
        (mid, ref),
    )
    conn.commit()
    conn.close()


def _gplay(mid: int, token: str, is_test: bool) -> None:
    wdb.record_gplay_points_purchase(mid, token, "points_1000", 1000, is_test=is_test)
    _charge_marker(mid, wdb.gplay_ref(token))


def main() -> int:
    import reset_tester_balances as rtb

    failed = 0
    with _db_isolation.isolated_db():
        wdb.init_wallet_tables()
        a = _member("rs_mock", 3000); _charge_marker(a, "pg:mock:a:1")
        b = _member("rs_testonly", 2500); _gplay(b, "tok_b", True)
        c = _member("rs_real", 4000); _charge_marker(c, "pg:mock:c:1"); _gplay(c, "tok_c1", True); _gplay(c, "tok_c2", False)
        d = _member("rs_toss", 9000); _charge_marker(d, "pg:mock:d:1"); _charge_marker(d, "pg:toss:d:1")
        e = _member("rs_legacy", 1500); _charge_marker(e, "pg:mock:e:1"); _charge_marker(e, "pg:gplay:legacy_e")
        f = _member("rs_normal", 120)
        g = _member("rs_already", 500); _charge_marker(g, "pg:mock:g:1")
        h = _member("rs_over", 800)
        i = _member("rs_apple_sb", 1500)
        wdb.record_gplay_points_purchase(i, "apple:sb1", "points_1000", 1000, is_test=True, store="apple")
        _charge_marker(i, wdb.gplay_ref("apple:sb1"))
        j = _member("rs_apple_real", 1500)
        wdb.record_gplay_points_purchase(j, "apple:pr1", "points_1000", 1000, is_test=False, store="apple")
        _charge_marker(j, wdb.gplay_ref("apple:pr1"))
        k = _member("rs_deleted", 300)
        wdb.anonymize_member_account(k)

        conn = wdb._connect()
        targets = dict(rtb.select_targets(conn, verbose=False))
        conn.close()
        checks = [
            ("S1 Mock 충전만 → 대상", a in targets),
            ("S2 테스트 결제만 → 대상", b in targets),
            ("S3 구글 실결제 → 제외", c not in targets),
            ("S4 토스 실결제 → 제외", d not in targets),
            ("S5 옛 구글 기록 → 제외", e not in targets),
            ("S6 일반 사용자(120P) → 대상", f in targets),
            ("S7 이미 500P → 제외", g not in targets),
            ("S9 결제 없이 800P → 대상", h in targets),
            ("S10a 애플 샌드박스만 → 대상", i in targets),
            ("S10b 애플 실결제 → 제외", j not in targets),
            ("S11 탈퇴 회원 → 제외", k not in targets),
        ]
        sys_argv = sys.argv
        sys.argv = ["reset_tester_balances.py"]
        try:
            rtb.main()
        finally:
            sys.argv = sys_argv
        checks.append(("S8 미리보기는 DB 불변", wdb.get_balance(a) == 3000 and wdb.get_balance(b) == 2500))
    for label, ok in checks:
        print(("PASS " if ok else "FAIL ") + label)
        failed += 0 if ok else 1
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
