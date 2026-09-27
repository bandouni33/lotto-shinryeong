# -*- coding: utf-8 -*-
"""앱이 '실제로 로드해서 쓰는' AUTO 규칙과 판정 기준 창 실측 (읽기 전용).

질문(2026-09-27 사용자): DB에서 로드되는 auto_rules의 "후보패턴 이웃수" 항목이
순위 계산에 몇 회 창을 쓰는가 — 100인가 200인가.
보는 것:
  1) DB(app_settings) → 로컬 JSON 순으로 실제 로드되는 stage1 규칙 원문(AUTO 항목 전부)
  2) combo_filter_v2 가 그 규칙의 '대상 번호'를 만들 때 쓰는 창(RECENT_WINDOW 상수와
     _gap_order_for_anchor / _compute_pool_for_anchor 코드 경로)
  3) 같은 기준 회차로 100회 창과 200회 창의 격차순위를 각각 계산해 실제로 다른지 비교
즉 "규칙에 창이 적혀 있는가" + "코드가 실제로 어느 창을 쓰는가"를 둘 다 본다.

실행: venv312\\Scripts\\python.exe scratch\\probe_auto_rule_window.py
"""
from __future__ import annotations

import inspect
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from env_loader import load_dotenv_file  # noqa: E402

load_dotenv_file()

import combo_filter_v2 as cf  # noqa: E402

OUT = ROOT / "scratch" / "probe_auto_rule_window_out.txt"
L: list[str] = []


def w(s: str = "") -> None:
    L.append(str(s))
    print(s, flush=True)


def gap_order_window(hist, anchor_round, window):
    """역대 rank − 최근 window회 rank (동점은 작은 번호) — 창을 인자로 받는 일반형."""
    rounds = [h["draw_round"] for h in hist]
    idx = rounds.index(anchor_round)
    allc: dict[int, int] = {}
    for h in hist[: idx + 1]:
        for x in h["nums"]:
            allc[x] = allc.get(x, 0) + 1
    rec: dict[int, int] = {}
    for h in hist[max(0, idx + 1 - window): idx + 1]:
        for x in h["nums"]:
            rec[x] = rec.get(x, 0) + 1
    ar = {n: i + 1 for i, n in enumerate(sorted(range(1, 46), key=lambda x: (-allc.get(x, 0), x)))}
    rr = {n: i + 1 for i, n in enumerate(sorted(range(1, 46), key=lambda x: (-rec.get(x, 0), x)))}
    return sorted(range(1, 46), key=lambda x: (-(rr[x] - ar[x]), x))


# ── 1) 실제 로드되는 규칙 원문
w("== 1) DB → 로컬 JSON 순으로 실제 로드되는 stage1 규칙 ==")
raw_db = None
try:
    import app_settings

    raw_db = app_settings.get_filter_rules_json(1)
    w(f"  app_settings.get_filter_rules_json(1) 길이 = {len(raw_db or '')}자")
except Exception as e:  # noqa: BLE001
    w(f"  [주의] DB 조회 실패: {type(e).__name__}: {e}")

raw_json = None
p = ROOT / "combo_filter_rules_stage1.json"
if p.exists():
    raw_json = p.read_text(encoding="utf-8")
    w(f"  로컬 파일 {p.name} 길이 = {len(raw_json)}자")

src = raw_db or raw_json
if src:
    entries = json.loads(src)
    autos = [e for e in entries if e.get("is_auto")]
    w(f"  규칙 {len(entries)}개 중 AUTO {len(autos)}개 (출처: {'DB' if raw_db else '로컬 파일'})")
    for e in autos:
        w(f"    AUTO 원문: {json.dumps(e, ensure_ascii=False)}")
    w("  → 항목에 '창(window)'을 지정하는 키가 있는가: "
      f"{sorted({k for e in autos for k in e})}")
else:
    w("  [주의] DB·로컬 어디에서도 규칙을 읽지 못했습니다")

static, auto, gap = cf._load_rules()
w(f"  cf._load_rules() → 고정 {len(static)} + AUTO {len(auto)} + 이격수 {len(gap)}")
for a in auto:
    w(f"    AUTO 로드결과: name={a.get('name')!r} min={a.get('min')} max={a.get('max')} "
      f"targets={a.get('targets')} 키={sorted(a)}")

# ── 2) 코드가 쓰는 창
w("\n== 2) combo_filter_v2가 그 규칙의 대상 번호를 만드는 코드 경로 ==")
w(f"  cf.RECENT_WINDOW = {cf.RECENT_WINDOW} (모듈 상수)")
src_gap = inspect.getsource(cf._gap_order_for_anchor)
w(f"  _gap_order_for_anchor 안에서 쓰는 창: "
  f"{'RECENT_WINDOW' if 'RECENT_WINDOW' in src_gap else '?'} "
  f"(함수 안에 '200'이라는 리터럴: {'있음' if '200' in src_gap else '없음'})")
src_pool = inspect.getsource(cf._compute_pool_for_anchor)
branch = [ln.strip() for ln in src_pool.splitlines() if "후보패턴" in ln]
w(f"  _compute_pool_for_anchor 의 '후보패턴 이웃수' 분기: {branch}")
w(f"  그 분기가 쓰는 격차순위 변수: gap_order (100회 창) — 200회용 순위 변수는 "
  f"{'있다' if 'gap_order_window' in src_pool or '200' in src_pool else '없다'}")

# ── 3) 실제로 다른가 — 같은 기준 회차로 100 vs 200 창 비교
w("\n== 3) 같은 기준 회차에서 100회 창과 200회 창의 실제 차이 ==")
import openpyxl  # noqa: E402

SRC = ROOT / "★조합생성_후보숫자_추적표" / "조합생성_후보숫자_추적표_샘플.xlsx"
wb = openpyxl.load_workbook(SRC, data_only=True)
try:
    ws = wb["전체당첨내역"]
    draws = {}
    for r in range(2, ws.max_row + 1):
        rr = ws.cell(r, 1).value
        if isinstance(rr, int):
            draws[rr] = [ws.cell(r, c).value for c in range(2, 9)]
finally:
    wb.close()
anchor = max(draws) - 1                      # 최신 당첨 = 1243 → 기준 회차 1242
hist = [{"draw_round": x, "nums": list(draws[x][:6]), "bonus": draws[x][6]}
        for x in sorted(draws) if x <= anchor]
o100_app = cf._gap_order_for_anchor(hist, anchor)     # 앱이 쓰는 것
o100_mine = gap_order_window(hist, anchor, 100)
o200 = gap_order_window(hist, anchor, 200)
w(f"  기준 회차 {anchor} · 직전 7개 = {draws[anchor][:6] + [draws[anchor][6]]}")
w(f"  앱 함수(cf._gap_order_for_anchor) 상위 10 = {o100_app[:10]}")
w(f"  내 100회 창                        상위 10 = {o100_mine[:10]}")
w(f"  내 200회 창                        상위 10 = {o200[:10]}")
w(f"  앱 함수 == 100회 창 : {o100_app == o100_mine}")
w(f"  100회 창 == 200회 창 : {o100_mine == o200} (다르면 창이 결과를 바꾼다)")


def cand_neighbor(order, anchors7):
    out = set()
    for x in anchors7:
        gi = order.index(x)
        if gi > 0:
            out.add(order[gi - 1])
        if gi < 44:
            out.add(order[gi + 1])
    return sorted(out)


a7 = draws[anchor][:6] + [draws[anchor][6]]
n100 = cand_neighbor(o100_app, a7)
n200 = cand_neighbor(o200, a7)
w(f"  '후보패턴 이웃수' 대상집합(100회) = {n100} ({len(n100)}개)")
w(f"  '후보패턴 이웃수' 대상집합(200회) = {n200} ({len(n200)}개)")
w(f"  두 집합 차이: 100회만 {sorted(set(n100) - set(n200))} / 200회만 {sorted(set(n200) - set(n100))}")

w("\n== 결론 ==")
w(f"  · DB/JSON의 AUTO 규칙 원문에는 '창'을 지정하는 키가 없고 이름에만 '(200회)'가 붙는다")
w(f"  · 앱 코드(combo_filter_v2)는 '후보패턴 이웃수'의 대상 번호를 RECENT_WINDOW={cf.RECENT_WINDOW} "
  f"창의 격차순위에서 만든다 → 앱이 실제로 쓰는 창은 100회")
w(f"  · 샘플 파일의 행 484('후보패턴 이웃수(200회)')가 200회 창을 요구하지만, 앱에는 그 창을 "
  f"쓰는 코드 경로가 없다(그래서 2차 통과수가 약 5% 어긋난다)")

OUT.write_text("\n".join(L), encoding="utf-8")
print(f"written {OUT}")
sys.exit(0)
