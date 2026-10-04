"""1·2등 배출 이벤트 배너 — 트리거·1회 노출·닫기 기록의 불변식 (2026-10-04 신규).

무엇을 고정하는가: "가장 최근에 확정된 회차가 1·2등 히트일 때만, 게스트당 회차별 1회,
닫을 때 기록"이라는 성질이다. 예시 하나가 아니라 경계(미확정·rank 0·NULL·이전 회차·다른
게스트·재닫기)에서도 성립하는지 본다.

  B1 1244회차는 하한(WIN_EVENT_BANNER_MIN_ROUND) 미만이라 대상이 아니다(건너뛰기 확정)
  B2 가장 최근 확정 회차가 히트면 그 회차가 대상이다(1등만/2등만/둘 다)
  B3 최신 확정 회차가 히트가 아니면 아무 것도 안 뜬다(지난 주 히트가 뒤늦게 뜨지 않음)
  B4 미확정(추첨 전) 행은 히트로 세지 않는다 — 0으로 못 박지 않는 원칙과 같은 선
  B5 rank가 0이거나 NULL이면 비히트
  B6 닫기 기록은 멱등이고 회차별·게스트별로 분리된다
  B7 기록 위치는 기존 패턴 그대로 guest_update_notice의 "win_event:{회차}" 키
  B8 문구는 확정된 B안 고정("필터 통과 조합 기준" 명시) + 버튼은 2개(이동 버튼 없음)
  B9 샘플 HTML과 화면이 같은 CSS를 쓴다(이중 구현 방지) + 샘플에 번호가 큼지막하게 있다

실행: venv312\\Scripts\\python.exe -X utf8 tests\\test_win_event_banner.py
"""

import sys
import re
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for _path in (str(ROOT), str(TESTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _db_isolation  # noqa: E402
import dialog_registry  # noqa: E402
import marketing_db as mdb  # noqa: E402
import win_event_banner as web  # noqa: E402

HIT_ROUND = mdb.WIN_EVENT_BANNER_MIN_ROUND  # 1245
NEXT_ROUND = HIT_ROUND + 1


class WinEventBannerTests(unittest.TestCase):
    def setUp(self):
        self._iso = _db_isolation.isolated_db()
        self._iso.__enter__()
        self.addCleanup(self._iso.__exit__, None, None, None)
        mdb.init_marketing_tables()

    # ── 헬퍼 ───────────────────────────────────────────────────────────
    def _finalize_with_ranks(self, draw_round, ranks, *, stage4=None, pattern=6465):
        """참고등수를 기록하고 스냅샷 → 확정까지 (운영과 같은 경로)."""
        mdb.set_reference_ranks(draw_round, ranks)
        mdb.snapshot_round_stats(draw_round, pattern)
        self.assertTrue(mdb.finalize_round_stats(draw_round))
        if stage4 is not None:
            mdb.record_draw_generation_stats(draw_round, 2_000_000, stage4, (34, 14, 45, 33, 40))

    def _rows(self, guest_id, draw_round):
        conn = mdb._connect()
        rows = conn.execute(
            "SELECT version, last_shown_date FROM guest_update_notice WHERE guest_id = ?",
            (guest_id,),
        ).fetchall()
        conn.close()
        return rows

    # B1 하한 (2026-10-04 재확정: 1244회차부터 노출)
    def test_B1_rounds_below_floor_are_never_targets(self):
        self.assertEqual(mdb.WIN_EVENT_BANNER_MIN_ROUND, 1244, "하한은 1244로 확정됐다(1244부터 노출)")
        # 1243은 하한(1244) 미만 - 히트여도 대상이 아니어야 한다.
        mdb.set_reference_ranks(1243, (0, 1, 18, 169, 1157))
        mdb.snapshot_round_stats(1243, 6465)
        self.assertTrue(mdb.finalize_round_stats(1243))
        self.assertIsNone(mdb.get_latest_win_event_round())

    def test_B1_1244_is_now_a_target(self):
        """재확정: 1244회차부터 노출. 실제 2등 히트인 1244가 대상이 된다."""
        mdb.set_reference_ranks(1244, (0, 1, 18, 169, 1157))
        mdb.snapshot_round_stats(1244, 6465)
        self.assertTrue(mdb.finalize_round_stats(1244))
        info = mdb.get_latest_win_event_round()
        self.assertIsNotNone(info)
        self.assertEqual(info["draw_round"], 1244)
        self.assertEqual(info["rank_2"], 1)

    # ── B2 히트 판정 ──────────────────────────────────────────────────
    def test_B2_latest_finalized_hit_is_the_target(self):
        self._finalize_with_ranks(HIT_ROUND, (0, 1, 18, 169, 1157), stage4=939_330)
        info = mdb.get_latest_win_event_round()
        self.assertIsNotNone(info)
        self.assertEqual(info["draw_round"], HIT_ROUND)
        self.assertEqual((info["rank_1"], info["rank_2"], info["rank_3"]), (0, 1, 18))
        self.assertEqual(info["stage4_count"], 939_330)

    def test_B2_rank_1_alone_is_enough(self):
        self._finalize_with_ranks(HIT_ROUND, (1, 0, 0, 0, 0))
        info = mdb.get_latest_win_event_round()
        self.assertIsNotNone(info, "1등만 나도 대상이다(둘 다 필요 없음)")
        self.assertEqual(info["rank_1"], 1)

    # ── B3 최신 확정 회차 기준 ────────────────────────────────────────
    def test_B3_not_a_hit_when_newest_finalized_round_is_clean(self):
        self._finalize_with_ranks(HIT_ROUND, (0, 1, 18, 169, 1157))
        self._finalize_with_ranks(NEXT_ROUND, (0, 0, 0, 5, 12))
        self.assertIsNone(
            mdb.get_latest_win_event_round(),
            "더 최신 확정 회차가 히트가 아니면 지난 주 히트가 뒤늦게 뜨면 안 된다",
        )

    def test_B3_newer_hit_supersedes_the_older_one(self):
        self._finalize_with_ranks(HIT_ROUND, (0, 1, 0, 0, 0))
        self._finalize_with_ranks(NEXT_ROUND, (0, 0, 2, 0, 0))
        self.assertIsNone(mdb.get_latest_win_event_round(), "2등 미만은 히트가 아니다")

        older = HIT_ROUND
        newer = NEXT_ROUND + 1
        self._finalize_with_ranks(newer, (0, 3, 0, 0, 0))
        info = mdb.get_latest_win_event_round()
        self.assertEqual(info["draw_round"], newer, "가장 최근 히트 회차가 대상이다")
        self.assertGreater(newer, older)

    # ── B4 미확정 행 ──────────────────────────────────────────────────
    def test_B4_unfinalized_rows_are_not_hits(self):
        mdb.set_reference_ranks(HIT_ROUND, (1, 1, 1, 1, 1))
        mdb.snapshot_round_stats(HIT_ROUND, 6465)
        # finalize 하지 않았다 = 아직 추첨 전(운영에서 1245가 이 상태)
        self.assertIsNone(mdb.get_latest_win_event_round())
        self.assertTrue(mdb.finalize_round_stats(HIT_ROUND))
        self.assertIsNotNone(mdb.get_latest_win_event_round(), "확정되면 그때 대상이 된다")

    # ── B5 0 / NULL 경계 ──────────────────────────────────────────────
    def test_B5_zero_ranks_are_not_hits(self):
        self._finalize_with_ranks(HIT_ROUND, (0, 0, 0, 0, 0))
        self.assertIsNone(mdb.get_latest_win_event_round())

    def test_B5_null_ranks_are_treated_as_zero(self):
        mdb.snapshot_round_stats(HIT_ROUND, 6465)
        conn = mdb._connect()
        conn.execute(
            "UPDATE combo_round_stats SET finalized_at = ? WHERE draw_round = ?",
            ("2026-10-04T00:00:00", HIT_ROUND),  # 확정 표시만 하고 등수는 NULL로 둔다
        )
        conn.commit()
        conn.close()
        self.assertIsNone(mdb.get_latest_win_event_round(), "NULL 등수는 0으로 취급")

    # ── B6 닫기 기록 ──────────────────────────────────────────────────
    def test_B6_close_record_is_idempotent_and_scoped(self):
        guest = "guest-a"
        self.assertFalse(mdb.was_win_event_banner_closed(guest, HIT_ROUND))
        mdb.mark_win_event_banner_closed(guest, HIT_ROUND)
        mdb.mark_win_event_banner_closed(guest, HIT_ROUND)  # 두 번 닫아도
        self.assertTrue(mdb.was_win_event_banner_closed(guest, HIT_ROUND))
        self.assertEqual(len(self._rows(guest, HIT_ROUND)), 1, "행은 1개(멱등)")

        self.assertFalse(
            mdb.was_win_event_banner_closed(guest, NEXT_ROUND),
            "회차가 다르면 별개다(새 히트 회차는 다시 뜬다)",
        )
        self.assertFalse(
            mdb.was_win_event_banner_closed("guest-b", HIT_ROUND),
            "게스트가 다르면 별개다",
        )

    # ── B7 기록 위치(기존 패턴 재사용) ────────────────────────────────
    def test_B7_record_reuses_guest_update_notice_with_round_key(self):
        mdb.mark_win_event_banner_closed("guest-a", HIT_ROUND)
        rows = self._rows("guest-a", HIT_ROUND)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], f"win_event:{HIT_ROUND}")
        self.assertTrue(rows[0][1], "닫은 시각이 기록된다")

    def test_B7_banner_key_is_per_round(self):
        self.assertEqual(web.__dict__["DIALOG_NAME"], "win_event_banner")
        self.assertNotEqual(
            mdb._win_event_banner_key(HIT_ROUND), mdb._win_event_banner_key(NEXT_ROUND)
        )

    # ── B8 문구·버튼 (확정 B안) ───────────────────────────────────────
    def test_B8_copy_is_minimal_only_hit_ranks(self):
        """재확정 문구(2026-10-04): 배출 등수만 간략 표기 · 조합수량 뺄 것 · 미사여구 없음."""
        info = {
            "draw_round": HIT_ROUND,
            "rank_1": 0,
            "rank_2": 1,
            "rank_3": 18,
            "rank_4": 169,
            "rank_5": 1157,
            "stage4_count": 939_330,
        }
        card = web.card_html(info)
        self.assertIn(f"{HIT_ROUND}회차 결과 — 2등 배출", card)
        self.assertIn("필터 통과 조합 기준", card)
        self.assertIn("2등 1개 · 3등 18개", card)
        self.assertNotIn("939,330", card, "조합수량은 문구에서 뺐다")
        self.assertNotIn("1,025,190", card)
        self.assertNotIn("1등 0개", card, "미배출 등수는 표기하지 않는다")
        self.assertNotIn("4등", card, "1~3등까지만 표기")
        self.assertNotIn("5등", card)
        self.assertNotIn("나왔습니다", card, "미사여구 없이 등수만")
        self.assertNotIn("참고 통계", card)
        self.assertEqual((web.BTN_NEVER, web.BTN_OK), ("다시 보지 않기", "확인"))

    def test_B8_title_label_follows_which_rank_hit(self):
        base = {"draw_round": HIT_ROUND, "rank_3": 5, "rank_4": 0, "rank_5": 0,
                "stage4_count": None}
        self.assertIn("1·2등 배출", web.card_html(dict(base, rank_1=1, rank_2=2)))
        self.assertIn("1등 배출", web.card_html(dict(base, rank_1=1, rank_2=0)))
        self.assertIn("2등 배출", web.card_html(dict(base, rank_1=0, rank_2=3)))

    def test_B8_combination_count_never_appears_even_when_known(self):
        """조합수량은 알더라도 화면 문구에는 절대 넣지 않는다(확정)."""
        info = {"draw_round": HIT_ROUND, "rank_1": 0, "rank_2": 1, "rank_3": 0,
                "rank_4": 0, "rank_5": 0, "stage4_count": 1_025_190}
        card = web.card_html(info)
        self.assertNotIn("1,025,190", card)
        self.assertIn("2등 1개", card)
        self.assertNotIn("3등 0개", card, "0인 등수는 빼고 표기")

    # ── B9 샘플과 화면의 단일 구현 ────────────────────────────────────
    def test_B9_sample_shares_the_same_style_as_the_screen(self):
        info = {"draw_round": HIT_ROUND, "rank_1": 0, "rank_2": 1, "rank_3": 18,
                "rank_4": 169, "rank_5": 1157, "stage4_count": 939_330}
        for style_id in web.STYLES:
            sample = web.sample_html(style_id, info)
            self.assertIn(f"샘플 {style_id}", sample, "번호가 파일 안에 큼지막하게 있다")
            self.assertIn(web.style_css(style_id), sample, "샘플과 화면이 같은 CSS를 쓴다")
            self.assertIn("2등 1개 · 3등 18개", sample)

    def test_B8_card_is_rendered_in_an_iframe_not_markdown(self):
        """실기기 신고(태그가 글자로 보임) 재발 방지 — 카드는 iframe(components.html)로 그린다."""
        src = (ROOT / "win_event_banner.py").read_text(encoding="utf-8")
        self.assertIn("components.html(card_iframe_html(info)", src)
        self.assertNotIn(
            "st.markdown(card_html(info)",
            src,
            "카드를 st.markdown HTML로 그리면 환경에 따라 태그가 글자로 노출된다",
        )

    def test_B8_iframe_document_carries_the_card_and_the_copy(self):
        info = {"draw_round": HIT_ROUND, "rank_1": 0, "rank_2": 1, "rank_3": 18,
                "rank_4": 169, "rank_5": 1157, "stage4_count": 1_025_190}
        doc = web.card_iframe_html(info)
        self.assertTrue(doc.startswith("<!doctype html>"))
        self.assertIn("background: transparent", doc, "창 배경을 해치지 않게 투명")
        self.assertIn("wev-card", doc)
        self.assertIn(web.style_css(web.CHOSEN_STYLE), doc, "확정 스타일 CSS가 들어 있다")
        self.assertIn(f"{HIT_ROUND}회차 결과 — 2등 배출", doc)
        self.assertIn("필터 통과 조합 기준", doc)
        self.assertIn("2등 1개 · 3등 18개", doc)
        self.assertNotIn("1,025,190", doc)

    def test_B8_iframe_reports_its_own_height(self):
        """창이 필요 이상으로 커지지 않게 — 내용 높이를 부모에 알려 프레임을 줄인다.

        2026-10-04 신고(배너창이 너무 크고 빈 공간이 많다) 대응: 고정 200px를 쓰지 않고
        신령 이미지 블록과 같은 방식(streamlit:setFrameHeight)으로 높이를 보고한다.
        """
        info = {"draw_round": HIT_ROUND, "rank_1": 0, "rank_2": 1, "rank_3": 18,
                "rank_4": 0, "rank_5": 0, "stage4_count": None}
        doc = web.card_iframe_html(info)
        self.assertIn("streamlit:setFrameHeight", doc)
        self.assertIn("document.body.scrollHeight", doc)
        self.assertLessEqual(web.CARD_IFRAME_HEIGHT, 130, "초기값(폴백)도 작게")
        src = (ROOT / "win_event_banner.py").read_text(encoding="utf-8")
        self.assertNotIn("height=200", src, "고정 200px로 되돌아가지 않았는지")

    def test_B8_card_stays_compact(self):
        """빈 공간을 만들던 값들(큰 패딩·여백)이 다시 커지지 않게 숫자로 못 박는다."""
        css = web.style_css(web.CHOSEN_STYLE)
        self.assertIn("padding: 12px 14px 10px;", css, "카드 안쪽 여백은 최소")
        self.assertIn("padding: 2px;", css, "테두리 링도 얇게")
        self.assertIn("font-size: 17px;", css)
        self.assertIn("margin-bottom: 6px;", css)

    def test_B8_shine_sweeps_continuously_until_the_banner_closes(self):
        """빛 사선이 계속 지나간다(닫기 전까지) + 모바일에서 부각되게 강화된 상태를 고정.

        2026-10-04 지시: 모바일 화면에서 빛이 잘 안 보인다 → 더 부각 + 계속 반복.
        창이 닫히면 이 모듈 자체가 사라지므로 infinite 는 곧 "닫기 전까지"와 같다.
        """
        css = web.style_css(2)  # 확정 스타일(네온)
        self.assertEqual(web.SHINE_SECONDS, 13.6, "6.8s에서 한 번 더 50%% 감속한 값")
        self.assertIn(f"animation: wevShine {web.SHINE_SECONDS:g}s", css)
        self.assertIn("infinite", css, "한 번이 아니라 계속 반복되어야 한다")
        for faster in ("3.4s", "6.8s"):
            self.assertNotIn(
                f"animation: wevShine {faster}",
                css,
                f"{faster}는 감속 지시 전 값이다 — 되돌아가면 다시 빠르다",
            )
        self.assertNotIn(
            "animation: wevShine 1.5s ease-out .35s 1 both",
            css,
            "1회짜리로 되돌아가면 모바일에서 다시 안 보인다",
        )
        self.assertIn("mix-blend-mode: screen", css, "어두운 배경 위에서 빛이 부각되게")
        self.assertIn("rgba(255,255,255,.98) 50%", css, "중심 광량(부각)")
        self.assertIn("width: 70%", css, "사선 폭을 넓혀 작은 화면에서도 보이게")

    def test_B8_quiet_style_keeps_the_shine_off(self):
        """반짝임 없는 스타일(3 미니멀)은 그대로 꺼져 있어야 한다."""
        self.assertIn(".wev-shine{display:none;}", web.style_css(3))
        self.assertNotIn("wevShine 2.8s", web.style_css(3))

    def test_B8_shine_crosses_the_whole_card(self):
        """빛 사선이 중간에서 꺼지지 않고 **오른쪽 끝을 지나서** 나가야 한다(2026-10-04 지시).\n\n        이전엔 불투명도가 62%에서 0이 돼 중간에서 사라졌다(신고: 중간까지만 오다 끝남).\n        """
        css = web.style_css(2)
        self.assertIn("translateX(-190%)", css, "왼쪽 밖에서 시작")
        self.assertIn("translateX(230%)", css, "오른쪽 밖으로 퇴장")
        self.assertIn("88%  { opacity: 1; }", css, "지나가는 동안 밝기를 유지")
        self.assertNotIn("62%  { opacity: 0; }", css, "중간에 꺼지는 동작으로 되돌아가지 않았는지")
        self.assertIn(f"wevShine {web.SHINE_SECONDS:g}s", css)
        self.assertIn("infinite", css, "창이 닫힐 때까지 계속")

    # ── 눈 내리듯 흘날리는 폭죽(2026-10-04 재지시) ─────────────────────
    def _particles(self, doc):
        return re.findall(r'<span class="wev-p" style="([^"]+)"', doc)

    def _vars(self, particle: str) -> dict:
        return dict(re.findall(r"--([a-z]+):([^;\"]+)", particle))

    def _card_doc(self) -> str:
        info = {"draw_round": HIT_ROUND, "rank_1": 0, "rank_2": 1, "rank_3": 18,
                "rank_4": 0, "rank_5": 0, "stage4_count": None}
        return web.card_iframe_html(info)

    def test_B8_confetti_duration_is_halved_again(self):
        """폭죽 낙하도 한 번 더 50%% 감속됐다(5.2s → 10.4s 기준, 입자별로 흘어짐)."""
        css = web.style_css(2)
        self.assertEqual(web.FALL_BASE_SECONDS, 10.4, "5.2s의 두 배")
        self.assertIn("animation: wevFall var(--dur) linear var(--d) infinite", css,
                      "계속 떨어져야 한다(입자마다 --dur로 다른 속도)")
        self.assertIn("background: var(--c)", css, "색종이는 입자마다 색을 받는다")
        for faster in ("wevFall 5.2s", "wevFall 2.6s"):
            self.assertNotIn(faster, css, f"{faster}는 감속 전 값이다")
        self.assertIn("wevTwinkle 2.6s", css, "반짝임은 filter로 남는다")
        self.assertIn("filter: brightness", css, "반짝임이 opacity를 건드리면 낙하 끝의 사라짐이 무효가 된다")

    def test_B8_confetti_scatters_like_snow(self):
        """입자마다 자리·시작·속도·흔들림·회전·크기·밝기가 **전부** 달라야 눈처럼 보인다.

        예전엔 (i*7)%%92 좌표에 다 같이 떨어져 "줄 세운 막대"처럼 보였다.
        """
        doc = self._card_doc()
        ps = self._particles(doc)
        count = int(web.STYLES[2]["particles"])
        self.assertEqual(len(ps), count)
        xs, durs, sways, rots, sizes, ops = [], [], [], [], set(), []
        for p in ps:
            v = self._vars(p)
            for key in ("x", "d", "dur", "o", "sx", "r", "w", "h", "c"):
                self.assertIn(key, v, f"입자에 --{key}가 없다: {p}")
            self.assertTrue(v["c"].startswith("#"), "색을 받는다")
            x, d, dur = float(v["x"][:-1]), float(v["d"][:-1]), float(v["dur"][:-1])
            xs.append(x)
            durs.append(dur)
            sways.append(float(v["sx"][:-2]))
            rots.append(v["r"])
            ops.append(float(v["o"]))
            sizes.add((v["w"], v["h"]))
            self.assertGreaterEqual(x, 0.0)
            self.assertLessEqual(x, 100.0)
            self.assertGreaterEqual(d, 0.0)
            self.assertLessEqual(d, web.FALL_BASE_SECONDS)
            self.assertGreaterEqual(dur, web.FALL_BASE_SECONDS * 0.85 - 1e-9)
            self.assertLessEqual(dur, web.FALL_BASE_SECONDS * 1.25 + 1e-9)
            self.assertGreaterEqual(ops[-1], 0.55)
            self.assertLessEqual(ops[-1], 1.0)
        self.assertEqual(len(set(xs)), count, "가로 위치가 겹치면 줄 세운 것과 같다")
        self.assertGreater(len(set(durs)), 1, "낙하 시간이 제각각이어야 눈처럼 보인다")
        self.assertTrue(any(s < 0 for s in sways) and any(s > 0 for s in sways),
                        "좌우로 어긋나야 뒤죽박죽으로 보인다")
        self.assertGreater(len(set(rots)), 1)
        self.assertGreater(len(sizes), 1, "크기도 달라야 한다")
        self.assertGreaterEqual(len(set(ops)), 2, "밝기도 달라야 한다")

    def test_B8_confetti_uses_several_colors(self):
        doc = self._card_doc()
        colors = {c for c in web.CONFETTI_COLORS if f"--c:{c}" in doc}
        self.assertGreaterEqual(len(colors), 3, f"여러 색이 섞여야 폭죽처럼 보인다: {colors}")
        self.assertGreaterEqual(int(web.STYLES[2]["particles"]), 10, "확정 스타일에는 폭죽이 있어야")

    def test_B8_particle_layout_is_deterministic_and_style_scoped(self):
        """같은 입력이면 같은 배치(렌더마다 눈송이가 요동치면 화면이 매번 달라진다)."""
        self.assertEqual(web._particles_html(2, 14), web._particles_html(2, 14))
        self.assertNotEqual(web._particles_html(2, 14), web._particles_html(2, 10))
        self.assertNotEqual(web._particles_html(2, 14), web._particles_html(1, 14))
        self.assertEqual(web._particles_html(2, 0), "", "0개면 빈 문자열")
        self.assertEqual(web._particles_html(3, 0), "", "입자 없는 스타일은 빈 문자열")

    def test_B8_dialog_chrome_is_centered_tight_and_one_row(self):
        """창 틀도 손본다 — 제목 가운데 · 버튼 한 줄 · 여백 최소(2026-10-04 지시).

        규칙은 이 창 본문 컨테이너(.st-key-win_event_banner_body)를 품은 다이얼로그로만
        좁혀 다른 안내창(적립금·충전·내정보)에 번지지 않게 한다.
        """
        src = (ROOT / "win_event_banner.py").read_text(encoding="utf-8")
        self.assertIn('div[data-testid="stDialog"]:has(.st-key-win_event_banner_body)',
                      web.DIALOG_SCOPE, "다이얼로그 규칙은 이 창으로만 좁힌다")
        self.assertIn('st.container(key="win_event_banner_body")', src, "기준점 컨테이너가 실제로 있어야")
        self.assertIn("{DIALOG_CSS}", src, "창 틀 CSS는 DIALOG_CSS 단일 구현을 쓴다(사본 금지)")
        self.assertEqual(src.count("flex-wrap: nowrap !important"), 1, "규칙을 복사해 두 곳에 두지 않는다")
        self.assertIn("text-align: center !important;", web.DIALOG_CSS, "제목 가운데 정렬")
        self.assertIn("flex-wrap: nowrap !important;", web.DIALOG_CSS, "버튼 두 개를 한 줄로")
        self.assertIn("width: 50% !important;", web.DIALOG_CSS, "버튼 열 폭 고정(줄바꿈 방지)")
        self.assertIn("min-width: 0 !important;", web.DIALOG_CSS,
                      "Streamlit의 좁은 화면 규칙(min-width: calc(100% - 24px))을 이겨야 한 줄이 된다")
        self.assertIn("padding: 4px 10px 6px !important;", web.DIALOG_CSS, "창 안쪽 여백 최소")
        self.assertIn("padding: 0 !important;", web.DIALOG_CSS, "제목 자체 여백 제거(계측: 63px → 27px)")
        self.assertIn("white-space: nowrap !important;", web.DIALOG_CSS, "버튼 글씨 줄바꿈 방지")

    def test_B8_emitted_css_has_no_doubled_braces(self):
        """2026-10-04 사고 재발 방지 — 문자열에 CSS를 넣을 때 중괄호를 두 번 쓰면
        (`{{ padding: ... }}`) 브라우저가 그걸 CSS 중첩으로 보고 **규칙을 통째로 버린다**.

        실제로 그렇게 새서 실기기에 "제목 왼쪽 정렬 · 버튼 두 줄"이 그대로 남았다.
        """
        subjects = {
            "DIALOG_CSS": web.DIALOG_CSS,
            "style_css(1)": web.style_css(1),
            "style_css(2)": web.style_css(2),
            "style_css(3)": web.style_css(3),
            "style_css(4)": web.style_css(4),
            "card_iframe_html": self._card_doc(),
            "sample_html": web.sample_html(2, {"draw_round": HIT_ROUND, "rank_1": 0, "rank_2": 1,
                                               "rank_3": 0, "rank_4": 0, "rank_5": 0,
                                               "stage4_count": None}),
        }
        for name, text in subjects.items():
            self.assertNotIn("{{", text, f"{name}에 이중 중괄호가 있다(규칙이 버려진다)")
            self.assertNotIn("}}", text, f"{name}에 이중 중괄호가 있다(규칙이 버려진다)")
            self.assertEqual(text.count("{"), text.count("}"), f"{name}의 중괄호 짝이 안 맞는다")
        for chunk in web.DIALOG_CSS.split("}"):
            if chunk.strip():
                self.assertIn("!important", chunk, "창 틀 규칙은 Streamlit 기본값을 이겨야 한다")

    def test_B9_every_style_is_distinct(self):
        css = [web.style_css(style_id) for style_id in web.STYLES]
        for style_id in web.STYLES:
            self.assertIn(style_id, web.STYLES)
        self.assertEqual(len(set(css)), len(css), "스타일마다 CSS가 달라야 샘플이 의미 있다")
        particles = {style_id: web.STYLES[style_id]["particles"] for style_id in web.STYLES}
        self.assertTrue(any(int(v) == 0 for v in particles.values()), "입자 없는 버전이 하나는 있어야")

    # ── 등록(기준점) ──────────────────────────────────────────────────
    def test_registry_entry_and_logout_cleanup(self):
        spec = dialog_registry.DIALOGS["win_event_banner"]
        self.assertEqual(spec.flag, "win_event_banner")
        self.assertEqual(spec.consumer, "win_event_banner.py")
        self.assertIn(spec.flag, (ROOT / spec.consumer).read_text(encoding="utf-8"))
        self.assertIn(spec.flag, dialog_registry.logout_keys())
        self.assertFalse(spec.resume_caller, "로그인 재개와 무관한 창이다")

    def test_agents_md_lists_the_banner(self):
        body = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("win_event_banner", body)

    def test_chosen_style_is_the_selected_sample(self):
        self.assertEqual(web.CHOSEN_STYLE, 2, "구름님이 고른 스타일(샘플 2 · 네온)")
        self.assertEqual(web.STYLES[web.CHOSEN_STYLE]["name"], "네온")

    def test_user_page_calls_it_only_on_main(self):
        body = (ROOT / "user_page.py").read_text(encoding="utf-8")
        self.assertIn("maybe_show_win_event_banner()", body)
        head = body[: body.index("maybe_show_win_event_banner()")]
        flags = [
            line for line in head.splitlines() if line.strip().startswith('if current_page == "main"')
        ]
        self.assertTrue(flags, "메인화면 분기 안에서만 불러야 한다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
