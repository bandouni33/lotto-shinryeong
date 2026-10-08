# -*- coding: utf-8 -*-
"""짧게 재사용하는 DB 조회 캐시(ttl_cache) — 2026-10-08 로딩 시간 대응.

  T1 같은 이름·인자는 TTL 동안 loader 를 다시 부르지 않고, 지나면 다시 부른다.
  T2 invalidate(prefix) 는 그 접두어 칸만 비운다.
  T3 DB 연결 함수가 바뀌면(테스트 격리 등) 다른 칸을 쓴다 — 운영 값과 섞이지 않는다.
  T4 쓰는 쪽이 즉시 비운다: app_settings.set_setting 직후 get_setting 은 새 값,
     draw_results_db.upsert_draw_result 직후 get_cache_key 는 새 키(격리 DB).
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import _db_isolation  # noqa: E402
import db_turso  # noqa: E402
import ttl_cache  # noqa: E402


class TtlCacheTests(unittest.TestCase):
    def setUp(self):
        ttl_cache.invalidate()

    def test_T1_ttl(self):
        calls = []
        load = lambda: calls.append(1) or len(calls)  # noqa: E731
        self.assertEqual(ttl_cache.cached("t:a", 0.3, load, 1), 1)
        self.assertEqual(ttl_cache.cached("t:a", 0.3, load, 1), 1)
        self.assertEqual(ttl_cache.cached("t:a", 0.3, load, 2), 2, "인자가 다르면 다른 칸")
        time.sleep(0.35)
        self.assertEqual(ttl_cache.cached("t:a", 0.3, load, 1), 3)

    def test_T2_invalidate_prefix(self):
        ttl_cache.cached("x:1", 60, lambda: "x")
        ttl_cache.cached("y:1", 60, lambda: "y")
        ttl_cache.invalidate("x:")
        self.assertEqual(ttl_cache.cached("x:1", 60, lambda: "x2"), "x2")
        self.assertEqual(ttl_cache.cached("y:1", 60, lambda: "y2"), "y")

    def test_T3_db_identity(self):
        ttl_cache.cached("z", 60, lambda: "prod")
        saved = db_turso.connect
        try:
            db_turso.connect = lambda: None
            self.assertEqual(ttl_cache.cached("z", 60, lambda: "other"), "other")
        finally:
            db_turso.connect = saved

    def test_T4_writers_invalidate(self):
        import app_settings
        import draw_results_db

        with _db_isolation.isolated_db():
            app_settings.init_settings_table()
            self.assertEqual(app_settings.get_setting("k_t4", "d"), "d")
            app_settings.set_setting("k_t4", "v1")
            self.assertEqual(app_settings.get_setting("k_t4", "d"), "v1")
            app_settings.set_setting("k_t4", "v2")
            self.assertEqual(app_settings.get_setting("k_t4", "d"), "v2")
            draw_results_db.init_draw_results_table()
            k0 = draw_results_db.get_cache_key()
            draw_results_db.upsert_draw_result(1300, [1, 2, 3, 4, 5, 6], 7)
            self.assertNotEqual(draw_results_db.get_cache_key(), k0)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(TtlCacheTests))
    sys.exit(0 if result.wasSuccessful() else 1)
