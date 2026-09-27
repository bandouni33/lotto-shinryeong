# -*- coding: utf-8 -*-
"""admin_dashboard.py '최근 5회차 생성 현황' 표 불변식 테스트 (연속 5회차 강제 버전).

검증 대상은 **파일에 실제로 들어간 그 블록**이다 — 사본이 아니라 admin_dashboard.py에서
블록 소스를 그대로 떼어내 exec 하므로, 파일에 뭐가 들어있는지를 그대로 검사한다.

불변식(모든 유효 입력에 성립해야 하는 것):
  S1 블록이 파일에 있고 기대한 모양이다(마커·들여쓰기, st/pd 사용, 함수 4개 사용)
  S2 생성시간 변환 — 입력 전 종류(없음·빈칸·깨진 문자열·마이크로초 유무·타임존·월/연 경계)
  S3 행 구성 — 회차는 **항상 연속 5개(latest~latest-4)**, 건너뛴 회차 없음(예: 1236),
     총 조합 개수=stage4_count / 조합 개수=get_combination_count_by_draw,
     값이 0·None·기록없음이면 "기록없음", 열 이름·순서, 회차 수만큼만 행, 함수 호출 횟수
  S4 렌더 — 행이 있으면 st.dataframe(DataFrame, use_container_width/hide_index), 없으면 미호출
  S5 실물 DB — 1244·1243·1242·1241·1240 연속, 1236 미노출, 1243 실측값(52,187 /
     1,043,741 / 09/20 14:03) 일치, 그리고 표 값 == DB 값(직접 재조회 교차 확인)

실행: venv312\\Scripts\\python.exe scratch\\test_admin_recent5_table.py
"""
from __future__ import annotations

import os
import re
import sys
import textwrap
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from env_loader import load_dotenv_file  # noqa: E402

load_dotenv_file()  # 실물 DB(Turso) 접속 정보 — 단독 실행 테스트에도 필요(없으면 S4·S5가 못 돈다)

OUT = ROOT / "scratch" / "test_admin_recent5_table_out.txt"
SRC = ROOT / "admin_dashboard.py"
R: list[str] = []
FAILS: list[str] = []
t0 = time.time()
FUNCS = ("get_combination_count_by_draw", "get_draw_extraction_stats",
         "get_draw_generation_stats", "get_pattern_recorded_at")


def w(s: str = "") -> None:
    R.append(str(s))
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(str(s).encode("cp949", errors="replace").decode("cp949", errors="replace"),
              flush=True)


def ok(cond: bool, msg: str) -> None:
    if cond:
        w(f"  ok   {msg}")
    else:
        FAILS.append(msg)
        w(f"  FAIL {msg}")


# ── S1 블록 추출
lines = SRC.read_text(encoding="utf-8").splitlines()
start = next(i for i, l in enumerate(lines) if "최근 5회차 생성 현황" in l
             and "사용자 지시" in l)
end = next(i for i in range(start, len(lines)) if "hide_index=True," in lines[i]) + 2
block_lines = lines[start:end]
BLOCK = textwrap.dedent("\n".join(block_lines))

w("== S1. 블록이 파일에 있는가 ==")
ok(all((not l.strip()) or l.startswith("    ") for l in block_lines),
   f"블록 {len(block_lines)}줄 전부 4칸 들여쓰기(대시보드 함수 안)")
ok("<h5 style='margin-top:20px;'>최근 5회차 생성 현황</h5>" in BLOCK, "표 제목이 들어 있다")
ok("@st.cache_data(ttl=60, show_spinner=False)" in BLOCK
   and "pd.DataFrame(_ops_recent_rows)" in BLOCK, "cache_data 데코레이터·DataFrame 렌더가 있다")
ok("range(latest_round, latest_round - 5, -1)" in BLOCK
   and "get_draw_extraction_stats(limit=1)" in BLOCK,
   "연속 5회차 강제(latest~latest-4) — limit=5로 회차를 나열하지 않는다")
ok(all(f in BLOCK for f in FUNCS), f"쓰는 함수 4개가 모두 블록 안에 있다 {list(FUNCS)}")
ok(any("등록된 조합 개수" in l for l in lines[max(0, start - 8):start]),
   "삽입 위치가 '등록된 조합 개수' metric 바로 뒤다")


class StubStreamlit:
    def __init__(self):
        self.markdowns: list[str] = []
        self.warnings: list[str] = []
        self.dataframes: list[dict] = []

    def cache_data(self, **_kw):
        def deco(fn):
            return fn
        return deco

    def markdown(self, body, **_kw):
        self.markdowns.append(body)

    def warning(self, body):
        self.warnings.append(body)

    def dataframe(self, data, **kw):
        self.dataframes.append({"data": data, **kw})


def load_block(st):
    ns = {"st": st, "pd": pd}
    exec(compile(BLOCK, "admin_dashboard.py", "exec"), ns)
    return ns


def stub_all(latest, gens=None, counts=None, ats=None, extract_returns=None):
    """네 함수를 결정적으로 흉내낸다. 최신 회차만 주면 나머지는 '기록없음' 쪽으로 둔다."""
    gens = gens or {}
    counts = counts or {}
    ats = ats or {}

    def f_extract(limit=1):
        assert limit == 1, f"최신 회차 조회는 limit=1이어야 한다(실제 {limit})"
        if extract_returns is not None:
            return extract_returns
        return [{"draw_round": latest, "total_count": 0}]

    def f_gen(r):
        return gens.get(r)

    def f_count(r):
        return counts.get(r)

    def f_at(r):
        return ats.get(r)
    return f_extract, f_gen, f_count, f_at


import marketing_db as mdb  # noqa: E402

REAL = {name: getattr(mdb, name) for name in FUNCS}
stub = StubStreamlit()
ns = load_block(stub)

w("\n== S2. 생성시간 변환(UTC→KST) — 입력 전 종류 ==")
CASES = [
    (None, "기록없음"), ("", "기록없음"), ("   ", "기록없음"),
    ("not-a-date", "기록없음"), ("2026-13-45T99:99:99", "기록없음"),
    ("2026-09-20T05:03:27.958619", "09/20 14:03"),   # 1243 실측값
    ("2026-09-27T10:11:22", "09/27 19:11"),          # 마이크로초 없음
    ("2026-09-30T20:00:00", "10/01 05:00"),          # 월 경계 넘김
    ("2026-12-31T20:00:00", "01/01 05:00"),          # 연 경계 넘김
    ("2026-09-20T05:03:27+00:00", "09/20 14:03"),    # 타임존 표기 포함
]
bad = []
for iso, want in CASES:
    mdb.get_draw_extraction_stats, mdb.get_draw_generation_stats, \
        mdb.get_combination_count_by_draw, mdb.get_pattern_recorded_at = stub_all(
            1243, gens={1243: {"stage4_count": 1}}, counts={1243: 1}, ats={1243: iso})
    got = ns["_ops_recent_generation_rows_cached"]()[0]["생성시간"]
    hit = (got == want) or (want == "기록없음"
                            and re.fullmatch(r"\d{2}/\d{2} \d{2}:\d{2}", got or ""))
    if not hit:
        bad.append(f"{iso!r}→{got!r}(기대 {want!r})")
    w(f"       {str(iso)!r:36} → {got}")
ok(not bad, f"{len(CASES)}종 입력이 모두 '기록없음' 또는 MM/DD HH:MM (예외 {len(bad)} {bad[:2]})")

w("\n== S3. 행 구성 규칙 ==")
calls = {"extract": 0, "gen": 0, "count": 0, "at": 0}
for latest in (1244, 1243, 1000, 5):        # 여러 최신 회차에 대해 '연속 5개' 성질을 확인
    want = [f"{latest - i}회차" for i in range(5)]
    mdb.get_draw_extraction_stats, mdb.get_draw_generation_stats, \
        mdb.get_combination_count_by_draw, mdb.get_pattern_recorded_at = stub_all(
            latest, gens={latest: {"stage4_count": 10}}, counts={latest: 20},
            ats={latest: "2026-09-20T05:03:27"})
    rows = ns["_ops_recent_generation_rows_cached"]()
    got = [r["배포 회차"] for r in rows]
    ok(got == want, f"최신 {latest} → 연속 5회차 {got}")
ok(all(len(ns["_ops_recent_generation_rows_cached"]()) == 5 for _ in range(1)),
   "항상 정확히 5행")

latest = 1243
calls = {"extract": 0, "gen": 0, "count": 0, "at": 0}


def counting(fn, key):
    def inner(r):
        calls[key] += 1
        return fn(r)
    return inner


f_extract, f_gen, f_count, f_at = stub_all(
    latest, gens={latest: {"stage4_count": 1043741}}, counts={latest: 52187},
    ats={latest: "2026-09-20T05:03:27.958619"})
mdb.get_draw_extraction_stats = f_extract
mdb.get_draw_generation_stats = counting(f_gen, "gen")
mdb.get_combination_count_by_draw = counting(f_count, "count")
mdb.get_pattern_recorded_at = counting(f_at, "at")
rows = ns["_ops_recent_generation_rows_cached"]()
ok(list(rows[0].keys()) == ["배포 회차", "생성시간", "총 조합 개수", "조합 개수"],
   f"열 이름·순서 = {list(rows[0].keys())}")
ok(rows[0]["총 조합 개수"] == "1,043,741 개" and rows[0]["조합 개수"] == "52,187 개",
   f"값 포맷(콤마): {rows[0]['총 조합 개수']} / {rows[0]['조합 개수']}")
ok(all(r["총 조합 개수"] == "기록없음" for r in rows[1:]),
   "생성기록 없으면 총 조합 개수 = '기록없음'")
ok(all(r["조합 개수"] == "기록없음" for r in rows[1:]),
   "등록 조합이 0/없음이면 조합 개수 = '기록없음'")
ok(all(r["생성시간"] == "기록없음" for r in rows[1:]), "생성시간 기록 없으면 '기록없음'")
ok(calls == {"extract": 0, "gen": 5, "count": 5, "at": 5},
   f"함수 호출 — 최신 조회 1회 + 회차마다 gen·count·at 5회씩 (실제 {calls})")
mdb.get_draw_extraction_stats, mdb.get_draw_generation_stats, \
    mdb.get_combination_count_by_draw, mdb.get_pattern_recorded_at = stub_all(
        latest, counts={1241: 0}, extract_returns=None)
mdb.get_combination_count_by_draw = lambda r: 0 if r == 1241 else None
rows0 = ns["_ops_recent_generation_rows_cached"]()
ok(all(r["조합 개수"] == "기록없음" for r in rows0),
   "0·None 둘 다 '기록없음'으로 처리(경계)")
mdb.get_draw_extraction_stats, mdb.get_draw_generation_stats, \
    mdb.get_combination_count_by_draw, mdb.get_pattern_recorded_at = stub_all(
        latest, extract_returns=[])
ok(ns["_ops_recent_generation_rows_cached"]() == [], "최신 회차가 없으면 빈 목록(행 0개)")
for name, fn in REAL.items():
    setattr(mdb, name, fn)

w("\n== S4. 렌더 호출 ==")
stub4 = StubStreamlit()
load_block(stub4)
ok(stub4.markdowns and "최근 5회차 생성 현황" in stub4.markdowns[0],
   f"표 제목이 렌더된다: {stub4.markdowns[:1]}")
ok(len(stub4.dataframes) == 1, f"dataframe 호출 {len(stub4.dataframes)}회 == 1회")
if stub4.dataframes:
    df_call = stub4.dataframes[0]
    ok(isinstance(df_call["data"], pd.DataFrame) and df_call["data"].shape == (5, 4),
       f"DataFrame 모양 = {df_call['data'].shape} (5행 4열)")
    ok(df_call.get("use_container_width") is True and df_call.get("hide_index") is True,
       "렌더 옵션 = use_container_width/hide_index")
stub4b = StubStreamlit()
mdb.get_draw_extraction_stats = lambda limit=1: []
try:
    load_block(stub4b)
finally:
    mdb.get_draw_extraction_stats = REAL["get_draw_extraction_stats"]
ok(stub4b.dataframes == [], f"최신 회차가 없으면 표를 그리지 않는다 (호출 {len(stub4b.dataframes)}회)")
ok(stub4b.markdowns and "최근 5회차 생성 현황" in stub4b.markdowns[0],
   "회차가 없어도 표 제목은 렌더된다")

w("\n== S5. 실물 DB ==")
stub5 = StubStreamlit()
ns5 = load_block(stub5)
rows5 = ns5["_ops_recent_generation_rows_cached"]()
latest5 = REAL["get_draw_extraction_stats"](limit=1)[0]["draw_round"]
labels5 = [r["배포 회차"] for r in rows5]
w(f"       표에 나온 회차: {labels5}")
ok(labels5 == [f"{latest5 - i}회차" for i in range(5)],
   f"실물 DB: 최신 {latest5}부터 연속 5개 — 건너뛴 회차 없음")
ok("1236회차" not in labels5, "건너뛴 옛 회차(1236 등)가 표에 없다")
bad5 = []
for r in rows5:
    rnd = int(r["배포 회차"].replace("회차", ""))
    g = REAL["get_draw_generation_stats"](rnd)
    c = REAL["get_combination_count_by_draw"](rnd)
    at = REAL["get_pattern_recorded_at"](rnd)
    if r["총 조합 개수"] != (f"{g['stage4_count']:,} 개" if g else "기록없음"):
        bad5.append(f"{rnd} 총 조합 개수 {r['총 조합 개수']} != DB {g and g['stage4_count']}")
    if r["조합 개수"] != (f"{c:,} 개" if c else "기록없음"):
        bad5.append(f"{rnd} 조합 개수 {r['조합 개수']} != DB {c}")
    if at and r["생성시간"] == "기록없음":
        bad5.append(f"{rnd} 생성시간이 기록없음인데 DB에는 {at}")
    if not at and r["생성시간"] != "기록없음":
        bad5.append(f"{rnd} 생성시간 {r['생성시간']}인데 DB에는 기록 없음")
ok(not bad5, f"표 값 == DB 값(교차 확인) — 불일치 {len(bad5)} {bad5[:3]}")
r1243 = next((r for r in rows5 if r["배포 회차"] == "1243회차"), {})
w(f"       1243회차 행: {r1243}")
ok(r1243.get("조합 개수") == "52,187 개", "1243 조합 개수 = 52,187 개")
ok(r1243.get("총 조합 개수") == "1,043,741 개", "1243 총 조합 개수 = 1,043,741 개")
ok(r1243.get("생성시간") == "09/20 14:03", "1243 생성시간 = 09/20 14:03 (KST 변환)")
다음없음 = [r["배포 회차"] for r in rows5 if r["조합 개수"] == "기록없음"]
w(f"       '기록없음'으로 표시되는 회차: {다음없음}")

w(f"\n단언 실패 {len(FAILS)}건" + ("" if not FAILS else ": " + " | ".join(FAILS[:5])))
w(f"총 경과 {time.time() - t0:.1f}s")
OUT.write_text("\n".join(R), encoding="utf-8")
print(f"written {OUT}")
os._exit(1 if FAILS else 0)
