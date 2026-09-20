"""load_lotto_data()가 draw_results DB 변경을 즉시 반영하는지 검증.

회귀 대상: lotto_stats._load_lotto_data_db_cached(_cache_key) — Streamlit은
함수 인자 이름이 밑줄로 시작하면 그 인자를 캐시 키 해시에서 제외한다(설치된
스트림릿 문서에도 그대로 적혀 있음: "from caching, use an underscore prefix in
the argument name"). 그래서 _draw_results_cache_key()가 아무리 정확해도 캐시
키는 항상 같은 값이었고, 관리자가 새 회차를 등록해도(또는 자동 동기화가 새
회차를 채워도) 프로세스가 재시작되기 전까지 최초 로드값이 그대로 반환됐다.

두 클래스로 나눠 검증한다.
  · LottoDataDbCacheTests — 수정 자체를 겨냥한 회귀 테스트(예전 코드에서 실패).
  · LottoDataDbCacheInvariantTests — 예시 하나가 아니라 "모든 유효 입력"에 대해
    성립해야 하는 불변식: 삽입 순서와 무관하게 각 삽입이 즉시 반영될 것,
    키가 다르면 캐시 항목이 분리될 것, 캐싱이 결과를 바꾸지 않을 것,
    경계값(빈 DB·중복·비정렬·1/45)과 잘못된 입력(거부 + DB 불변)까지.

주의: lotto_stats의 캐시는 프로세스 전역이라 테스트끼리 겹칠 수 있어서
setUp에서 매번 비운다(각 테스트는 항상 "차가운 캐시"에서 시작하고, 캐시를
비우지 않는 호출이 바로 이 회귀의 검증 지점이다).
"""

import random
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import draw_results_db  # noqa: E402
import lotto_stats  # noqa: E402


def _rounds(data) -> set[int]:
    return {int(v) for v in data[lotto_stats.COL_DRAW] if v is not None}


class _IsolatedStatsCase(unittest.TestCase):
    """임시 sqlite 격리 + 캐시 초기화 + 외부 조회 차단 — 모든 테스트 공통 준비."""

    def setUp(self):
        # 진짜 운영 Turso로 나가지 않도록 임시 sqlite로 격리한다(tests/_db_isolation.py).
        self._iso = _db_isolation.isolated_db()
        self._iso.__enter__()
        self.addCleanup(self._iso.__exit__, None, None, None)
        draw_results_db.init_draw_results_table()

        # 테스트마다 DB 파일은 새로 만들어지지만 캐시 키는 (건수, 최신회차)라
        # 테스트끼리 같은 값이 될 수 있다 — 앞 테스트가 남긴 캐시를 물려받으면
        # 검증하려는 것과 다른 이유로 통과/실패할 수 있다.
        lotto_stats._load_lotto_data_db_cached.clear()

        # _draw_results_cache_key() 안에서 동행복권 사이트를 조회하는데(캐시 TTL
        # 1시간), 테스트가 외부 응답에 의존하거나 최대 8초씩 느려지면 안 된다.
        # 호출부가 `draw_results_db.sync_latest_from_dhlottery()`로 모듈 속성을
        # 매번 다시 찾으므로 이 패치가 그대로 먹는다.
        original_sync = draw_results_db.sync_latest_from_dhlottery
        draw_results_db.sync_latest_from_dhlottery = lambda: None
        self.addCleanup(
            setattr, draw_results_db, "sync_latest_from_dhlottery", original_sync
        )
        lotto_stats._auto_sync_latest_draw_cached.clear()

    def insert(self, draw_round: int, numbers: list[int], bonus: int) -> None:
        draw_results_db.upsert_draw_result(draw_round, numbers, bonus)

    def assert_data_matches_db(self, context: str = "") -> None:
        """로더 반환값이 "지금 DB에 있는 그대로"인지 — 회차 집합·건수뿐 아니라
        각 행의 번호·보너스·AC값까지 본다(회차 수만 맞고 값이 옛 것일 수 있으므로)."""
        data = lotto_stats.load_lotto_data()
        expected = {r["draw_round"]: r for r in draw_results_db.get_all_draw_results()}
        self.assertEqual(len(data), len(expected), f"{context}: 건수가 DB와 다르다")
        self.assertEqual(_rounds(data), set(expected), f"{context}: 회차 집합이 DB와 다르다")
        for _, row in data.iterrows():
            rnd = int(row[lotto_stats.COL_DRAW])
            nums = [int(row[lotto_stats.COL_NUM_START + i]) for i in range(6)]
            self.assertEqual(nums, expected[rnd]["numbers"], f"{context}: {rnd}회차 번호")
            self.assertEqual(
                int(row[lotto_stats.COL_BONUS]), expected[rnd]["bonus"], f"{context}: {rnd}회차 보너스"
            )
            self.assertEqual(
                int(row[lotto_stats.COL_AC]), lotto_stats._ac_value(nums), f"{context}: {rnd}회차 AC"
            )


class LottoDataDbCacheTests(_IsolatedStatsCase):
    def test_new_round_is_visible_without_cache_clear(self):
        """회귀의 핵심 — upsert_draw_result() 후 load_lotto_data()가 즉시 새 값."""
        self.insert(1237, [1, 2, 3, 4, 5, 6], 7)
        first = lotto_stats.load_lotto_data()
        self.assertIn(1237, _rounds(first))

        self.insert(1238, [10, 11, 12, 13, 14, 15], 16)
        # 캐시를 비우지 않고 그대로 다시 부른다 — 예전 코드는 여기서 1237만 담긴
        # 최초 로드값을 그대로 돌려줬다.
        second = lotto_stats.load_lotto_data()
        self.assertIn(
            1238,
            _rounds(second),
            "새 회차가 반영되지 않았다 — 캐시가 무효화되지 않고 있다",
        )

        # 회차 존재만이 아니라 번호·보너스 값 자체가 새 회차의 값인지까지 본다.
        row = second[second[lotto_stats.COL_DRAW] == 1238].iloc[0]
        nums = [int(row[lotto_stats.COL_NUM_START + i]) for i in range(6)]
        self.assertEqual(nums, [10, 11, 12, 13, 14, 15])
        self.assertEqual(int(row[lotto_stats.COL_BONUS]), 16)

    def test_loader_cache_key_participates_in_hashing(self):
        """화이트박스 보강 — 캐시 키 값이 다르면 다른 결과가 나온다(밑줄 인자 아님).

        key가 해시에서 제외되면 두 호출이 같은 캐시 항목을 타서 행 수가 같아진다.
        """
        self.insert(1237, [1, 2, 3, 4, 5, 6], 7)
        one_round = lotto_stats._load_lotto_data_db_cached((1, 1237))
        self.assertEqual(len(one_round), 1)

        self.insert(1238, [10, 11, 12, 13, 14, 15], 16)
        two_rounds = lotto_stats._load_lotto_data_db_cached((2, 1238))
        self.assertEqual(len(two_rounds), 2)

        # 같은 키로 다시 부르면 캐시된 같은 결과(캐싱 자체는 여전히 동작한다).
        self.assertEqual(len(lotto_stats._load_lotto_data_db_cached((2, 1238))), 2)

    def test_distinct_keys_do_not_alias_in_either_order(self):
        """키가 다르면 캐시 항목이 분리된다 — 어떤 순서로 다시 불러도 각 키의 값 유지."""
        self.insert(1237, [1, 2, 3, 4, 5, 6], 7)
        old = lotto_stats._load_lotto_data_db_cached((1, 1237))
        self.insert(1238, [10, 11, 12, 13, 14, 15], 16)
        new = lotto_stats._load_lotto_data_db_cached((2, 1238))

        self.assertEqual(len(old), 1)
        self.assertEqual(len(new), 2)
        # 역순 재조회(새 키 먼저 → 옛 키)에서도 값이 서로 섞이지 않는다.
        self.assertEqual(len(lotto_stats._load_lotto_data_db_cached((2, 1238))), 2)
        self.assertEqual(len(lotto_stats._load_lotto_data_db_cached((1, 1237))), 1)


class LottoDataDbCacheInvariantTests(_IsolatedStatsCase):
    def test_every_insert_is_visible_regardless_of_order(self):
        """불변식: 새 회차를 넣는 한, 삽입 순서와 무관하게 그 직후 호출이 DB와 일치한다."""
        rng = random.Random(20260920)
        rounds = list(range(100, 130))  # 30회차
        rng.shuffle(rounds)  # 순서 뒤섞기(중간에 낮은 회차가 나중에 들어오는 경우 포함)
        for rnd in rounds:
            nums = sorted(rng.sample(range(1, 46), 6))
            bonus = rng.choice([n for n in range(1, 46) if n not in nums])
            self.insert(rnd, nums, bonus)
            self.assert_data_matches_db(f"{rnd} 삽입 직후")

    def test_cache_key_moves_on_every_new_round(self):
        """이 수정이 기대는 전제 — 새 회차 등록은 매번 캐시 키를 바꾼다."""
        rng = random.Random(7)
        key = lotto_stats._draw_results_cache_key()
        for rnd in range(200, 215):
            nums = sorted(rng.sample(range(1, 46), 6))
            bonus = rng.choice([n for n in range(1, 46) if n not in nums])
            self.insert(rnd, nums, bonus)
            new_key = lotto_stats._draw_results_cache_key()
            self.assertNotEqual(new_key, key, f"{rnd} 등록 후에도 캐시 키가 그대로다")
            key = new_key

    def test_next_draw_round_follows_db_without_restart(self):
        """사용자에게 보이는 증상 그대로 — 새 회차가 확정되면 "다음 회차"도 즉시 한 칸 밀린다.

        화면에 나오는 "다음회차"(자동구매 배포 대상·번개조합 풀 회차·관리자 표의
        "다음에 추출할 회차")는 모두 _next_draw_round() = 최신 확정 회차 + 1 로 계산된다
        (auto_purchase_service.py:30). 로더가 무효화되지 않던 시절에는 프로세스가 뜬
        시점의 최신 회차에 고정돼서, 1242가 확정된 뒤에도 화면은 계속 1242를 "다음
        회차"로 보여줬다(정답은 1243).
        """
        from auto_purchase_service import _next_draw_round

        self.insert(1241, [1, 2, 3, 4, 5, 6], 7)
        self.assertEqual(_next_draw_round(), 1242)

        self.insert(1242, [10, 11, 12, 13, 14, 15], 16)
        self.assertEqual(
            _next_draw_round(),
            1243,
            "새 회차가 확정된 뒤에도 '다음 회차'가 옛 값에 고정돼 있다",
        )

    def test_caching_is_transparent_to_results(self):
        """같은 상태에서 여러 번 불러도 같은 값(캐시 적중이 결과를 바꾸지 않는다)."""
        for rnd in (150, 151, 152):
            self.insert(rnd, [1, 2, 3, 4, 5, 6 + (rnd - 150)], 7)
            first = lotto_stats.load_lotto_data()
            second = lotto_stats.load_lotto_data()
            self.assertTrue(first.equals(second), f"{rnd} 삽입 후 재호출 결과가 달라졌다")
            self.assert_data_matches_db(f"{rnd} 재호출")

    def test_empty_db_returns_none(self):
        """빈 DB 계약 유지 — None을 반환해서 호출부가 xlsb 폴백으로 넘어갈 수 있어야 한다."""
        self.assertIsNone(lotto_stats._load_lotto_data_db_cached((0, 0)))
        self.assertIsNone(
            lotto_stats._load_lotto_data_db_cached((5, 9999)),
            "DB가 비어 있는데 키 값에 따라 다른 결과가 나왔다",
        )

    def test_duplicate_identical_insert_is_idempotent(self):
        for _ in range(3):
            self.insert(1237, [1, 2, 3, 4, 5, 6], 7)
        self.assertEqual(draw_results_db.get_draw_results_count(), 1)
        self.assert_data_matches_db("같은 회차 3회 등록 후")

    def test_boundary_numbers_are_normalized(self):
        """경계값(1·45 포함, 뒤섞인 입력) — upsert가 정렬 저장하고 로더도 정렬로 돌려준다."""
        self.insert(3000, [45, 1, 22, 9, 7, 3], 44)
        self.assert_data_matches_db("1·45 경계 + 비정렬 입력")
        row = lotto_stats.load_lotto_data().iloc[0]
        nums = [int(row[lotto_stats.COL_NUM_START + i]) for i in range(6)]
        self.assertEqual(nums, [1, 3, 7, 9, 22, 45])
        self.assertEqual(int(row[lotto_stats.COL_BONUS]), 44)

    def test_invalid_input_is_rejected_and_changes_nothing(self):
        """오류 케이스는 실패해야 하고, 그 실패가 DB·캐시를 건드리면 안 된다."""
        self.insert(1237, [1, 2, 3, 4, 5, 6], 7)
        before = lotto_stats.load_lotto_data()

        for bad_numbers in ([1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 5], [0, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 46]):
            with self.assertRaises(ValueError, msg=f"{bad_numbers} 가 거부되지 않았다"):
                self.insert(1238, bad_numbers, 7)
        for bad_bonus in (0, 46):
            with self.assertRaises(ValueError, msg=f"보너스 {bad_bonus} 가 거부되지 않았다"):
                self.insert(9999, [1, 2, 3, 4, 5, 6], bad_bonus)

        self.assertEqual(draw_results_db.get_draw_results_count(), 1)
        self.assertTrue(before.equals(lotto_stats.load_lotto_data()))
        self.assert_data_matches_db("잘못된 입력 반복 후")


if __name__ == "__main__":
    unittest.main()
