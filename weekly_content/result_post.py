# -*- coding: utf-8 -*-
"""'결과 정리' 게시물 — 공식 발표 뒤 1등 당첨자 수·금액·1등 명당(2026-10-18 승인 3번).

토요일 즉시 게시(캡처 번호)엔 '동행복권 집계중'으로 나가고, 공식 결과가 나오면 이 게시물이 따로 한 번 올라간다
(publish.py --kind result, 기록 키 '채널:result'). 카드 2장: ① 등수별 당첨 ② 1등 판매점(명당) 목록.

실행: python -m weekly_content.result_post --out result_out [--round N]
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
from weekly_content.cards import GOLD, MUTED, W, WHITE, _canvas, _center, _panel, font  # noqa: E402
from weekly_content.round_result import eok  # noqa: E402

LABEL = "로또신령 추첨결과"


def card_ranks(res: dict) -> "cards.Image.Image":
    rnd, r1 = res["round"], res["ranks"][0]
    im = _canvas()
    d = ImageDraw.Draw(im)
    _center(d, 110, f"{rnd}회 추첨결과", font(60, "Black"), GOLD)
    _panel(im, (80, 190, W - 80, 520))
    d = ImageDraw.Draw(im)
    _center(d, 240, "1등", font(36, "Bold"), MUTED)
    _center(d, 320, f"{r1['count']}명", font(84, "Black"), WHITE)
    _center(d, 420, f"1명당 {eok(r1['amount'])}", font(42, "Bold"), GOLD)
    kinds = " · ".join(f"{k} {v}" for k, v in res["first_kinds"].items())
    if kinds:
        _center(d, 478, kinds, font(30, "Medium"), MUTED)
    y = 580
    for r in res["ranks"][1:]:
        _panel(im, (80, y, W - 80, y + 110), radius=20)
        d = ImageDraw.Draw(im)
        d.text((130, y + 55), f"{r['rank']}등", font=font(36, "Bold"), fill=GOLD, anchor="lm")
        d.text((330, y + 55), f"{r['count']:,}명", font=font(36, "Bold"), fill=WHITE, anchor="lm")
        d.text((W - 130, y + 55), eok(r["amount"]), font=font(34, "Medium"), fill=WHITE, anchor="rm")
        y += 130
    if res.get("sales"):
        _center(d, y + 30, f"총 판매액 {eok(res['sales'])}", font(28, "Medium"), MUTED)
    cards._footer(im, 1, 2, LABEL)
    return im


def card_shops(res: dict) -> "cards.Image.Image":
    rnd, shops = res["round"], res["first_shops"]
    im = _canvas()
    d = ImageDraw.Draw(im)
    _center(d, 110, f"{rnd}회 1등 명당", font(60, "Black"), GOLD)
    top = ", ".join(f"{k} {v}곳" for k, v in res["first_regions"][:4])
    _center(d, 190, top, font(32, "Medium"), WHITE)
    show = shops[:13]
    y = 250
    _panel(im, (60, y, W - 60, y + 66 * len(show) + 30))
    d = ImageDraw.Draw(im)
    y += 30
    for s in show:
        d.text((100, y + 22), s["region"], font=font(28, "Bold"), fill=GOLD, anchor="lm")
        name = s["name"] if len(s["name"]) <= 16 else s["name"][:15] + "…"
        d.text((210, y + 22), name, font=font(30, "Bold"), fill=WHITE, anchor="lm")
        d.text((W - 100, y + 22), s["kind"], font=font(26, "Medium"), fill=MUTED, anchor="rm")
        y += 66
    if len(shops) > len(show):
        _center(d, y + 30, f"외 {len(shops) - len(show)}곳 — 전체는 홈페이지 회차 페이지에서", font(28, "Medium"), MUTED)
    cards._footer(im, 2, 2, LABEL)
    return im


def captions(res: dict) -> dict:
    rnd, r1 = res["round"], res["ranks"][0]
    kinds = ", ".join(f"{k} {v}" for k, v in res["first_kinds"].items())
    regions = ", ".join(f"{k} {v}곳" for k, v in res["first_regions"][:5])
    lines = "\n".join(f"{r['rank']}등 {r['count']:,}명 · {eok(r['amount'])}" for r in res["ranks"][1:])
    shops = "\n".join(f"· {s['region']} {s['name']} ({s['kind']})" for s in res["first_shops"][:16])

    from weekly_content import sns_copy as sc

    net = sc.net_prize(r1["amount"])
    # 2026-10-22: 첫 줄 훅 = '세금 떼면 얼마?'(홈페이지 실수령액 계산기와 같은 식) · 링크·해시태그는 sns_copy 한 곳
    head = (f"💰 제{rnd}회 로또 1등 {r1['count']}명, 1명당 {eok(r1['amount'])}.\n"
            f"세금 떼면 손에 쥐는 돈은 약 {eok(net)}이에요.\n\n"
            + (f"1등 구매 방식: {kinds}\n" if kinds else ""))
    head += f"{lines}\n\n🏆 1등 명당: {regions}\n{shops}\n\n우리 동네 판매점도 있나요? 👇 댓글로 지역을 남겨주세요."

    def tail(src):
        return (f"\n\n{sc.footer(src, f'/round/{rnd}/', '판매점 전체·번호 구성')}"
                "\n(동행복권 공식 발표 기준)")

    tags_ig = sc.hashtags(rnd, sc.KW_PRIZE, sc.KW_DRAW, channel="instagram")
    tags_fb = sc.hashtags(rnd, sc.KW_PRIZE, sc.KW_DRAW, channel="facebook")
    th = (f"💰 {rnd}회 1등 {r1['count']}명, 1명당 {eok(r1['amount'])}\n세금 떼면 약 {eok(net)}\n"
          f"1등 명당: {regions}\n\n{sc.footer('threads', f'/round/{rnd}/')}\n#로또")[:cards.THREADS_LIMIT]
    return {"instagram": head + tail("instagram") + "\n" + tags_ig, "facebook": head + tail("facebook") + "\n" + tags_fb,
            "threads": th,
            "youtube_title": f"{rnd}회 로또 1등 {r1['count']}명 · 명당 | 로또신령"[:100],
            "youtube_description": head + tail("youtube")}


def build(res: dict, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    rnd = res["round"]
    paths = []
    for i, im in enumerate((card_ranks(res), card_shops(res)), 1):
        p = out / f"{rnd}_{i}.png"
        im.save(p, optimize=True)
        paths.append(p)
    (out / f"{rnd}_captions.json").write_text(json.dumps(captions(res), ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"{rnd}_result.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="result_out")
    ap.add_argument("--round", type=int)
    a = ap.parse_args()
    import draw_results_db

    from weekly_content import round_result

    rnd = a.round or draw_results_db.get_latest_draw_round()
    res = round_result.fetch(rnd)
    if not res:
        print(f"[대기] {rnd}회 공식 결과·판매점 아직 없음 — 다음 실행에서 다시")
        return 3
    build(res, Path(a.out))
    print(f"[완료] {rnd}회 결과 정리 카드 2장 → {a.out}")
    return 0


if __name__ == "__main__":
    import traceback
    try:
        code = main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (1 if e.code else 0)
    except BaseException:
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
