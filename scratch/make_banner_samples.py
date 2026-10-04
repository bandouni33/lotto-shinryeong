"""1·2등 배출 배너 — 비주얼 샘플 4개 생성 (2026-10-04).

구름님이 번호로 고를 수 있게 스타일만 다르게 4개를 만든다(문구는 확정 B안 동일).
카드·CSS는 실제 구현 모듈(win_event_banner.py)의 같은 함수를 그대로 쓴다 —
샘플과 화면이 갈라지지 않게(이중 구현 방지).

예시 값은 1244회차 실측(B안 문구 예시로 확정된 그 값)이다:
  4차 통과 1,025,190개 / 1등 0 · 2등 1 · 3등 18

산출물: 샘플_1.html ~ 샘플_4.html (프로젝트 루트 + 내PC 다운로드 폴더)
실행: venv312\\Scripts\\python.exe -X utf8 scratch\\make_banner_samples.py
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import win_event_banner as web  # noqa: E402

# 확정 B안 문구의 예시값(1244회차 실측 — 설계안에 적어 구름님이 확인한 값)
EXAMPLE = {
    "draw_round": 1244,
    "rank_1": 0,
    "rank_2": 1,
    "rank_3": 18,
    "rank_4": 169,
    "rank_5": 1157,
    "stage4_count": 1_025_190,
}

DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")


def main() -> int:
    print("생성할 샘플:")
    for style_id, style in web.STYLES.items():
        print(f"  샘플 {style_id}: {style['name']} — {style['desc']}")

    written: list[str] = []
    for style_id in web.STYLES:
        path = ROOT / f"샘플_{style_id}.html"
        path.write_text(web.sample_html(style_id, EXAMPLE), encoding="utf-8")
        target = os.path.join(DOWNLOADS, path.name)
        shutil.copy2(path, target)
        same = path.read_bytes() == open(target, "rb").read()
        written.append(path.name)
        print(f"SAVED {path.name} ({path.stat().st_size} bytes) · 다운로드 사본 동일={same}")

    # 검사: 네 파일이 서로 다른 스타일이고, B안 문구·번호 라벨이 들어 있다.
    bodies = {name: (ROOT / name).read_text(encoding="utf-8") for name in written}

    def _last_style_block(text: str) -> str:
        """파일에서 마지막 <style>…</style>(= 카드 CSS)을 떼어낸다.
        앞쪽 style은 샘플 페이지 공통 CSS라 네 파일이 같은 게 정상이다."""
        return text.rsplit("<style>", 1)[1].split("</style>")[0]

    checks = {
        "4개 생성": len(bodies) == 4,
        "카드 스타일이 서로 다름": len({_last_style_block(b) for b in bodies.values()}) == 4,
        "각 파일이 자기 번호의 스타일을 쓴다": all(
            web.style_css(int(name.split("_")[1].split(".")[0])) in bodies[name]
            for name in written
        ),
        "확정 문구 동일(기준선)": all("필터 통과 조합 기준" in b for b in bodies.values()),
        "확정 문구 동일(등수)": all("2등 1개 · 3등 18개" in b for b in bodies.values()),
        "조합수량·미사여구 없음": all(
            "1,025,190" not in b and "나왔습니다" not in b for b in bodies.values()
        ),
        "번호 라벨": all(f"샘플 {i}" in bodies[f"샘플_{i}.html"] for i in web.STYLES),
        "버튼 2개 규격": all("다시 보지 않기" in b and ">확인<" in b for b in bodies.values()),
        "다운로드 사본 동일": all(
            open(os.path.join(DOWNLOADS, n), "rb").read() == (ROOT / n).read_bytes()
            for n in written
        ),
    }
    for label, ok in checks.items():
        print(("  PASS  " if ok else "  FAIL  ") + label)
    failed = [label for label, ok in checks.items() if not ok]
    print(f"\n결과: {'전부 통과' if not failed else str(len(failed)) + '건 실패'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
