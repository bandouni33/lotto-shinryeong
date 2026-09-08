"""wallet_db tests.

2026-09-08 수정: DB_PATH를 바꿔서 격리하려 했지만 wallet_db._connect()/
marketing_db._connect()가 실제로는 항상 db_turso.connect()(=진짜 운영
Turso)를 호출해서 DB_PATH를 아예 안 봤다 — 즉 이 테스트들은 격리되지
않고 이 파일을 실행할 때마다 매번 운영 DB에 가짜 회원(user123/u2/u3/u4/
auto_user)과 가짜 9001회차 조합·주문을 실제로 남기고 있었다(실측: id
100~104 회원, 9001회차 auto_orders 1건이 운영 Turso에 남아있는 것으로
확인·정리함). _connect() 자체를 임시 sqlite 파일로 바꿔치기하는 방식으로
교체해 실제로 격리되게 한다."""

import os
import tempfile
import sqlite3

import wallet_db as wdb


def _isolated_connect(path):
    def _connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    return _connect


def _with_isolated_db(modules):
    """modules(wallet_db, marketing_db 등)의 _connect()를 전부 같은 임시
    sqlite 파일로 바꿔치기하는 컨텍스트 매니저 — 진짜 Turso는 절대 안 건드림."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.db")
            originals = {m: m._connect for m in modules}
            for m in modules:
                m._connect = _isolated_connect(path)
            try:
                yield path
            finally:
                for m in modules:
                    m._connect = originals[m]

    return _ctx()


def test_signup_bonus_once():
    with _with_isolated_db([wdb]):
        wdb._WALLET_TABLES_READY = False
        wdb.init_wallet_tables()
        mid, new = wdb.get_or_create_member("kakao", "user123")
        assert new
        assert wdb.grant_signup_bonus(mid)
        assert wdb.get_balance(mid) == wdb.SIGNUP_BONUS
        assert not wdb.grant_signup_bonus(mid)
        assert wdb.get_balance(mid) == wdb.SIGNUP_BONUS


def test_deduct_idempotent():
    with _with_isolated_db([wdb]):
        wdb._WALLET_TABLES_READY = False
        wdb.init_wallet_tables()
        mid, _ = wdb.get_or_create_member("kakao", "u2")
        wdb.grant_signup_bonus(mid)
        assert wdb.deduct_points(mid, 100, "test", "ref:1")
        assert wdb.get_balance(mid) == wdb.SIGNUP_BONUS - 100
        assert wdb.deduct_points(mid, 100, "test", "ref:1")
        assert wdb.get_balance(mid) == wdb.SIGNUP_BONUS - 100
        assert not wdb.deduct_points(mid, 99999, "test", "ref:2")


def test_free_advanced_sub():
    with _with_isolated_db([wdb]):
        wdb._WALLET_TABLES_READY = False
        wdb.init_wallet_tables()
        mid, _ = wdb.get_or_create_member("kakao", "u3")
        assert wdb.eligible_free_advanced_sub(mid)
        assert wdb.activate_free_advanced_sub(mid)
        assert not wdb.eligible_free_advanced_sub(mid)
        assert wdb.has_active_subscription(mid)


def test_charge_points():
    with _with_isolated_db([wdb]):
        wdb._WALLET_TABLES_READY = False
        wdb.init_wallet_tables()
        mid, _ = wdb.get_or_create_member("kakao", "u4")
        wdb.grant_signup_bonus(mid)
        assert wdb.charge_points(mid, 10000, "pg:mock:1")
        assert wdb.get_balance(mid) == wdb.SIGNUP_BONUS + 10000
        assert wdb.charge_points(mid, 10000, "pg:mock:1")
        assert wdb.get_balance(mid) == wdb.SIGNUP_BONUS + 10000


def test_auto_order_flow():
    import unittest.mock

    import marketing_db as mdb
    import auto_purchase_service as aps

    draw_round = 9001
    seed_combos = [
        (7, 8, 9, 10, 11, 12),
        (7, 8, 9, 13, 14, 15),
        (7, 8, 16, 17, 18, 19),
        (7, 20, 21, 22, 23, 24),
        (7, 25, 26, 27, 28, 29),
        (1, 2, 3, 4, 5, 6),
    ]

    with _with_isolated_db([wdb, mdb]):
        wdb._WALLET_TABLES_READY = False
        mdb._MARKETING_TABLES_READY = False
        wdb.init_wallet_tables()
        mdb.init_marketing_tables()
        mdb.bulk_insert_lotto_combinations(draw_round, seed_combos)
        mid, _ = wdb.get_or_create_member("kakao", "auto_user")
        wdb.grant_signup_bonus(mid)
        before = wdb.get_balance(mid)
        with unittest.mock.patch.object(aps, "_next_draw_round", return_value=draw_round):
            outcome = aps.process_auto_purchase(mid, 5, "즉시", "01011112222")
        assert outcome["ok"]
        assert outcome["combo_count"] == 5
        assert outcome["draw_round"] == draw_round
        assert len(outcome["combo_ids"]) == 5
        assert wdb.get_balance(mid) == before - wdb.calc_auto_cost(5)
        assert mdb.get_combination_count_by_draw(draw_round) == 6
        assert mdb.count_available_combinations(draw_round) == 1
        conn = mdb._connect()
        allocated = conn.execute(
            "SELECT COUNT(*) FROM lotto_combinations WHERE draw_round = ? AND allocated_at IS NOT NULL",
            (draw_round,),
        ).fetchone()[0]
        conn.close()
        assert allocated == 5
