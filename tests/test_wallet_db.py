"""wallet_db tests."""

import os
import tempfile
import wallet_db as wdb


def test_signup_bonus_once():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        old = wdb.DB_PATH
        wdb.DB_PATH = path
        try:
            wdb.init_wallet_tables()
            mid, new = wdb.get_or_create_member("kakao", "user123")
            assert new
            assert wdb.grant_signup_bonus(mid)
            assert wdb.get_balance(mid) == 5000
            assert not wdb.grant_signup_bonus(mid)
            assert wdb.get_balance(mid) == 5000
        finally:
            wdb.DB_PATH = old


def test_deduct_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        old = wdb.DB_PATH
        wdb.DB_PATH = path
        try:
            wdb.init_wallet_tables()
            mid, _ = wdb.get_or_create_member("kakao", "u2")
            wdb.grant_signup_bonus(mid)
            assert wdb.deduct_points(mid, 1000, "test", "ref:1")
            assert wdb.get_balance(mid) == 4000
            assert wdb.deduct_points(mid, 1000, "test", "ref:1")
            assert wdb.get_balance(mid) == 4000
            assert not wdb.deduct_points(mid, 99999, "test", "ref:2")
        finally:
            wdb.DB_PATH = old


def test_free_advanced_sub():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        old = wdb.DB_PATH
        wdb.DB_PATH = path
        try:
            wdb.init_wallet_tables()
            mid, _ = wdb.get_or_create_member("kakao", "u3")
            assert wdb.eligible_free_advanced_sub(mid)
            assert wdb.activate_free_advanced_sub(mid)
            assert not wdb.eligible_free_advanced_sub(mid)
            assert wdb.has_active_subscription(mid)
        finally:
            wdb.DB_PATH = old


def test_charge_points():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        old = wdb.DB_PATH
        wdb.DB_PATH = path
        try:
            wdb.init_wallet_tables()
            mid, _ = wdb.get_or_create_member("kakao", "u4")
            wdb.grant_signup_bonus(mid)
            assert wdb.charge_points(mid, 10000, "pg:mock:1")
            assert wdb.get_balance(mid) == 15000
            assert wdb.charge_points(mid, 10000, "pg:mock:1")
            assert wdb.get_balance(mid) == 15000
        finally:
            wdb.DB_PATH = old


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

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        old_w, old_m = wdb.DB_PATH, mdb.DB_PATH
        wdb.DB_PATH = path
        mdb.DB_PATH = path
        try:
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
            assert wdb.get_balance(mid) == before - 1000
            assert mdb.get_combination_count_by_draw(draw_round) == 6
            assert mdb.count_available_combinations(draw_round) == 1
            conn = mdb._connect()
            allocated = conn.execute(
                "SELECT COUNT(*) FROM lotto_combinations WHERE draw_round = ? AND allocated_at IS NOT NULL",
                (draw_round,),
            ).fetchone()[0]
            conn.close()
            assert allocated == 5
        finally:
            wdb.DB_PATH = old_w
            mdb.DB_PATH = old_m
