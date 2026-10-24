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


def make_shorts(pngs: list[Path], out: Path, sec: float = 4.5, xf: float = 0.8, medley: bool = False,
                ppt: bool = False, plan: dict | None = None) -> Path | None:
    """세로 9:16 짧은 영상(네이버 클립·쇼츠용).

    2026-10-17(사용자 지적 '빛바랜 화질'): 예전엔 색공간 표시 없이 BT.601 로 변환돼 재생기(BT.709 가정)에서
    색이 바래 보였다 → BT.709 행렬로 변환 + 색공간 태그, 고화질(crf 16·slow·stillimage), faststart.
    배경은 단색 띠 대신 같은 카드를 흐리게·어둡게 깔아 9:16 화면을 꽉 채운다. 첫 장(번호)은 표지라 조금 길게."""
    if not shutil.which("ffmpeg"):
        print("  (ffmpeg 없음 — 쇼츠는 건너뜀)")
        return None
    # 2026-10-24 목요일 'PPT 느낌'(ppt=True, 사용자 지시): 장당 시간 2배, 장이 바뀔 때 '슥' 소리 + 서서히 나타남(디졸브),
    # 장마다 살짝 줌인. 줌은 3배 크게 키운 뒤 줄여 그려 글자가 떨리지 않게(정수 반올림 떨림 방지).
    # 2026-10-24 목요일 수정 제안(plan, thursday.video_plan): 장 시간 = 글자 수 비례(전체 약 1분), 장 넘김 효과·
    # 장별 음악 장르·줌 방향이 매주 바뀌고, 장이 들어올 때마다 빛줄기가 카드 위를 쓸고 지나간다.
    if plan:
        ppt, medley, xf = True, True, plan["xf"]
        durs = list(plan["secs"])
    else:
        if ppt:
            sec, xf = sec * 2, 1.2
        durs = [sec + 0.8] + [sec] * (len(pngs) - 1)
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    for p, d in zip(pngs, durs):
        args += ["-loop", "1", "-framerate", "30", "-t", f"{d:.2f}", "-i", str(p)]
    streak = None
    if plan:
        streak = _light_streak(out.with_suffix(".streak.png"))
        for d in durs:   # 장마다 따로 입력(하나를 split 하면 늦게 쓰는 장 몫이 메모리에 쌓여 OOM)
            args += ["-loop", "1", "-framerate", "30", "-t", f"{d:.2f}", "-i", str(streak)]

    def fg_chain(i: int, d: float) -> str:
        if not ppt:
            return f"[b{i}]scale=1080:1350:flags=lanczos[fg{i}];"
        n = int(d * 30)
        mo = plan["motions"][i] if plan else "in"
        z = f"1.06-0.05*on/{n}" if mo == "out" else f"1+0.05*on/{n}"
        y = "(ih-ih/zoom)*0.15" if mo == "in_top" else "ih/2-(ih/zoom/2)"
        return (f"[b{i}]scale=3240:4050:flags=lanczos,zoompan=z='{z}':d=1:"
                f"x='iw/2-(iw/zoom/2)':y='{y}':s=1080x1350:fps=30[fg{i}];")

    def shine(i: int) -> str:   # 빛줄기: 장이 나타난 직후 0.3~1.3초 사이 왼쪽→오른쪽
        if not plan:
            return ""
        t0 = 0.3 if i == 0 else xf * 0.6
        return (f"[c{i}][s{i}]overlay=x='-420+(t-{t0:.2f})*1500':y=285:"
                f"enable='between(t,{t0:.2f},{t0 + 1.1:.2f})'[d{i}];[d{i}]")

    chains = "".join(f"[{len(pngs) + i}:v]format=rgba[s{i}];" for i in range(len(pngs))) if plan else ""
    chains += "".join(
        f"[{i}:v]split[a{i}][b{i}];"
        f"[a{i}]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:3,"
        f"eq=brightness=-0.18:saturation=1.1[bg{i}];"
        + fg_chain(i, durs[i]) +
        (f"[bg{i}][fg{i}]overlay=0:(H-h)/2[c{i}];" + shine(i) if plan else f"[bg{i}][fg{i}]overlay=0:(H-h)/2,")
        + "setsar=1,fps=30,"
        f"scale=out_color_matrix=bt709:out_range=tv,format=yuv420p[v{i}];"
        for i in range(len(pngs)))
    # 2026-10-24(사용자 지시 '페이지 넘기기 좀 느리게'): 장당 3.2초→4.5초, 넘기는 동작 0.4초→0.8초
    prev, off, parts = "v0", durs[0] - xf, []
    for i in range(1, len(pngs)):
        tag = "out" if i == len(pngs) - 1 else f"x{i}"
        trans = plan["trans"][i - 1] if plan else ("fade" if ppt else "slideleft")
        parts.append(f"[{prev}][v{i}]xfade=transition={trans}:duration={xf}:offset={off:.2f}[{tag}]")
        prev, off = tag, off + durs[i] - xf
    # 2026-10-24(사용자 지시 '음악 삽입 필수'): 코드로 만든 배경음악(저작권 문제 없음)을 영상 길이에 맞춰 넣는다.
    import zlib

    from weekly_content import bgm

    total = sum(durs) - xf * (len(pngs) - 1)
    seed = f"{out.name}:{zlib.crc32(pngs[-1].read_bytes())}"   # 게시물마다 다른 곡(목·금·토가 서로 다름)
    if medley:   # 2026-10-24 목요일: 장이 바뀔 때마다 곡도 바뀜(+ ppt 면 넘김 순간마다 '슥' 소리)
        segs = [durs[0] - xf / 2] + [d - xf for d in durs[1:-1]] + [durs[-1] - xf / 2 + 0.5]
        starts = []
        t = 0.0
        for d in durs[:-1]:
            t += d - xf
            starts.append(t)
        sparks = [t for t, tr in zip(starts, plan["trans"]) if tr in plan["light"]] if plan else None
        wav = bgm.write_medley(out.with_suffix(".bgm.wav"), segs, seed, whoosh_at=starts if ppt else None,
                               styles=plan["styles"] if plan else None, sparkle_at=sparks)
    else:
        wav = bgm.write_wav(out.with_suffix(".bgm.wav"), round(total + 0.5, 2), seed=seed)
    args += ["-i", str(wav)]
    a_idx = len(pngs) * (2 if streak else 1)
    args += ["-filter_complex", chains + ";".join(parts), "-map", "[out]", "-map", f"{a_idx}:a",
             "-c:a", "aac", "-b:a", "160k", "-shortest", "-r", "30",
             "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-tune", "stillimage", "-profile:v", "high",
             "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
             "-color_range", "tv", "-movflags", "+faststart", str(out)]
    subprocess.run(args, check=True)
    wav.unlink(missing_ok=True)
    if streak:
        streak.unlink(missing_ok=True)
    return out


def _light_streak(path: Path) -> Path:
    """카드 위를 쓸고 지나가는 비스듬한 빛줄기(가운데 밝고 양옆으로 사라짐) — 420x1350 투명 PNG."""
    from PIL import Image

    import numpy as np

    w, h = 420, 1350
    xs = np.arange(w)[None, :] - (np.arange(h)[:, None] - h / 2) * 0.2   # 위가 오른쪽으로 기운 띠
    d = np.abs(xs - w / 2) / (w * 0.22)
    a = (np.clip(1 - d, 0, 1) ** 2 * 120).astype(np.uint8)
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2], rgba[..., 3] = 255, 244, 214, a
    Image.fromarray(rgba, "RGBA").save(path)
    return path


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
    # 2026-10-24(사용자 지시 '첫 페이지 부적 삭제'): SNS 게시·영상에서 회차 부적을 뺀다(홈페이지 부적은 site_export 가 따로 만듦).
    # 2026-10-24(사용자 지시): 토요일도 목요일과 같은 방식 — 약 1분·PPT 넘김·'슥' 소리·장마다 다른 비트 음악(video_fx).
    # 장 길이 비중: 당첨번호 13 · 숫자 분석 17(정보 많음) · 타로 14 · 앱 안내 10. offset=2 → 같은 주 목요일과 다른 연출.
    from weekly_content import video_fx

    weights = [13, 17, 14, 10][: len(pngs)]
    shorts = make_shorts(pngs, out / f"{rnd}_shorts.mp4", plan=video_fx.plan(weights, rnd - 1247, offset=2))
    if shorts:
        from weekly_content import clip_kit

        clip_kit.write(out, rnd, "sat")   # 네이버 클립 수동 업로드용 문구(실행 기록 Artifacts)
    print(f"[완료] {rnd}회 카드 {len(pngs)}장 · 문구 · 쇼츠={'있음' if shorts else '없음'} · "
          f"→ {out}")
    return 0


if __name__ == "__main__":
    # 2026-10-17: 예외로 끝나도 os._exit 로 바로 종료 — 아니면 db_turso 비데몬 스레드 때문에 프로세스가
    # 안 끝나 Actions 가 시간 한도까지 '진행 중'으로 멈추고, 같은 concurrency 의 다음 실행까지 막는다.
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
    os._exit(code)  # db_turso 비데몬 스레드로 종료가 멈추지 않게(hourly_draw_sync 와 같은 처리)
