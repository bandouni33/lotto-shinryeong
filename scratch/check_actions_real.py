# -*- coding: utf-8 -*-
"""G3 게이트가 보는 실제 데이터를 그대로 꺼내 검증한다(2026-09-27).

확인 항목:
  1. weekly_combo_gen.yml 이 원격에 존재하는가 · 최근 실행 이력(있으면 created_at UTC→KST)
  2. GitHub API가 최신순으로 주는가(actions_gate가 runs[0]을 최신으로 가정) — 실행 이력이
     있는 다른 워크플로(hourly_draw_sync.yml)로 실측
  3. UTC→KST 변환이 실제 데이터에서 맞는가 — hourly_draw_sync는 매시 정각(KST) 실행이라
     변환 후 분이 00이어야 한다(정시 스케줄 = 변환 검증용 기준).
  4. 게이트와 **완전히 같은 코드 경로**(weekly_backup_cleanup.actions_gate)로 판정을 다시
     계산해, 로그에 찍힌 판정과 일치하는지 대조.

읽기 전용. DB·백업 폴더·작업 스케줄러를 변경하지 않는다.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import weekly_backup_cleanup as wbc  # noqa: E402

KST = timezone(timedelta(hours=9))
API = "https://api.github.com/repos/{repo}/{path}"


def api(path: str) -> tuple[bool, object]:
    req = urllib.request.Request(API.format(repo=wbc.GITHUB_REPO, path=path), headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "lotto-app-backup-cleanup-verify",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def kst_of(iso: str) -> str:
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


def show_runs(label: str, path: str) -> list[dict]:
    ok, data = api(path)
    print(f"\n── {label} ──")
    print(f"  URL: {API.format(repo=wbc.GITHUB_REPO, path=path)}")
    if not ok:
        print(f"  !! 조회 실패: {data}")
        return []
    runs = data.get("workflow_runs") or []
    print(f"  총 실행 {data.get('total_count')}건 · 받은 {len(runs)}건")
    for r in runs[:8]:
        created, updated = r.get("created_at"), r.get("updated_at")
        print(f"   id={r.get('id')} event={r.get('event'):<17} branch={r.get('head_branch'):<6} "
              f"status={r.get('status'):<11} conclusion={r.get('conclusion')!s:<9} "
              f"created={created}(UTC) → {kst_of(created)}(KST)  updated={kst_of(updated)}(KST)")
    # 최신순 정렬 검증
    times = [r.get("created_at") for r in runs]
    desc = all(times[i] >= times[i + 1] for i in range(len(times) - 1))
    print(f"  → 최신순 정렬(runs[0]이 최신이라는 가정): {'OK' if desc else '!! 위반'}")
    return runs


def main() -> int:
    print("=" * 100)
    print(f"기준 시각: {wbc.now_kst().strftime('%Y-%m-%d %H:%M:%S %A')} KST "
          f"(UTC {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"감시 대상: {wbc.GITHUB_REPO} 의 {wbc.ACTIONS_WORKFLOW} (게이트는 branch=main, per_page=10)")

    ok, wfs = api("actions/workflows?per_page=50")
    print("\n── 원격 워크플로 목록 ──")
    if ok:
        for w in wfs.get("workflows", []):
            print(f"  id={w.get('id'):<12} state={w.get('state'):<12} path={w.get('path')}")
        # API는 path를 앞 슬래시 없이 준다(.github/workflows/...). 처음엔 '/.github/...'로
        # 비교해 "없음"으로 잘못 찍었다 — 비교식을 실제 응답 형태에 맞춘다.
        paths = [str(w.get("path") or "") for w in wfs.get("workflows", [])]
        want = ".github/workflows/" + wbc.ACTIONS_WORKFLOW
        found = any(p.lstrip("/") == want for p in paths)
        print(f"  → 게이트가 보는 파일 {want} 존재: {'OK(id/state는 위 목록)' if found else '!! 없음(게이트는 404로 실패 처리)'}")
    else:
        print(f"  !! 조회 실패: {wfs}")

    show_runs("weekly_combo_gen.yml — 게이트가 보는 워크플로(전체 브랜치)",
              f"actions/workflows/{wbc.ACTIONS_WORKFLOW}/runs?per_page=10")
    show_runs("weekly_combo_gen.yml — 게이트와 동일 조건(branch=main)",
              f"actions/workflows/{wbc.ACTIONS_WORKFLOW}/runs?branch=main&per_page=10")
    show_runs("hourly_draw_sync.yml — 변환·정렬 검증용(매시 정각 KST 실행)",
              "actions/workflows/hourly_draw_sync.yml/runs?per_page=10")

    print("\n" + "=" * 100)
    print("게이트 코드 경로 재계산(weekly_backup_cleanup.actions_gate)")
    today = wbc.now_kst().strftime("%Y-%m-%d")
    gate_ok, detail = wbc.actions_gate(today)
    print(f"  today={today} → {'통과' if gate_ok else '실패'} · {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
