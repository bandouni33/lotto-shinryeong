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
    _center(d, 1110, f"1~{latest}회 공식 당첨번호 기준", font(26, "Regular"), MUTED)   # 2026-10-24: 참고사항 문구 제외
    cards._footer(im, 1, 2, "로또신령 번호 흐름")
    return im


def captions(kind: str, draws: dict[int, dict], latest: int) -> dict:
    """2026-10-22 개편(사용자 지시 — 호기심·감성 훅, 홈페이지 활용, 검색 키워드):
    첫 줄은 감정(타로 문장)·시간 압박(판매 마감) 같은 훅, 가운데는 데이터 '사실'(번호를 추천하지 않는다),
    끝은 댓글로 답할 수 있는 질문. 링크·해시태그·고지는 sns_copy 한 곳."""
    from weekly_content import sns_copy as sc

    nxt = latest + 1
    if kind == "thu":
        # 2026-10-24 사용자 컨셉: 5장(타로·자동·번개·검증·고급필터) 문구를 그대로 본문으로 — 장 문구와 항상 일치
        from weekly_content import thursday

        icons = ["🔮", "💎", "⚡", "🛡", "👑"]
        pages = [thursday.page_text(i, nxt) for i in range(thursday.TOTAL)]
        h1, b1 = pages[0]
        head = (f"{icons[0]} {' '.join(h1)}\n{' '.join(b1)}\n\n" +
                "\n\n".join(f"{icons[i]} {' '.join(h)}\n{' '.join(bd)}" for i, (h, bd) in enumerate(pages[1:], 1)) +
                "\n\n👇 여러분은 이번 주 번호를 어떻게 고르세요? 댓글로 알려주세요.")
        groups, path, what = (sc.KW_TAROT, sc.KW_DRAW, sc.KW_STATS), "/manual/", "기능별 사용설명서"
        # 2026-10-24(사용자 지시): 스레드도 5장 컨셉 — 각 장 질문만 짧게(500자 제한)
        th_head = "\n".join(f"{icons[i]} {' '.join(h)}" for i, (h, _) in enumerate(pages)) + \
            "\n\n넘겨서 보세요 → 여러분은 번호를 어떻게 고르세요? 댓글로!"
    else:
        hot, cold = flow(draws, latest)
        head = (f"⏰ {nxt}회 판매 마감은 토요일 저녁 8시. 번호 고르기 전에 30초만 보세요.\n\n"
                f"🔥 최근 50회 가장 많이 나온 번호: {', '.join(f'{n}({c}회)' for n, c in hot)}\n"
                f"🧊 가장 오래 잠든 번호: {', '.join(f'{n}({g}회째)' for n, g in cold)}\n\n"
                "자주 나온 번호를 믿나요, 오래 쉰 번호를 믿나요?\n"
                "👇 댓글로 🔥 또는 🧊 하나만 남겨주세요.\n"
                "내 번호가 1회부터 지금까지 몇 번 나왔는지는 홈페이지 '번호 통계'에서 바로 확인돼요.")
        groups, path, what = (sc.KW_STATS, sc.KW_DRAW, sc.KW_TIME), "/stats/", "번호 통계"
        th_head = (f"⏰ {nxt}회 판매 마감 토 20:00\n"
                   f"🔥 많이 나온 번호 {', '.join(str(n) for n, _ in hot)}\n"
                   f"🧊 오래 잠든 번호 {', '.join(str(n) for n, _ in cold)}\n\n"
                   "당신은 🔥파? 🧊파? 댓글로!")
    out = {c: f"{head}\n\n{sc.footer(c, path, what)}\n{sc.hashtags(nxt, *groups, channel=c)}"
           for c in ("instagram", "facebook")}
    out["threads"] = f"{th_head}\n\n{sc.footer('threads', path)}\n{sc.hashtags(nxt, channel='threads')}"[:cards.THREADS_LIMIT]
    out["youtube_title"] = f"{nxt}회 로또 {'이번 주 신령 타로' if kind == 'thu' else '번호 흐름'} | 로또신령"
    out["youtube_description"] = f"{head}\n\n{sc.footer('youtube', path, what)}"
    return out


def build(kind: str, draws: dict[int, dict], latest: int, out: Path) -> list[Path]:
    if kind not in KINDS:
        raise SystemExit(f"[중단] kind 는 {KINDS} 중 하나")
    out.mkdir(parents=True, exist_ok=True)
    if kind == "thu":   # 2026-10-24 사용자 컨셉: 앱 화면 5장 + 문구(매주 변형) — weekly_content/thursday.py
        from weekly_content import thursday

        imgs = thursday.build(latest + 1)
    else:
        imgs = [card_flow(draws, latest), cards.card5("구글 플레이 · 앱스토어", foot=(2, 2, "로또신령 번호 흐름"))]
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
    shorts = make_shorts(pngs, out / f"{latest + 1}_shorts.mp4", medley=(a.kind == "thu"), ppt=(a.kind == "thu"))
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
