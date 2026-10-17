# -*- coding: utf-8 -*-
"""주간 리포트 자동 제작 — 토요일 당첨번호 반영 직후(GitHub Actions weekly_content.yml).

1. DB(draw_results)에서 전체 당첨 이력을 읽고 최신 회차를 고른다(--round 로 지정 가능).
2. 안전 확인 — 하나라도 어긋나면 만들지 않고 실패로 끝낸다(틀린 번호가 나가면 신뢰를 잃는다):
   · 번호 6개가 1~45 서로 다름, 보너스가 1~45이고 본번호와 다름
   · 회차가 1부터 빠짐없이 이어짐
   · (자동 실행) 최신 회차 == 날짜로 계산한 '이번 주 토요일' 회차 — 반영이 덜 됐으면 멈춤
3. 카드 5장·게시 문구·쇼츠(mp4)를 out 폴더에 만든다. 3장은 '동행복권 집계중' 한 줄 + 공식 채널(필터 결과는 앱에서만 공유).

게시(인스타·스레드·유튜브)는 계정 연동 뒤 별도 단계로 붙인다 — 지금은 제작물만 만든다.
실행: python -m weekly_content.run_weekly --out weekly_out [--round 1246] [--no-date-check]
"""
from __future__ import annotations

import argparse
import json
import datetime as dt
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from weekly_content import cards  # noqa: E402


def validate(draws: dict[int, dict], rnd: int) -> None:
    rounds = sorted(draws)
    if rounds != list(range(1, rounds[-1] + 1)):
        missing = sorted(set(range(1, rounds[-1] + 1)) - set(rounds))[:10]
        raise SystemExit(f"[중단] 빠진 회차가 있습니다: {missing}")
    if rnd not in draws:
        raise SystemExit(f"[중단] {rnd}회 당첨번호가 DB에 없습니다")
    nums, bonus = draws[rnd]["nums"], draws[rnd]["bonus"]
    if len(set(nums)) != 6 or not all(1 <= n <= 45 for n in nums):
        raise SystemExit(f"[중단] {rnd}회 번호가 이상합니다: {nums}")
    if not (1 <= bonus <= 45) or bonus in nums:
        raise SystemExit(f"[중단] {rnd}회 보너스가 이상합니다: {bonus}")


def expected_latest_round(now: dt.datetime | None = None) -> int:
    """지금 시각 기준으로 이미 추첨이 끝났어야 하는 최신 회차(토 19:55 경계)."""
    from sales_window import target_round_for

    return target_round_for(now) - 1


def draw_date_text(rnd: int) -> str:
    return (dt.date(2002, 12, 7) + dt.timedelta(weeks=rnd - 1)).strftime("%Y.%m.%d")


def make_shorts(pngs: list[Path], out: Path, sec: float = 4.0) -> Path | None:
    if not shutil.which("ffmpeg"):
        print("  (ffmpeg 없음 — 쇼츠는 건너뜀)")
        return None
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    for p in pngs:
        args += ["-loop", "1", "-t", str(sec), "-i", str(p)]
    chains = "".join(f"[{i}:v]scale=1080:1350,pad=1080:1920:0:285:color=0x161c33,setsar=1,format=yuv420p[v{i}];"
                     for i in range(len(pngs)))
    prev, off, parts = "v0", sec - 0.5, []
    for i in range(1, len(pngs)):
        tag = "out" if i == len(pngs) - 1 else f"x{i}"
        parts.append(f"[{prev}][v{i}]xfade=transition=slideleft:duration=0.5:offset={off:.1f}[{tag}]")
        prev, off = tag, off + sec - 0.5
    args += ["-filter_complex", chains + ";".join(parts), "-map", "[out]", "-r", "30",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(args, check=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="weekly_out")
    ap.add_argument("--round", type=int)
    ap.add_argument("--no-date-check", action="store_true")
    ap.add_argument("--capture", help="토요일 즉시 게시: 캡처 번호 파일(instant/<회차>.txt) — DB에 그 회차가 아직 없을 때만 씀(DB엔 넣지 않음)")
    a = ap.parse_args()

    import draw_results_db

    draws = {h["draw_round"]: {"nums": sorted(h["numbers"]), "bonus": h["bonus"]}
             for h in draw_results_db.get_all_draw_results()}
    if a.capture:   # 2026-10-17(사용자 지시): 공식 발표를 기다리지 않고 캡처 번호로 바로 제작
        from weekly_content.instant_check import parse

        c_rnd, c_nums, c_bonus = parse(Path(a.capture))
        if c_rnd not in draws:
            draws[c_rnd] = {"nums": c_nums, "bonus": c_bonus}
            print(f"  ({c_rnd}회는 공식 미반영 — 캡처 번호로 제작, DB에는 넣지 않음)")
    rnd = a.round or max(draws)
    validate(draws, rnd)
    if not a.round and not a.no_date_check:
        exp = expected_latest_round()
        if rnd != exp:
            raise SystemExit(f"[중단] DB 최신 {rnd}회 ≠ 날짜상 최신 {exp}회 — 당첨번호 반영 후 다시 실행")

    out = Path(a.out)
    pngs = cards.build(draws, rnd, out, date_text=draw_date_text(rnd))
    (out / f"{rnd}_caption.txt").write_text(cards.caption(draws, rnd), encoding="utf-8")
    (out / f"{rnd}_captions.json").write_text(
        json.dumps(cards.captions_all(draws, rnd), ensure_ascii=False, indent=1), encoding="utf-8")
    shorts = make_shorts(pngs, out / f"{rnd}_shorts.mp4")
    print(f"[완료] {rnd}회 카드 {len(pngs)}장 · 문구 · 쇼츠={'있음' if shorts else '없음'} · "
          f"→ {out}")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)  # db_turso 비데몬 스레드로 종료가 멈추지 않게(hourly_draw_sync 와 같은 처리)
