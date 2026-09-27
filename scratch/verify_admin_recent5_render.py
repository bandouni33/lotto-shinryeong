# -*- coding: utf-8 -*-
"""관리자 대시보드 페이지를 실제로 실행해 '최근 5회차 생성 현황' 표가 렌더되는지 확인.

단위 테스트가 아니라 진입점 검증이다 — Streamlit 자체 헤드리스 러너(AppTest)로
admin_dashboard.py를 is_admin=True 세션으로 돌리고, 렌더된 요소에서
①표 제목 ②표(DataFrame) 4열 5행 ③1243회차 값 을 직접 확인한다.

실행: venv312\\Scripts\\python.exe scratch\\verify_admin_recent5_render.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from env_loader import load_dotenv_file  # noqa: E402

load_dotenv_file()

OUT = ROOT / "scratch" / "verify_admin_recent5_render_out.txt"
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


import streamlit as st  # noqa: E402

w(f"streamlit {st.__version__} (AppTest 사용)")

from streamlit.testing.v1 import AppTest  # noqa: E402

at = AppTest.from_file(str(ROOT / "admin_dashboard.py"), default_timeout=600)
at.session_state["is_admin"] = True
# 삽입한 블록은 1654행 `elif admin_view == "ops_manage":` 안에 있다 — 그 뷰로 들어가야 렌더된다.
at.session_state["admin_view"] = "ops_manage"
w(f"[{time.time() - t0:.0f}s] admin_dashboard.py 실행 중(is_admin=True)...")
at.run()
w(f"[{time.time() - t0:.0f}s] 실행 완료 — 예외 {len(at.exception)}건, "
  f"markdown {len(at.markdown)}개, dataframe {len(at.dataframe)}개, "
  f"warning {len(at.warning)}개, error {len(at.error)}개")

for e in at.exception[:3]:
    w(f"  [페이지 예외] {e.type}: {e.message}")
for e in at.error[:5]:
    w(f"  [st.error] {str(e.value)[:300]}")
for e in at.warning[:5]:
    w(f"  [st.warning] {str(e.value)[:200]}")
w("  --- 렌더된 markdown(앞 120자) ---")
for i, mk in enumerate(at.markdown):
    body = str(mk.value).replace("\n", " ")
    w(f"    [{i}] {body[:120]}")
w("  --- 렌더된 dataframe 열 ---")
for i, d in enumerate(at.dataframe):
    try:
        w(f"    [{i}] cols={list(d.value.columns)}")
    except Exception as e:  # noqa: BLE001
        w(f"    [{i}] 값 읽기 실패 {type(e).__name__}: {e}")

titles = [m.value for m in at.markdown if "최근 5회차 생성 현황" in (m.value or "")]
ok(bool(titles), f"표 제목 '최근 5회차 생성 현황'이 렌더됐다 ({titles[:1]})")

tabs = []
for d in at.dataframe:
    try:
        df = d.value
    except Exception as e:  # noqa: BLE001
        w(f"  [dataframe 값 읽기 실패] {type(e).__name__}: {e}")
        continue
    cols = list(getattr(df, "columns", []))
    if cols[:4] == ["배포 회차", "생성시간", "총 조합 개수", "조합 개수"]:
        tabs.append(df)

ok(bool(tabs), f"4열짜리 생성현황 표가 렌더됐다 (해당 dataframe {len(tabs)}개 / 전체 {len(at.dataframe)}개)")
if tabs:
    df = tabs[0]
    w("  렌더된 표:")
    for line in df.to_string(index=False).splitlines():
        w(f"    {line}")
    ok(df.shape[0] == 5 and df.shape[1] == 4, f"표 모양 = {df.shape} (5행 4열)")
    row = df[df["배포 회차"] == "1243회차"]
    ok(len(row) == 1, "1243회차 행이 표에 있다")
    if len(row) == 1:
        r = row.iloc[0].to_dict()
        ok(r["조합 개수"] == "52,187 개", f"1243 조합 개수 = {r['조합 개수']} (DB 52,187)")
        ok(r["총 조합 개수"] == "1,043,741 개",
           f"1243 총 조합 개수 = {r['총 조합 개수']} (DB stage4 1,043,741)")
        ok(r["생성시간"] == "09/20 14:03",
           f"1243 생성시간 = {r['생성시간']} (DB 2026-09-20T05:03:27 UTC → KST)")

        # ② 연속 5회차 강제 — 최신부터 1씩 감소, 건너뛴 회차가 없어야 한다
        labels = list(df["배포 회차"])
        latest = int(labels[0].replace("회차", ""))
        ok(labels == [f"{latest - i}회차" for i in range(5)],
           f"표 회차가 최신 {latest}부터 연속 5개: {labels}")
        ok("1236회차" not in labels
           and all(int(l.replace("회차", "")) >= latest - 4 for l in labels),
           "건너뛴 옛 회차(1236 등)가 표에 없다")

        # ③ 표 값 == DB 값 (기록 없는 회차는 '기록없음')
        import marketing_db as mdb

        bad = []
        for lab in labels:
            rnd = int(lab.replace("회차", ""))
            row = df[df["배포 회차"] == lab].iloc[0].to_dict()
            g = mdb.get_draw_generation_stats(rnd)
            c = mdb.get_combination_count_by_draw(rnd)
            at = mdb.get_pattern_recorded_at(rnd)
            if row["총 조합 개수"] != (f"{g['stage4_count']:,} 개" if g else "기록없음"):
                bad.append(f"{rnd} 총 조합 개수 {row['총 조합 개수']} != DB {g and g['stage4_count']}")
            if row["조합 개수"] != (f"{c:,} 개" if c else "기록없음"):
                bad.append(f"{rnd} 조합 개수 {row['조합 개수']} != DB {c}")
            if (at is None) != (row["생성시간"] == "기록없음"):
                bad.append(f"{rnd} 생성시간 {row['생성시간']} / DB {at}")
        ok(not bad, f"렌더된 표 값 == DB 값(교차 확인) — 불일치 {len(bad)} {bad[:3]}")
        none_rows = [r["배포 회차"] for _, r in df.iterrows() if r["조합 개수"] == "기록없음"]
        w(f"       '기록없음'으로 표시되는 회차: {none_rows}")

w(f"\n단언 실패 {len(FAILS)}건" + ("" if not FAILS else ": " + " | ".join(FAILS[:5])))
w(f"총 경과 {time.time() - t0:.0f}s")
OUT.write_text("\n".join(R), encoding="utf-8")
print(f"written {OUT}")
os._exit(1 if FAILS else 0)
