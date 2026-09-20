"""조립된 실제 진입점(app.py)에서 "사용자가 보는 값이 지금 DB 기준인지" 확인한다.

단위 테스트는 함수 하나만 본다 — 여기서는 Streamlit AppTest로 실제 진입점 app.py를
사용자가 여는 방식 그대로 렌더하고, 화면에 실제로 나가는 값이 DB와 맞는지 본다.

두 화면을 본다.
  1) 기본 화면(user_page) — 화면 상단 "최근당첨번호 NNNN회". DB에 새 회차가 들어오면
     서버 재시작 없이 그 값이 바뀌어야 한다(예전에는 프로세스가 뜬 시점 값에 고정).
  2) 번개조합 화면(?page=thunder) — 조합 추첨 근거인 번호별 가중치(numberWeights)를
     JS로 내려보낸다. 이 값도 지금 DB 기준이어야 한다.

주의: AppTest로 앱 전체를 렌더하므로 다른 AppTest 테스트들처럼 scratch/run_db_tests.py의
목록에는 넣지 않는다(그 러너는 빠른 DB 단위 테스트용).

실행: venv312\\Scripts\\python.exe -m unittest discover -s tests -p "test_app_draw_data_live.py" -v
"""

import os
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
from streamlit.testing.v1 import AppTest  # noqa: E402

ENTRY = str(ROOT / "app.py")
TIMEOUT_SEC = 90


def _markdown_blob(at: AppTest) -> str:
    return "\n".join((m.value or "") for m in at.markdown)


def _fresh_gid(prefix: str) -> str:
    return prefix + os.urandom(6).hex()


class _LiveAppCase(unittest.TestCase):
    """임시 sqlite 격리 + 캐시 초기화 + 외부 호출 차단 — 실제 진입점 렌더 공통 준비."""

    def setUp(self):
        # 격리 없이 돌리면 앱 렌더가 진짜 운영 Turso에 붙어(게스트 회원·지갑 테이블
        # 생성 등) 운영 DB에 흔적을 남긴다(tests/_db_isolation.py).
        self._iso = _db_isolation.isolated_db()
        self._iso.__enter__()
        self.addCleanup(self._iso.__exit__, None, None, None)
        draw_results_db.init_draw_results_table()

        # 렌더가 외부 응답(동행복권)에 의존하지 않게 조회만 막는다(최대 8초 지연도 방지).
        original_sync = draw_results_db.sync_latest_from_dhlottery
        draw_results_db.sync_latest_from_dhlottery = lambda: None
        self.addCleanup(
            setattr, draw_results_db, "sync_latest_from_dhlottery", original_sync
        )

        for cached in (
            lotto_stats._auto_sync_latest_draw_cached,
            lotto_stats._load_lotto_data_db_cached,
            lotto_stats._number_weights_cached,
        ):
            cached.clear()

        # 일요일 14시대에 이 테스트가 돌면 combo_gen_trigger가 진짜 워커 프로세스를
        # 띄운다(그 프로세스는 격리 밖이라 운영 DB로 나간다) — 그 경로를 막는다.
        import combo_gen_trigger

        original_trigger = combo_gen_trigger.maybe_trigger_weekly_generation
        combo_gen_trigger.maybe_trigger_weekly_generation = lambda: None
        self.addCleanup(
            setattr,
            combo_gen_trigger,
            "maybe_trigger_weekly_generation",
            original_trigger,
        )

    def open_app(self, gid: str, page: str | None = None) -> AppTest:
        """사용자가 주소로 앱을 여는 것과 같은 방식(AppTest가 app.py를 실행)."""
        at = AppTest.from_file(ENTRY, default_timeout=TIMEOUT_SEC)
        if page is not None:
            at.query_params["page"] = page
        at.query_params["gid"] = gid
        at.run()
        return at


class AppDrawDataLiveTests(_LiveAppCase):
    def test_new_round_shows_on_real_entry_without_restart(self):
        """기본 화면 — DB에 새 회차가 들어오면 서버 재시작 없이 화면이 따라온다."""
        draw_results_db.upsert_draw_result(4321, [2, 11, 25, 33, 41, 45], 7)

        at = self.open_app(_fresh_gid("live"))
        self.assertEqual(len(at.exception), 0, f"진입점이 예외로 죽었다: {at.exception}")
        first = _markdown_blob(at)
        self.assertIn(
            "4321회",
            first,
            f"첫 렌더에 최신 회차 표기가 없다 (markdown {len(at.markdown)}개)",
        )

        # 서버는 그대로 둔 채 DB에만 새 회차가 들어온다(관리자 입력/자동 동기화).
        draw_results_db.upsert_draw_result(4322, [1, 5, 9, 13, 17, 21], 23)
        at.run()
        self.assertEqual(len(at.exception), 0, f"재렌더가 예외로 죽었다: {at.exception}")
        second = _markdown_blob(at)
        self.assertIn(
            "4322회",
            second,
            "새 회차가 화면에 반영되지 않았다 — 재시작 전까지 옛 회차가 계속 보이고 있다",
        )


class AppThunderWeightsLiveTests(_LiveAppCase):
    def _render_thunder_spying_on_components_html(self) -> list[str]:
        """번개조합 화면이 components.html로 내려보낸 HTML을 모은다."""
        import streamlit.components.v1 as c1

        seen: list[str] = []
        original = c1.html
        c1.html = lambda html, **kw: (seen.append(html or ""), original(html, **kw))[1]
        try:
            at = self.open_app(_fresh_gid("thw"), page="thunder")
            self.assertEqual(
                len(at.exception), 0, f"번개조합 화면이 예외로 죽었다: {at.exception}"
            )
        finally:
            c1.html = original
        return seen

    def test_thunder_screen_sends_weights_computed_from_current_db(self):
        """번개조합 화면이 내려보내는 numberWeights가 지금 DB 기준인지.

        가중치(get_number_weights)는 조합 추첨의 근거인데, 캐시가 밑줄 인자 때문에
        무효화되지 않던 시절에는 프로세스가 뜬 시점 값이 계속 브라우저로 나갔다.
        """
        draw_results_db.upsert_draw_result(1241, [1, 2, 3, 4, 5, 6], 7)
        draw_results_db.upsert_draw_result(1242, [1, 2, 3, 4, 5, 6], 8)  # 1~6번이 2회 출현

        # AppTest 하네스 특성: 맨 처음 실행에서는 components.html 스파이가 안 잡힌다(예열 1회).
        warm = self.open_app(_fresh_gid("warm"), page="thunder")
        self.assertEqual(len(warm.exception), 0, f"예열 렌더가 예외로 죽었다: {warm.exception}")

        payloads = self._render_thunder_spying_on_components_html()
        self.assertTrue(
            payloads, "components.html 페이로드가 하나도 잡히지 않았다(계측 실패)"
        )

        weights = [p for p in payloads if "const numberWeights" in p]
        self.assertTrue(
            weights,
            f"번개조합 화면이 numberWeights를 내려보내지 않았다(페이로드 {len(payloads)}건)",
        )
        self.assertRegex(
            weights[0],
            r'"1":\s*2',
            "가중치가 지금 DB 기준이 아니다(1~6번이 두 회차 나왔으므로 1번 가중치는 2여야 한다)",
        )


if __name__ == "__main__":
    unittest.main()
