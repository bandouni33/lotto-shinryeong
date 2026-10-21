# -*- coding: utf-8 -*-
"""목·금 구매 전 콘텐츠(2026-10-18 사용자 승인 5번) — 카드 2장 + 문구 + 짧은 영상.

  목(thu) '이번 주 신령 타로'  : 주간 카드 4번과 같은 타로(cards.tarot_for_round) + 앱 설치 카드
  금(fri) '이번 주 번호 흐름'  : 공식 당첨번호로 센 최근 50회 많이 나온 번호 · 가장 오래 안 나온 번호 + 앱 설치 카드
                                 (홈페이지 '번호 통계'와 같은 계산)

결과는 run_weekly 와 같은 모양({회차}_1~2.png · _captions.json · _shorts.mp4)이라 publish.py 가 그대로 올린다
(--kind thu/fri — 게시 기록 키가 '채널:thu' 처럼 달라 토요일 게시와 섞이지 않음).
번호를 '추천'하지 않는다 — 공식 데이터의 사실과 재미(타로)만.

실행: python -m weekly_content.pre_draw --kind thu --out pre_out
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from PIL import ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from weekly_content import cards  # noqa: E402
from weekly_content.cards import GOLD, MUTED, W, WHITE, _ball, _canvas, _center, _panel, font  # noqa: E402

KINDS = ("thu", "fri")


def flow(draws: dict[int, dict], upto: int, window: int = 50) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """최근 window 회 많이 나온 6개(번호, 횟수), 가장 오래 안 나온 6개(번호, 몇 회째)."""
    cnt = {n: 0 for n in range(1, 46)}
    last = {n: 0 for n in range(1, 46)}
    for r in sorted(draws):
        if r > upto:
            break
        for n in draws[r]["nums"]:
            last[n] = r
            if r > upto - window:
                cnt[n] += 1
    hot = sorted(range(1, 46), key=lambda n: (-cnt[n], n))[:6]
    cold = sorted(range(1, 46), key=lambda n: (last[n], n))[:6]
    return [(n, cnt[n]) for n in hot], [(n, upto - last[n]) for n in cold]


def card_flow(draws: dict[int, dict], latest: int) -> "cards.Image.Image":
    hot, cold = flow(draws, latest)
    im = _canvas()
    d = ImageDraw.Draw(im)
    _center(d, 110, f"{latest + 1}회 앞두고", font(60, "Black"), GOLD)
    _center(d, 200, "이번 주 번호 흐름", font(40, "Medium"), WHITE)
    for top, title, nums, subs in ((300, "최근 50회 가장 많이 나온 번호", [n for n, _ in hot], [f"{c}회" for _, c in hot]),
                                   (700, "가장 오래 안 나온 번호", [n for n, _ in cold], [f"{g}회째" for _, g in cold])):
        _panel(im, (80, top, W - 80, top + 340))
        d = ImageDraw.Draw(im)
        _center(d, top + 40, title, font(36, "Bold"), GOLD)
        step = (W - 160) // 6
        for i, n in enumerate(nums):
            cx = 80 + step * i + step // 2
            _ball(im, cx, top + 175, 54, n)
            if subs:
                d = ImageDraw.Draw(im)
                d.text((cx, top + 285), subs[i], font=font(26, "Medium"), fill=MUTED, anchor="mm")
    d = ImageDraw.Draw(im)
    _center(d, 1110, f"1~{latest}회 공식 당첨번호 기준 · 매 회차 모든 번호의 확률은 같습니다", font(26, "Regular"), MUTED)
    cards._footer(im, 1, 2, "로또신령 번호 흐름")
    return im


def _caption_tail(source: str) -> str:
    import social_links

    return (f"\n\n🔎 회차별 당첨번호·번호 통계: {social_links.SITE_URL}/stats/"
            "\n첫 가입 500P로 번호 조합 무료 체험 → 구글 플레이·앱스토어에서 '로또신령'\n"
            f"📲 설치: {social_links.store_link(source, campaign='predraw')}\n"
            f"📖 사용설명서: {social_links.MANUAL_URL}\n"
            "\n※ 참고·재미용 정보이며 당첨을 보장하지 않습니다. 복권은 만 19세 이상.")


def captions(kind: str, draws: dict[int, dict], latest: int) -> dict:
    nxt = latest + 1
    if kind == "thu":
        t = cards.tarot_for_round(latest)
        head = (f"🔮 {nxt}회를 기다리는 이번 주 신령 타로\n\n{t['name']} ({t['name_en']})\n“{t['line']}”\n\n"
                "이번 주 마음은 어떤 카드에 가까운가요? 앱에서 내 카드를 직접 뽑아보세요.")
        tags = f"\n#로또 #로또{nxt}회 #타로 #오늘의타로 #로또신령"
        th_head = f"🔮 {nxt}회 이번 주 신령 타로: {t['name']}\n“{t['line']}”"
    else:
        hot, cold = flow(draws, latest)
        head = (f"📊 {nxt}회 앞두고 보는 번호 흐름(1~{latest}회 공식 당첨번호)\n\n"
                f"최근 50회 가장 많이 나온 번호: {', '.join(f'{n}({c}회)' for n, c in hot)}\n"
                f"가장 오래 안 나온 번호: {', '.join(f'{n}({g}회째)' for n, g in cold)}\n\n"
                "토요일 저녁 8시 판매 마감 전에 확인하세요.")
        tags = f"\n#로또 #로또{nxt}회 #로또번호 #로또통계 #로또신령"
        th_head = (f"📊 {nxt}회 번호 흐름\n많이 나온 번호 {', '.join(str(n) for n, _ in hot)}\n"
                   f"오래 안 나온 번호 {', '.join(str(n) for n, _ in cold)}")
    import social_links

    if kind == "thu":   # 2026-10-18 스레드 = 신령과의 문답: 목요일 질문 → 토요일 결과(cards.caption_threads)
        from weekly_content import number_story

        q = number_story.question(draws, latest)
        th_head = (f"🗳 {nxt}회 신령 문답\n공백기 멤버 중 이번 주 컴백할 번호는?\n"
                   f"후보: {', '.join(map(str, q['candidates']))}\n댓글로 한 명 골라주세요. 토요일 밤 결과 공개!")
    threads = (f"{th_head}\n\n설치: {social_links.store_link('threads', campaign='predraw')}\n"
               "※ 참고·재미용 · 복권은 만 19세 이상\n#로또")[:cards.THREADS_LIMIT]
    return {"instagram": head + _caption_tail("instagram") + tags, "facebook": head + _caption_tail("facebook") + tags,
            "threads": threads, "youtube_title": f"{nxt}회 로또 {'이번 주 신령 타로' if kind == 'thu' else '번호 흐름'} | 로또신령",
            "youtube_description": head + _caption_tail("youtube")}


def build(kind: str, draws: dict[int, dict], latest: int, out: Path) -> list[Path]:
    if kind not in KINDS:
        raise SystemExit(f"[중단] kind 는 {KINDS} 중 하나")
    out.mkdir(parents=True, exist_ok=True)
    label = "로또신령 이번 주 타로" if kind == "thu" else "로또신령 번호 흐름"
    first = (cards.card4(latest, cards.tarot_for_round(latest), foot=(1, 2, label)) if kind == "thu"
             else card_flow(draws, latest))
    imgs = [first, cards.card5("구글 플레이 · 앱스토어", foot=(2, 2, label))]
    tag = latest + 1   # 게시 기록·파일 이름은 '다가오는 회차' 기준
    paths = []
    for i, im in enumerate(imgs, 1):
        p = out / f"{tag}_{i}.png"
        im.save(p, optimize=True)
        paths.append(p)
    (out / f"{tag}_captions.json").write_text(json.dumps(captions(kind, draws, latest), ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    return paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=KINDS)
    ap.add_argument("--out", default="pre_out")
    a = ap.parse_args()
    import draw_results_db
    from weekly_content.run_weekly import make_shorts

    draws = {h["draw_round"]: {"nums": sorted(h["numbers"]), "bonus": h["bonus"]}
             for h in draw_results_db.get_all_draw_results()}
    latest = max(draws)
    out = Path(a.out)
    pngs = build(a.kind, draws, latest, out)
    shorts = make_shorts(pngs, out / f"{latest + 1}_shorts.mp4")
    if shorts:
        from weekly_content import clip_kit

        clip_kit.write(out, latest + 1, a.kind)   # 네이버 클립 수동 업로드용 문구(실행 기록 Artifacts)
    print(f"[완료] {a.kind} {latest + 1}회 카드 {len(pngs)}장 · 쇼츠={'있음' if shorts else '없음'} → {out}")
    return 0


if __name__ == "__main__":
    import traceback
    try:
        code = main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (1 if e.code else 0)
        if not isinstance(e.code, int) and e.code:
            print(e.code)
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
