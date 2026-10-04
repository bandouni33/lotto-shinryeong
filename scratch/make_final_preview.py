"""배너 최종 적용본 미리보기 — 구름님 재컨펌용 (2026-10-04).

확정된 문구(배출 등수만 간략 표기 · 조합수량 없음 · 미사여구 없음)와
선택된 스타일(샘플 2 · 네온)을 **실제 구현 모듈 그대로** 렌더한다.
화면(win_event_banner.card_html)과 100% 같은 함수를 쓰므로 미리보기 = 실제 모달.

산출물: 배너_최종_미리보기.html (프로젝트 루트 + 내PC 다운로드 폴더)
실행: venv312\\Scripts\\python.exe -X utf8 scratch\\make_final_preview.py
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

# 1244회차 실측값(구름님이 확정 문구에 적어준 예시 그대로: 2등 1개 · 3등 18개)
EXAMPLE = {
    "draw_round": 1244,
    "rank_1": 0,
    "rank_2": 1,
    "rank_3": 18,
    "rank_4": 169,
    "rank_5": 1157,
    "stage4_count": 1_025_190,  # 화면 문구에는 쓰이지 않는다(확정: 조합수량 뺄 것)
}
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")


def main() -> int:
    card = web.card_html(EXAMPLE)  # CHOSEN_STYLE(=2) 그대로
    html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>배너 최종 적용본 (샘플 2 · 네온)</title>
<style>
  html, body {{ margin: 0; background: #0b0b10; color: #f2f2f6;
    font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; }}
  .page {{ max-width: 420px; margin: 0 auto; padding: 22px 16px 40px; }}
  .t {{ font-size: 26px; font-weight: 900; letter-spacing: -1px; text-align: center; }}
  .d {{ text-align: center; font-size: 12.5px; color: #9a9aa6; margin: 6px 0 18px; }}
  .btns {{ display: flex; gap: 10px; margin-top: 14px; }}
  .b {{ flex: 1; height: 42px; border-radius: 10px; font-size: 14px; font-weight: 800;
    border: 1px solid #3a3a46; background: #1b1b22; color: #e8e8ee; }}
  .b.primary {{ background: linear-gradient(180deg, #2f6df6, #2456c8); border-color: #2f6df6; color: #fff; }}
  .foot {{ margin-top: 18px; font-size: 11.5px; color: #7c7c88; line-height: 1.7; }}
</style></head>
<body>
  <div class="page">
    <div class="t">최종 적용본</div>
    <div class="d">샘플 2 · 네온 — 확정 문구(배출 등수만 · 조합수량 없음 · 미사여구 없음)</div>
    {card}
    <div class="btns">
      <button class="b" type="button">{web.BTN_NEVER}</button>
      <button class="b primary" type="button">{web.BTN_OK}</button>
    </div>
    <div class="foot">
      · 애니메이션(테두리 맥동)은 페이지를 열 때 1회 재생됩니다 — 다시 보려면 새로고침.<br>
      · 아래 버튼은 실제 모달과 같은 자리·규격입니다(이 미리보기 파일에서는 동작하지 않습니다).<br>
      · 이 카드 HTML은 실제 화면(win_event_banner.card_html)과 같은 함수가 만든 것입니다.
    </div>
  </div>
</body></html>
"""
    path = ROOT / "배너_최종_미리보기.html"
    path.write_text(html, encoding="utf-8")
    target = os.path.join(DOWNLOADS, path.name)
    shutil.copy2(path, target)
    same = path.read_bytes() == open(target, "rb").read()

    checks = {
        "스타일 2 적용": web.CHOSEN_STYLE == 2,
        "제목에 배출 등수만": f"{EXAMPLE['draw_round']}회차 결과 — 2등 배출" in html,
        "기준선(조합수량 없음)": "필터 통과 조합 기준" in html,
        "등수만 간략 표기": "2등 1개 · 3등 18개" in html,
        "조합수량 숫자 없음": "1,025,190" not in html and "939,330" not in html,
        "미배출 등수 없음": "1등 0개" not in html and "4등" not in html and "5등" not in html,
        "미사여구 없음": "나왔습니다" not in html and "참고 통계" not in html,
        "다운로드 사본 동일": same,
    }
    for label, ok in checks.items():
        print(("  PASS  " if ok else "  FAIL  ") + label)
    failed = [label for label, ok in checks.items() if not ok]
    print(f"\n미리보기: {path.name} ({path.stat().st_size} bytes)")
    print(f"결과: {'전부 통과' if not failed else str(len(failed)) + '건 실패'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
