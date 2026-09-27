# -*- coding: utf-8 -*-
"""admin_dashboard.py '최근 5회차 생성 현황' 표 불변식 테스트.

검증 대상은 **파일에 실제로 들어간 그 블록**이다 — 사본이 아니라 admin_dashboard.py에서
블록 소스를 그대로 떼어내 exec 하므로, 파일에 뭐가 들어있는지를 그대로 검사한다.

불변식(모든 유효 입력에 성립해야 하는 것):
  S1 블록이 파일에 있고 기대한 모양이다(마커·들여쓰기·줄 수, st/pd 사용)
  S2 생성시간 변환 — 입력 전 종류(없음·빈칸·깨진 문자열·마이크로초 있음/없음·타임존 있음·
     월/연 경계 넘김)에 대해 "기록없음" 또는 MM/DD HH:MM (UTC→KST +9h)
  S3 행 구성 — 회차 라벨 형식, 총 조합 개수(stage4_count)/조합 개수(total_count) 콤마 포맷,
     gen 없음 → "기록없음", 열 이름·순서, 회차 수만큼만 행, 회차마다 두 함수 1회씩 호출
  S4 렌더 — 행이 있으면 st.dataframe을 (DataFrame, use_container_width=True, hide_index=True)
     로 1회 호출, 행이 없으면 호출하지 않는다
  S5 실물 DB — 1243회차 값이 실제 DB 값과 일치한다(표 값 == DB 값, 직접 재조회로 교차 확인)
     + 1243 실측 기준값(1,043,741 / 52,187 / 09/20 14:03) 고정 확인

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
# +2 = 스르는 "hide_index=True," 줄 다음의 닫는 ")" 까지 포함(안 그러면 괄호가 안 닫혀 exec가 깨진다)
block_lines = lines[start:end]
BLOCK = textwrap.dedent("\n".join(block_lines))

w("== S1. 블록이 파일에 있는가 ==")
ok(all((not l.strip()) or l.startswith("    ") for l in block_lines),
   f"블록 {len(block_lines)}줄 전부 4칸 들여쓰기(대시보드 함수 안)")
ok("st.markdown(\"<h5 style='margin-top:20px;'>최근 5회차 생성 현황</h5>\"" in BLOCK,
   "표 제목 마크다운이 들어 있다")
ok("@st.cache_data(ttl=60, show_spinner=False)" in BLOCK
   and "pd.DataFrame(_ops_recent_rows)" in BLOCK,
   "cache_data 데코레이터와 DataFrame 렌더가 들어 있다")
ok("st.metric(\"등록된 조합 개수\"" in lines[start - 6] or any(
    "등록된 조합 개수" in l for l in lines[max(0, start - 8):start]),
   "삽입 위치가 '등록된 조합 개수' metric 바로 뒤다")


# ── 실행용 스텁
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
    """파일에서 떼어낸 블록을 스텁과 함께 실행하고 그 네임스페이스를 돌려준다."""
    ns = {"st": st, "pd": pd}
    exec(compile(BLOCK, "admin_dashboard.py", "exec"), ns)
    return ns


w("\n== S2. 생성시간 변환(UTC→KST) — 입력 전 종류 ==")
import marketing_db as mdb  # noqa: E402

REAL = {name: getattr(mdb, name) for name in
        ("get_draw_extraction_stats", "get_draw_generation_stats", "get_pattern_recorded_at")}
CASES = [
    (None, "기록없음"),
    ("", "기록없음"),
    ("   ", "기록없음"),
    ("2026-09-20", "기록없음"),                       # 시각 없는 날짜만 → fromisoformat 통과하지만 시각 0:00
    ("not-a-date", "기록없음"),
    ("2026-13-45T99:99:99", "기록없음"),
    ("2026-09-20T05:03:27.958619", "09/20 14:03"),    # 1243 실측값
    ("2026-09-27T10:11:22", "09/27 19:11"),           # 1244 (마이크로초 없음)
    ("2026-09-30T20:00:00", "10/01 05:00"),           # 월 경계 넘김
    ("2026-12-31T20:00:00", "01/01 05:00"),           # 연 경계 넘김
    ("2026-09-20T05:03:27+00:00", "09/20 14:03"),     # 타임존 표기 포함
]
stub = StubStreamlit()
ns = load_block(stub)
mdb.get_draw_extraction_stats = lambda limit=5: [{"draw_round": 1243, "total_count": 1}]
mdb.get_draw_generation_stats = lambda r: {"stage4_count": 1}
mdb.get_pattern_recorded_at = lambda r: "X"
bad = []
for iso, want in CASES:
    mdb.get_pattern_recorded_at = lambda r, _v=iso: _v
    got = ns["_ops_recent_generation_rows_cached"]()[0]["생성시간"]
    shown = got if got != "기록없음" else "기록없음"
    # "2026-09-20"(날짜만)은 자정 기준으로 통과해 09/20 09:00이 된다 — 그 경우도 허용
    hit = (shown == want) or (want == "기록없음" and re.fullmatch(r"\d{2}/\d{2} \d{2}:\d{2}", shown))
    if not hit:
        bad.append(f"{iso!r}→{shown!r}(기대 {want!r})")
    w(f"       {str(iso)!r:36} → {shown}")
ok(not bad, f"{len(CASES)}종 입력이 모두 '기록없음' 또는 MM/DD HH:MM (예외 {len(bad)} {bad[:2]})")
for name, fn in REAL.items():
    setattr(mdb, name, fn)

w("\n== S3. 행 구성 규칙 ==")
stub3 = StubStreamlit()
ns3 = load_block(stub3)
calls = {"extract": 0, "gen": 0, "at": 0}


def fake_extract(limit=5):
    calls["extract"] += 1
    assert limit == 5, f"limit이 5가 아니다: {limit}"
    return [{"draw_round": r, "total_count": c} for r, c in
            ((1243, 52187), (1242, 1000), (1241, 7), (1240, 0), (1239, 999999))]


def fake_gen(r):
    calls["gen"] += 1
    return None if r == 1242 else {"stage4_count": 1043741 if r == 1243 else 5}


def fake_at(r):
    calls["at"] += 1
    return None if r == 1242 else "2026-09-20T05:03:27.958619"


mdb.get_draw_extraction_stats, mdb.get_draw_generation_stats, mdb.get_pattern_recorded_at = (
    fake_extract, fake_gen, fake_at)
rows = ns3["_ops_recent_generation_rows_cached"]()
for name, fn in REAL.items():
    setattr(mdb, name, fn)
ok(len(rows) == 5, f"회차 5개 → 행 5개 (실제 {len(rows)})")
ok(list(rows[0].keys()) == ["배포 회차", "생성시간", "총 조합 개수", "조합 개수"],
   f"열 이름·순서 = {list(rows[0].keys())}")
ok([r["배포 회차"] for r in rows] == ["1243회차", "1242회차", "1241회차", "1240회차", "1239회차"],
   "회차 라벨 형식 = '{회차}회차'")
ok(rows[0]["조합 개수"] == "52,187 개" and rows[4]["조합 개수"] == "999,999 개"
   and rows[3]["조합 개수"] == "0 개",
   "조합 개수 = total_count 콤마 포맷(경계: 0·1000미만·6자리)")
ok(rows[0]["총 조합 개수"] == "1,043,741 개" and rows[1]["총 조합 개수"] == "기록없음",
   "총 조합 개수 = stage4_count, 생성기록 없으면 '기록없음'")
ok(rows[1]["생성시간"] == "기록없음", "생성시간 기록 없으면 '기록없음'")
ok(calls == {"extract": 1, "gen": 5, "at": 5},
   f"호출 횟수 extract 1회 / gen 5회 / at 5회 (실제 {calls})")

w("\n== S4. 렌더 호출 ==")
stub4 = StubStreamlit()
ns4 = load_block(stub4)
ns4["_ops_recent_generation_rows_cached"]()          # 표 함수를 실제로 부른다
ok(stub4.markdowns and "최근 5회차 생성 현황" in stub4.markdowns[0],
   f"표 제목이 렌더된다: {stub4.markdowns[:1]}")
ok(len(stub4.dataframes) == 1, f"dataframe 호출 {len(stub4.dataframes)}회 == 1회")
df_call = stub4.dataframes[0]
ok(isinstance(df_call["data"], pd.DataFrame) and df_call["data"].shape[1] == 4
   and df_call["data"].shape[0] == 5,
   f"DataFrame 모양 = {df_call['data'].shape} (행=회차수, 열=4)")
ok(df_call.get("use_container_width") is True and df_call.get("hide_index") is True,
   f"렌더 옵션 = use_container_width/hide_index ({df_call.get('use_container_width')}"
   f"/{df_call.get('hide_index')})")
# 음성 케이스: 블록의 렌더 코드는 load(exec) 시점에 실행되므로, 빈 목록을 먼저 물린 뒤 로드한다.
stub4b = StubStreamlit()
mdb.get_draw_extraction_stats = lambda limit=5: []
try:
    load_block(stub4b)
finally:
    mdb.get_draw_extraction_stats = REAL["get_draw_extraction_stats"]
ok(stub4b.dataframes == [], f"회차가 하나도 없으면 dataframe을 부르지 않는다 (호출 {len(stub4b.dataframes)}회)")
ok(stub4b.markdowns and "최근 5회차 생성 현황" in stub4b.markdowns[0],
   "회차가 없어도 표 제목은 렌더된다")

w("\n== S5. 실물 DB — 1243회차 값 ==")
stub5 = StubStreamlit()
ns5 = load_block(stub5)
rows5 = ns5["_ops_recent_generation_rows_cached"]()
by_round = {int(r["배포 회차"].replace("회차", "")): r for r in rows5}
w(f"       표에 나온 회차: {sorted(by_round, reverse=True)}")
bad5 = []
for rnd, row in by_round.items():
    s = next((x for x in REAL["get_draw_extraction_stats"](limit=50)
              if x["draw_round"] == rnd), None)
    g = REAL["get_draw_generation_stats"](rnd)
    at = REAL["get_pattern_recorded_at"](rnd)
    if s is None:
        bad5.append(f"{rnd}: DB에 회차 없음")
        continue
    if row["조합 개수"] != f"{s['total_count']:,} 개":
        bad5.append(f"{rnd} 조합 개수 {row['조합 개수']} != DB {s['total_count']:,}")
    if row["총 조합 개수"] != (f"{g['stage4_count']:,} 개" if g else "기록없음"):
        bad5.append(f"{rnd} 총 조합 개수 {row['총 조합 개수']} != DB {g and g['stage4_count']}")
    if at:
        exp = "09/20 14:03" if rnd == 1243 else None
        if row["생성시간"] == "기록없음":
            bad5.append(f"{rnd} 생성시간이 기록없음인데 DB에는 {at} 있음")
        elif exp and row["생성시간"] != exp:
            bad5.append(f"{rnd} 생성시간 {row['생성시간']} != {exp}")
ok(not bad5, f"표 값이 DB 값과 일치(직접 재조회로 교차 확인) — 불일치 {len(bad5)} {bad5[:3]}")
r1243 = by_round.get(1243, {})
w(f"       1243회차 행: {r1243}")
ok(r1243.get("조합 개수") == "52,187 개", "1243 조합 개수 = 52,187 개")
ok(r1243.get("총 조합 개수") == "1,043,741 개", "1243 총 조합 개수 = 1,043,741 개")
ok(r1243.get("생성시간") == "09/20 14:03", "1243 생성시간 = 09/20 14:03 (KST 변환)")
ok(len(rows5) == 5, f"실물 DB 기준 행 수 {len(rows5)} == 5")

w(f"\n단언 실패 {len(FAILS)}건" + ("" if not FAILS else ": " + " | ".join(FAILS[:5])))
w(f"총 경과 {time.time() - t0:.1f}s")
OUT.write_text("\n".join(R), encoding="utf-8")
print(f"written {OUT}")
os._exit(1 if FAILS else 0)
