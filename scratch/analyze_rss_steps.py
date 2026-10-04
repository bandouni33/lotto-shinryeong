"""RSS/CPU 샘플 CSV를 **단계 경계 시각**으로 잘라 단계별로 요약한다 (2026-10-04 조사).

부하테스트가 출력한 "=== 단계: 동시 N명 (HH:MM:SS) ===" 시각을 그대로 경계로 주면,
각 단계의 시작/끝 RSS·CPU와 단계 간 증가분을 계산해 준다. 세션 1개당 계수는 이 증가분으로
구한다(측정 목적은 그 계수 하나다).

실행:
  venv312\\Scripts\\python.exe -X utf8 scratch\\analyze_rss_steps.py --csv scratch\\rss_ramp.csv ^
      --steps "10=17:36:43,30=17:37:28,60=17:38:13,100=17:38:58,150=17:39:43"
"""

from __future__ import annotations

import argparse
import csv
import sys


def parse_steps(text: str) -> list[tuple[int, str]]:
    out = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        n, t = part.split("=")
        out.append((int(n), t.strip()))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="scratch/rss_ramp.csv")
    ap.add_argument("--steps", required=True, help='예: "10=17:36:43,30=17:37:28"')
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    steps = parse_steps(args.steps)
    if not rows:
        print("샘플이 없다")
        return 1

    def num(row: dict, key: str) -> float | None:
        v = (row.get(key) or "").strip()
        try:
            return float(v)
        except ValueError:
            return None

    print(f"샘플 {len(rows)}개 · {rows[0]['t']} ~ {rows[-1]['t']}")
    baseline = num(rows[0], "rss_mb")
    print(f"기준선(첫 샘플) RSS {baseline}MB · 여유 RAM {rows[0]['free_mb']}MB\n")
    print(f"{'동시':>5} | {'구간 시작':>9} | {'시작RSS':>8} | {'끝RSS':>8} | "
          f"{'증가':>7} | {'세션당':>7} | {'procCPU평균':>10} | {'sysCPU평균':>10}")
    prev_end = baseline
    for i, (n, t) in enumerate(steps):
        next_t = steps[i + 1][1] if i + 1 < len(steps) else None
        window = [r for r in rows if r["t"] >= t and (next_t is None or r["t"] < next_t)]
        if not window:
            print(f"{n:>5} | {t:>9} | (샘플 없음 — 그 시각 이후 데이터가 없다)")
            continue
        start = num(window[0], "rss_mb")
        end = num(window[-1], "rss_mb")
        peaks = [num(r, "rss_mb") for r in window if num(r, "rss_mb") is not None]
        cpu = [num(r, "proc_cpu_pct") for r in window if num(r, "proc_cpu_pct") is not None]
        scpu = [num(r, "sys_cpu_pct") for r in window if num(r, "sys_cpu_pct") is not None]
        per = (end - baseline) / n if end is not None and baseline is not None else None
        print(f"{n:>5} | {t:>9} | {start:>8.1f} | {end:>8.1f} | "
              f"{(end - prev_end):>7.1f} | {('-' if per is None else f'{per:.1f}'):>7} | "
              f"{(sum(cpu) / len(cpu) if cpu else 0):>10.1f} | "
              f"{(sum(scpu) / len(scpu) if scpu else 0):>10.1f}")
        if peaks:
            print(f"        (구간 최대 RSS {max(peaks):.1f}MB · 샘플 {len(window)}개 · "
                  f"끝 여유 RAM {window[-1]['free_mb']}MB)")
        prev_end = end if end is not None else prev_end

    all_rss = [num(r, "rss_mb") for r in rows if num(r, "rss_mb") is not None]
    print(f"\n전체 최대 RSS {max(all_rss):.1f}MB · 최소 {min(all_rss):.1f}MB")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
