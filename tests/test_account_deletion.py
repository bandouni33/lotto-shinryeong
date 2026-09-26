"""계정 삭제(회원 탈퇴) 검증 — 2026-09-27 (Google Play '계정 삭제' 정책 대응).

무엇을 보는가
  I1 신원 파기 — OAuth 해시가 다시 나오지 않고, 같은 계정 재로그인은 새 회원이 된다
  I2 기기 연결 파기 — 남아있으면 자동로그인이 되살아난다(전수 guest_id)
  I3 기기 스코프 사용자 데이터 파기(구매내역·저장 조합·타로 뽑기·배너 확인)
  I4 생일·개선 의견·주문 연락처 파기(연락처는 테이블 전체에서 사라졌는지 본다)
  I5 **법정 보관 증빙은 지우지 않는다**(ledger·결제승인·동의·구독 이력) — 과잉 삭제는
     전자상거래법 위반이고, 지갑 잔액·미정산 대기행은 정리된다
  I6 멱등 + 다른 회원 무영향(경계: 같은 DB에 두 번째 회원)
  I7 누적 가입자 수에서 탈퇴 계정 제외
  I8 화면·약관 문구(legal_notices)와 실제 파기/보관 목록(account_deletion)이 일치
  B1 실제 진입점(app.py)의 내정보 창에 [회원 탈퇴] 버튼이 있다
  B2 버튼을 누르면 확인창이 열리고, 확인 체크 전에는 실행 버튼이 눌리지 않는다(가드)
  F1 탈퇴 실행 = 파기 + 로그아웃 + 완료 안내 (다이얼로그 안 버튼은 AppTest가 재현하지
     못하므로, 그 버튼이 부르는 함수를 프로브로 그대로 태운다)
  F2 앱 밖 공개 URL(page=delete_account)과 개인정보 처리방침(page=privacy)에
     탈퇴 경로가 실제로 보인다 — Play Console에 신고할 URL이 실제로 열리는지

DB는 _db_isolation.isolated_db()로만 만진다(운영 Turso 접촉 0).
pytest 없이 돌도록 표준 assert + __main__ 러너를 둔다.
"""

from __future__ import annotations

import itertools
import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

from streamlit.testing.v1 import AppTest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import wallet_db as wdb  # noqa: E402

ENTRY = str(ROOT / "app.py")
PROBE = str(TESTS_DIR / "_account_deletion_probe.py")
TIMEOUT_SEC = 60
PHONE = "010-1234-5678"
NOW = "2026-09-27 10:00:00.000000"
# guest_auto_orders.auto_order_id는 UNIQUE다 — 한 테스트 안에서 회원을 둘 이상 심어도
# 겹치지 않게 프로세스 전역 카운터를 쓴다.
_AUTO_ORDER_SEQ = itertools.count(9001)


# ── 공용 도우미 ────────────────────────────────────────────────
def _rows(sql: str, *params):
    conn = sqlite3.connect(_db_isolation.current_path())
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _exec(sql: str, *params) -> None:
    conn = sqlite3.connect(_db_isolation.current_path())
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _count(table: str, where: str = "1=1", *params) -> int:
    return int(_rows(f"SELECT COUNT(*) FROM {table} WHERE {where}", *params)[0][0])


def _seed_member(handle: str, gids: tuple[str, ...] = ()) -> int:
    """회원 1명 + (지워져야 하는) 개인정보 + (남아야 하는) 보관 증빙을 모두 심는다."""
    wdb.init_wallet_tables()
    mid, _is_new = wdb.get_or_create_member("kakao", handle)
    mid = int(mid)
    for gid in gids:
        wdb.link_guest_to_member(gid, mid, f"ua-{gid}")

    # 보관 증빙(법정 5년) — 탈퇴해도 남아야 한다
    _exec(
        "UPDATE wallets SET balance = ?, toss_customer_key = ? WHERE member_id = ?",
        1500,
        f"ck_{handle}",
        mid,
    )
    _exec(
        "INSERT INTO wallet_ledger (member_id, delta, balance_after, reason, ref_id, created_at)"
        " VALUES (?,?,?,?,?,?)",
        mid,
        1000,
        1000,
        "charge",
        f"ledger_{handle}",
        NOW,
    )
    _exec(
        "INSERT INTO pg_charges (member_id, amount, pg_ref_id, status, created_at) VALUES (?,?,?,?,?)",
        mid,
        10000,
        f"pg_{handle}",
        "completed",
        NOW,
    )
    _exec(
        "INSERT INTO consent_log (member_id, notice_version, agreed_at) VALUES (?,?,?)",
        mid,
        "v1.1-draft",
        NOW,
    )
    _exec(
        "INSERT INTO signup_grants (member_id, granted_at, amount) VALUES (?,?,?)",
        mid,
        NOW,
        500,
    )
    _exec(
        "INSERT INTO subscriptions (member_id, product, starts_at, expires_at, is_free_promo)"
        " VALUES (?,?,?,?,0)",
        mid,
        "advanced_filter_monthly",
        NOW,
        NOW,
    )
    _exec(
        "INSERT INTO toss_pending_orders (order_id, member_id, won_amount, points, status, created_at)"
        " VALUES (?,?,?,?,?,?)",
        f"order_ok_{handle}",
        mid,
        10000,
        1000,
        "confirmed",
        NOW,
    )

    # 탈퇴 시 사라져야 하는 것
    _exec(
        "INSERT INTO thunder_pending_charges (ref_id, member_id, cost, game_count, created_at, settled)"
        " VALUES (?,?,?,?,?,0)",
        f"th_{handle}",
        mid,
        100,
        10,
        NOW,
    )
    _exec(
        "INSERT INTO toss_pending_orders (order_id, member_id, won_amount, points, status, created_at)"
        " VALUES (?,?,?,?,?,?)",
        f"order_pending_{handle}",
        mid,
        10000,
        1000,
        "pending",
        NOW,
    )
    wdb.create_auto_order(mid, 5, "일반구매", PHONE, "", f"auto_{handle}")

    import birthday_db
    import feedback_db
    import marketing_db
    from user_scope import birthday_scope_for

    birthday_db.upsert_birthday(birthday_scope_for(mid), 1, "본인", "0101")
    feedback_db.init_feedback_tables()
    feedback_db.save_feedback("개선 의견 본문", member_id=mid)
    marketing_db.init_marketing_tables()
    for gid in gids:
        _exec(
            "INSERT INTO guest_generated_combos"
            " (guest_id, source, draw_round, num1, num2, num3, num4, num5, num6, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            gid,
            "thunder",
            1242,
            1,
            2,
            3,
            4,
            5,
            6,
            NOW,
        )
        _exec(
            "INSERT INTO guest_auto_orders (guest_id, auto_order_id, created_at) VALUES (?,?,?)",
            gid,
            next(_AUTO_ORDER_SEQ),
            NOW,
        )
        _exec(
            "INSERT INTO guest_tarot_draws (guest_id, draw_date, count) VALUES (?,?,?)",
            gid,
            "2026-09-27",
            1,
        )
        _exec(
            "INSERT INTO guest_update_notice (guest_id, version, last_shown_date) VALUES (?,?,?)",
            gid,
            "v1",
            "2026-09-27",
        )
    return mid


@contextmanager
def _prod_like_env():
    """운영과 같은 판정(테스트 기간 우회 꺼짐)을 만들기 위한 최소 환경변수."""
    keys = ("KAKAO_REST_API_KEY", "LOTTO_DEV_MOCK_AUTH", "TOSS_CLIENT_KEY", "TOSS_SECRET_KEY")
    before = {key: os.environ.get(key) for key in keys}
    os.environ["KAKAO_REST_API_KEY"] = "test_kakao_key"
    os.environ["LOTTO_DEV_MOCK_AUTH"] = "0"
    try:
        yield
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _safe(text: str) -> str:
    """콘솔(cp949)에서 못 찍는 문자 때문에 테스트 출력이 죽는 것을 막는다."""
    return str(text).encode("ascii", "replace").decode("ascii")


def _ss(at: AppTest, key: str, default=None):
    """AppTest의 session_state 프록시에는 .get()이 없다 — getitem + KeyError로 대신한다
    (tests/test_login_gate_callbacks.py의 같은 도우미와 동일한 이유)."""
    try:
        return at.session_state[key]
    except KeyError:
        return default


def _keys(at: AppTest) -> list[str]:
    return [b.key for b in at.button]


def _body(at: AppTest) -> str:
    return "\n".join((m.value or "") for m in at.markdown)


def _open_my_info(mid: int) -> AppTest:
    at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
    at.query_params["page"] = "main"
    at.query_params["gid"] = "delentry01"
    at.query_params["native"] = "1"
    at.session_state["member_id"] = mid
    at.session_state["_guest_id"] = "delentry01"
    at.session_state["my_info_dialog_open"] = True
    at.run()
    return at


def _click(at: AppTest, key: str) -> AppTest:
    for button in at.button:
        if button.key == key:
            return button.click().run()
    raise AssertionError(f"버튼을 찾지 못했다: {key} (있던 키: {_keys(at)})")


# ── I. 불변식(모든 유효 입력에 성립해야 하는 성질) ──────────────
def test_I1_identity_is_destroyed_and_relogin_creates_new_member():
    with _db_isolation.isolated_db():
        import account_deletion

        mid = _seed_member("del_i1", ("gid-i1",))
        before_hash, before_provider = _rows(
            "SELECT oauth_hash, provider FROM members WHERE id = ?", mid
        )[0]

        summary = account_deletion.delete_account(mid)

        rows = _rows("SELECT oauth_hash, provider, deleted_at FROM members WHERE id = ?", mid)
        assert len(rows) == 1, "보관 증빙(ledger·pg_charges)이 가리킬 회원 행이 사라졌다"
        after_hash, after_provider, deleted_at = rows[0]
        assert after_hash != before_hash, "OAuth 식별자 해시가 그대로 남았다(신원 미파기)"
        assert after_provider == "deleted" and deleted_at, "탈퇴 표식(provider/deleted_at)이 없다"
        assert _rows("SELECT id FROM members WHERE oauth_hash = ?", before_hash) == [], (
            "옛 해시로 조회된다 — 신원이 파기되지 않았다"
        )
        assert summary["members"] == 1

        new_mid, is_new = wdb.get_or_create_member("kakao", "del_i1")
        assert is_new and int(new_mid) != mid, "탈퇴 후 재로그인이 새 계정으로 처리되지 않았다"


def test_I2_every_device_link_is_severed():
    with _db_isolation.isolated_db():
        import account_deletion

        gids = ("gid-i2a", "gid-i2b")
        mid = _seed_member("del_i2", gids)
        summary = account_deletion.delete_account(mid)

        assert summary["guest_ids"] == len(gids)
        assert summary["guest_member_links"] == len(gids)
        for gid in gids:
            assert _count("guest_member_links", "guest_id = ?", gid) == 0
            linked, ua = wdb.get_member_and_ua_for_guest(gid)
            assert not linked, f"{gid}로 자동로그인이 되살아난다(연결 미파기)"


def test_I3_device_scoped_user_data_is_purged():
    with _db_isolation.isolated_db():
        import account_deletion

        gids = ("gid-i3a", "gid-i3b")
        mid = _seed_member("del_i3", gids)
        for table in (
            "guest_generated_combos",
            "guest_auto_orders",
            "guest_tarot_draws",
            "guest_update_notice",
        ):
            assert _count(table) > 0, f"사전조건 실패: {table}에 심은 데이터가 없다"

        account_deletion.delete_account(mid)

        for table in (
            "guest_generated_combos",
            "guest_auto_orders",
            "guest_tarot_draws",
            "guest_update_notice",
        ):
            left = _count(table)
            assert left == 0, f"{table}에 기기 스코프 데이터가 남았다: {left}건"


def test_I4_birthday_feedback_and_contact_are_purged():
    with _db_isolation.isolated_db():
        import account_deletion
        from user_scope import birthday_scope_for

        mid = _seed_member("del_i4", ("gid-i4",))
        assert _count("userBirthdays", "user_id = ?", birthday_scope_for(mid)) == 1
        assert _count("improvement_feedback", "member_id = ?", mid) == 1
        assert _count("auto_orders", "phone = ?", PHONE) == 1

        account_deletion.delete_account(mid)

        assert _count("userBirthdays", "user_id = ?", birthday_scope_for(mid)) == 0, (
            "등록한 생일이 남았다"
        )
        assert _count("improvement_feedback", "member_id = ?", mid) == 0, "작성한 글이 남았다"
        assert _count("auto_orders", "phone = ?", PHONE) == 0, (
            "주문 연락처가 DB 어디에도 남아서는 안 된다"
        )
        assert _count("auto_orders", "member_id = ?", mid) == 1, "주문 기록 자체는 보관 대상이다"


def test_I5_legally_required_evidence_is_kept():
    with _db_isolation.isolated_db():
        import account_deletion

        mid = _seed_member("del_i5", ("gid-i5",))
        account_deletion.delete_account(mid)

        assert _count("wallet_ledger", "member_id = ?", mid) == 1, "[I5.ledger] 적립금 원장이 지워졌다"
        assert _count("pg_charges", "member_id = ?", mid) == 1, "[I5.pg_charges] 결제 승인 기록이 지워졌다"
        assert _count("consent_log", "member_id = ?", mid) == 1, "[I5.consent_log] 약관·동의 기록이 지워졌다"
        assert _count("subscriptions", "member_id = ?", mid) == 1, "[I5.subscriptions] 구독 이력이 지워졌다"
        assert (
            _count("signup_grants", "member_id = ?", mid) == 1
        ), "[I5.signup_grants] 가입 적립금 지급 기록이 지워졌다"
        assert (
            _count("toss_pending_orders", "member_id = ? AND status = 'confirmed'", mid) == 1
        ), "[I5.toss_confirmed] 승인 완료된 결제 기록이 지워졌다"

        # 탈퇴 후 이뤄지면 안 되는 대기행·잔액은 정리된다
        assert (
            _count("thunder_pending_charges", "member_id = ?", mid) == 0
        ), "[I5.thunder_pending] 미정산 대기행이 남았다"
        assert (
            _count("toss_pending_orders", "member_id = ? AND status = 'pending'", mid) == 0
        ), "[I5.toss_pending] 미완료 주문이 남았다"
        balance, customer_key = _rows(
            "SELECT balance, toss_customer_key FROM wallets WHERE member_id = ?", mid
        )[0]
        assert int(balance) == 0, "[I5.balance] 탈퇴했는데 지갑 잔액이 남았다"
        assert not customer_key, "[I5.customer_key] 결제 고객 식별키가 남았다"


def test_I6_deletion_is_idempotent_and_leaves_other_members_alone():
    with _db_isolation.isolated_db():
        import account_deletion
        from user_scope import birthday_scope_for

        target = _seed_member("del_i6_target", ("gid-i6t",))
        other = _seed_member("del_i6_other", ("gid-i6o",))
        other_hash = _rows("SELECT oauth_hash FROM members WHERE id = ?", other)[0][0]

        first = account_deletion.delete_account(target)
        second = account_deletion.delete_account(target)

        assert first["guest_ids"] == 1
        assert second["guest_ids"] == 0 and second["guest_data"] == 0, "두 번째 호출이 지울 것을 찾았다"
        assert second["birthdays"] == 0 and second["feedback"] == 0
        assert second["toss_pending_orders_pending"] == 0

        # 다른 회원은 한 건도 건드리지 않는다
        assert _rows("SELECT oauth_hash FROM members WHERE id = ?", other)[0][0] == other_hash
        assert _count("guest_member_links", "guest_id = ?", "gid-i6o") == 1
        assert _count("userBirthdays", "user_id = ?", birthday_scope_for(other)) == 1
        assert _count("improvement_feedback", "member_id = ?", other) == 1
        assert _count("guest_generated_combos", "guest_id = ?", "gid-i6o") == 1
        assert _count("auto_orders", "phone = ?", PHONE) == 1, "다른 회원의 주문 연락처가 지워졌다"


def test_I7_deleted_account_leaves_installed_member_count():
    with _db_isolation.isolated_db():
        import account_deletion

        keep = _seed_member("del_i7_keep")
        drop = _seed_member("del_i7_drop")
        assert wdb.get_total_installed_members() == 2

        account_deletion.delete_account(drop)

        assert wdb.get_total_installed_members() == 1, "탈퇴 계정이 누적 가입자 수에 남았다"
        assert _rows("SELECT id FROM members WHERE id = ?", keep) != []


def test_I8_notice_text_matches_the_real_deletion_lists():
    import account_deletion
    import legal_notices

    body = legal_notices.ACCOUNT_DELETION_BODY
    for item in account_deletion.DELETED_ITEMS:
        assert item in body, f"탈퇴 안내 문구에 삭제 항목이 없다: {item}"
    for item in account_deletion.RETAINED_ITEMS:
        assert item in body, f"탈퇴 안내 문구에 보관 항목이 없다: {item}"
    assert account_deletion.RETAINED_REASON in body, "보관 근거(법령)가 문구에 없다"
    assert "page=delete_account" in body, "안내 문구가 공개 URL을 가리키지 않는다"
    assert "내정보" in body, "안내 문구가 앱 내 경로를 안내하지 않는다"


# ── B. 행동(사용자가 실제로 밟는 경로) ──────────────────────────
def test_B1_my_info_offers_account_deletion_button():
    with _prod_like_env(), _db_isolation.isolated_db():
        mid = _seed_member("del_b1", ("gid-b1",))
        at = _open_my_info(mid)
        assert not at.exception, f"진입점 렌더 예외: {at.exception}"
        assert "wallet_delete_account_btn" in _keys(at), (
            f"내정보 창에 회원 탈퇴 버튼이 없다: {_safe(str(_keys(at)))}"
        )


def test_B2_confirm_dialog_guards_the_irreversible_action():
    with _prod_like_env(), _db_isolation.isolated_db():
        mid = _seed_member("del_b2", ("gid-b2",))
        at = _open_my_info(mid)
        at = _click(at, "wallet_delete_account_btn")
        assert not at.exception, f"탈퇴 버튼 클릭 후 예외: {at.exception}"

        keys = _keys(at)
        assert "delete_account_confirm_btn" in keys, (
            f"확인창이 열리지 않았다(실행 버튼 없음): {_safe(str(keys))}"
        )
        assert "delete_account_cancel_btn" in keys, "확인창에 취소 버튼이 없다"
        assert "delete_account_agree" in [c.key for c in at.checkbox], "확인 체크박스가 없다"

        body = _body(at)
        assert "탈퇴하면 즉시 파기되는 항목" in body, "무엇이 지워지는지 화면에 없다"
        assert "법령에 따라 남는 항목" in body, "무엇이 남는지 화면에 없다"

        # 확인 전에는 실행할 수 없다(되돌릴 수 없는 작업의 최소 안전장치)
        confirm = [b for b in at.button if b.key == "delete_account_confirm_btn"][0]
        assert confirm.proto.disabled is True, "확인 체크 없이 실행 버튼이 눌린다"
        assert _rows("SELECT deleted_at FROM members WHERE id = ?", mid)[0][0] is None

        # 체크하면 실행 가능해진다 — 그리고 그때까지는 아무 것도 지워지지 않았다
        for box in at.checkbox:
            if box.key == "delete_account_agree":
                at = box.check().run()
                break
        assert not at.exception, f"체크 후 예외: {at.exception}"
        confirm = [b for b in at.button if b.key == "delete_account_confirm_btn"][0]
        assert confirm.proto.disabled is False, "확인을 체크해도 실행 버튼이 잠겨 있다"
        assert _rows("SELECT deleted_at FROM members WHERE id = ?", mid)[0][0] is None, (
            "체크만 했는데 탈퇴가 실행되었다"
        )


# ── F. 기능(조립된 것이 실제로 돈다) ────────────────────────────
def test_F1_running_deletion_destroys_logs_out_and_announces():
    with _prod_like_env(), _db_isolation.isolated_db():
        import legal_notices

        mid = _seed_member("del_f1", ("gid-f1",))
        at = AppTest.from_file(PROBE, default_timeout=TIMEOUT_SEC)
        at.query_params["probe"] = "run"
        at.session_state["member_id"] = mid
        at.run()
        assert not at.exception, f"탈퇴 실행 프로브 예외: {at.exception}"
        assert "DELETED" in _body(at), f"탈퇴가 실행되지 않았다: {_safe(_body(at)[:200])}"

        assert _ss(at, "member_id") in (None, 0), "탈퇴 후에도 로그인 상태가 남아있다"
        assert _ss(at, "wallet_toast") == legal_notices.ACCOUNT_DELETION_DONE, (
            "탈퇴 완료 안내가 세워지지 않았다(로그아웃이 지워버렸는지 확인 필요)"
        )
        summary = _ss(at, "probe_delete_summary") or {}
        assert summary.get("members") == 1 and summary.get("guest_member_links") == 1, (
            f"파기 요약이 비었다: {summary}"
        )

        assert _rows("SELECT deleted_at FROM members WHERE id = ?", mid)[0][0], "신원이 남았다"
        assert _count("guest_member_links", "member_id = ?", mid) == 0
        assert _count("guest_generated_combos") == 0
        assert _count("wallet_ledger", "member_id = ?", mid) == 1, "보관 증빙까지 지워졌다"


def test_F2_public_deletion_url_and_privacy_page_show_the_path():
    with _prod_like_env(), _db_isolation.isolated_db():
        at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
        at.query_params["page"] = "delete_account"
        at.run()
        assert not at.exception, f"공개 탈퇴 페이지 예외: {at.exception}"
        body = _body(at)
        assert "점검 중" not in body, "공개 탈퇴 페이지가 예외 화면으로 바뀌었다"
        assert "회원 탈퇴" in body and "내정보" in body, (
            f"공개 URL에 탈퇴 안내가 없다: {_safe(body[:200])}"
        )
        assert "?page=delete_account" in body, "자기 URL(신고할 주소)이 문구에 없다"

        at2 = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
        at2.query_params["page"] = "privacy"
        at2.run()
        assert not at2.exception, f"개인정보 처리방침 페이지 예외: {at2.exception}"
        privacy_body = _body(at2)
        assert "회원 탈퇴" in privacy_body and "내정보" in privacy_body, (
            "개인정보 처리방침(Play에 제출한 URL)에 앱 내 탈퇴 경로가 없다"
        )


def _main() -> int:
    tests = [
        test_I1_identity_is_destroyed_and_relogin_creates_new_member,
        test_I2_every_device_link_is_severed,
        test_I3_device_scoped_user_data_is_purged,
        test_I4_birthday_feedback_and_contact_are_purged,
        test_I5_legally_required_evidence_is_kept,
        test_I6_deletion_is_idempotent_and_leaves_other_members_alone,
        test_I7_deleted_account_leaves_installed_member_count,
        test_I8_notice_text_matches_the_real_deletion_lists,
        test_B1_my_info_offers_account_deletion_button,
        test_B2_confirm_dialog_guards_the_irreversible_action,
        test_F1_running_deletion_destroys_logs_out_and_announces,
        test_F2_public_deletion_url_and_privacy_page_show_the_path,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {_safe(str(exc))}")
        except Exception as exc:  # noqa: BLE001 — 러너이므로 무엇이든 보고하고 계속
            failed += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {_safe(str(exc))}")
        else:
            print(f"PASS {test.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
