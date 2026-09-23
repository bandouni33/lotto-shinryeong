"""manual_ui.py 초안 검증 — 컨펌 전에 확인해야 할 불변식(M1~M5).

  M1. 항목은 7개, 모든 필수 키가 채워져 있고 빈 문자열이 없다.
  M2. 적립금 문구는 하드코딩이 아니라 legal_notices.PRICING에서 계산돼 들어간다
      (값을 바꾸면 문구도 같이 바뀐다 — 설명서가 실제 가격과 어긋나지 않는다).
  M3. "배포 시간" 표기가 실제 코드와 일치한다:
        · 자동조합 = 화 09:00~토 19:55 (sales_window.is_sales_window_open 과 동일)
        · 번개조합/번호검증 = 제한 없음 (해당 화면 소스가 sales_window를 부르지 않음)
  M4. 렌더 HTML이 온전하다 — 태그 짝이 맞고, 7개 제목이 모두 들어가며, None/미치환 표기가 없다.
  M5. 다이얼로그와 트리거 버튼이 예외 없이 뜨고, 버튼 클릭이 rerun 없이 열림 플래그만 세운다.

실행: venv312\\Scripts\\python.exe scratch\\verify_manual_ui.py
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _db_isolation  # noqa: E402

TIMEOUT_SEC = 60
failures: list[str] = []

# 기대 제목 — manual_ui.manual_sections()의 실제 title과 **글자 단위로** 같아야 한다.
# (여기를 줄여 쓰면 "구매복권 검증"처럼 괄호가 빠져 검증이 헛돌게 된다 — 실제로 이 검증에서
#  한 번 그렇게 어긋나 잡혔다. 제목을 바꿀 때는 이 목록도 같이 고칠 것.)
TITLES = [
    "타로점",
    "자동조합",
    "번개조합",
    "번호 검증 (전체·개별리셋)",
    "고급필터",
    "통계센터",
    "고객불만 / 개선요구사항",
]
REQUIRED_KEYS = ("no", "icon", "title", "badge", "summary", "steps", "price", "notes")


def _manual():
    import manual_ui

    return manual_ui


def check_structure() -> None:
    """M1 — 7개 · 필수 키 · 빈 값 없음."""
    sections = _manual().manual_sections()
    print(f"M1 항목 수: {len(sections)}")
    if len(sections) != 7:
        failures.append(f"M1: 항목이 7개가 아니다 ({len(sections)})")
    for section in sections:
        for key in REQUIRED_KEYS:
            value = section.get(key)
            if value in (None, "", [], ()):
                failures.append(f"M1: {section.get('title')}의 '{key}'가 비어 있다")
        for key in ("title", "badge", "summary", "price"):
            text = section.get(key) or ""
            if "None" in text or "{" in text:
                failures.append(f"M1: {section.get('title')}의 '{key}'에 미치환 표기: {text!r}")
        for step in section["steps"]:
            if not step.strip() or "None" in step:
                failures.append(f"M1: {section['title']} 단계 문구 이상: {step!r}")
    titles = [s["title"] for s in sections]
    print(f"   제목: {titles}")
    if titles != TITLES:
        failures.append(f"M1: 제목 목록이 기대와 다르다 {titles}")


def check_prices_follow_pricing() -> None:
    """M2 — 가격은 PRICING에서 계산된 값이어야 한다(하드코딩 금지)."""
    from legal_notices import PRICING

    sections = {s["title"]: s for s in _manual().manual_sections()}
    checks = (
        ("타로점", f"{PRICING['tarot_extra_draw']:,}P"),
        ("자동조합", f"{PRICING['auto_per_unit'] * 5:,}P"),
        ("번개조합", f"{PRICING['thunder_per_game'] * 10:,}P"),
        ("번호 검증 (전체·개별리셋)", f"{5 * 2 * PRICING['hedge_per_combo']:,}P"),
        ("고급필터", f"{PRICING['advanced_monthly']:,}P"),
        ("고급필터", f"{PRICING['advanced_3month']:,}P"),
    )
    for title, expected in checks:
        text = sections[title]["price"]
        ok = expected in text
        print(f"M2 {'OK ' if ok else '!! '} {title:28} '{expected}' 포함 여부 → {ok}")
        if not ok:
            failures.append(f"M2: {title} 문구에 {expected}가 없다 ({text!r})")

    # PRICING 값을 다른 곳에서 바꾸면 문구가 따라 움직이는지(하드코딩이면 안 움직인다).
    import legal_notices

    original = legal_notices.PRICING["auto_per_unit"]
    try:
        legal_notices.PRICING["auto_per_unit"] = 77
        sections2 = {s["title"]: s for s in _manual().manual_sections()}
        moved = "385P" in sections2["자동조합"]["price"]  # 77 × 5
        print(f"M2   가격 변경 반영(50P→385P): {moved}")
        if not moved:
            failures.append("M2: PRICING을 바꿔도 문구가 따라오지 않는다(하드코딩 의심)")
    finally:
        legal_notices.PRICING["auto_per_unit"] = original


def _calls_sales_window(path: Path) -> bool:
    """그 화면 소스가 is_sales_window_open()을 실제로 호출하는지(AST 검사)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {"is_sales_window_open", "_is_auto_deploy_window_open"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            target = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if target in names:
                return True
    return False


def check_sales_window_matches_code() -> None:
    """M3 — 설명서의 '배포 시간' 주장이 코드와 일치하는지."""
    from sales_window import is_sales_window_open

    assert is_sales_window_open is not None
    sections = {s["title"]: s for s in _manual().manual_sections()}

    auto_badge = sections["자동조합"]["badge"]
    ok = "화 09:00" in auto_badge and "토 19:55" in auto_badge
    print(f"M3 {'OK ' if ok else '!! '} 자동조합 배지 → {auto_badge!r}")
    if not ok:
        failures.append(f"M3: 자동조합 배지가 sales_window 규칙과 다르다: {auto_badge!r}")

    # 자동조합만 sales_window를 실제로 '호출'한다 → 나머지는 '제한 없음'이 맞다.
    # 단순 문자열 검색은 주석에 남은 함수 이름까지 잡으므로 AST로 호출만 본다
    # (page_thunder.py/page_hedge.py는 제거 이력을 설명하는 주석에 이름이 남아 있다).
    uses = {name: _calls_sales_window(ROOT / name) for name in
            ("page_auto.py", "page_thunder.py", "page_hedge.py")}
    print(f"M3   화면별 sales_window 실제 호출: {uses}")
    if not uses["page_auto.py"]:
        failures.append("M3: 자동조합이 sales_window를 안 쓴다 — 설명서 전제가 깨졌다")
    if uses["page_thunder.py"] or uses["page_hedge.py"]:
        failures.append(
            "M3: 번개조합/번호검증이 다시 시간 제한을 쓰기 시작했다 — "
            "설명서의 '제한 없음' 문구를 고쳐야 한다"
        )
    for title in ("번개조합", "번호 검증 (전체·개별리셋)"):
        badge = sections[title]["badge"]
        if "제한 없음" not in badge:
            failures.append(f"M3: {title} 배지에 '제한 없음'이 없다: {badge!r}")


def check_html_rendering() -> None:
    """M4 — 렌더 HTML 온전성(태그 짝·제목·미치환 표기)."""
    ui = _manual()
    html = ui.manual_css() + ui.manual_overview_html()
    for section in ui.manual_sections():
        html += ui.manual_section_html(section)
    html += ui.manual_footer_html()

    opens, closes = html.count("<div"), html.count("</div>")
    ul_open, ul_close = html.count("<ul"), html.count("</ul>")
    li_open, li_close = html.count("<li"), html.count("</li>")
    print(f"M4 태그 짝: div {opens}/{closes} · ul {ul_open}/{ul_close} · li {li_open}/{li_close}")
    if opens != closes or ul_open != ul_close or li_open != li_close:
        failures.append("M4: HTML 태그 짝이 맞지 않는다")
    if "None" in html or "{" in html.split("<style>")[0]:
        failures.append("M4: HTML에 미치환 표기가 있다")
    for title in TITLES:
        if title not in html:
            failures.append(f"M4: 제목이 HTML에 없다: {title}")
    # 2026-09-23: 표지 카드("USER GUIDE" 등)는 다이얼로그 제목과 중복이라 사용자 지시로
    # 뺐다 — 그래서 이 라벨 목록에서도 뺐다(디자인이 바뀌면 검증도 같이 고친다).
    for label in ("이렇게 사용하세요", "적립금", "알아두세요"):
        if label not in html:
            failures.append(f"M4: 메뉴얼 섹션 라벨이 없다: {label}")
    print(f"M4 렌더 HTML 길이: {len(html):,}자 · 7개 제목·섹션 라벨 확인")


_DIALOG_APP = """
import streamlit as st
from manual_ui import manual_dialog

st.session_state["runs"] = st.session_state.get("runs", 0) + 1
manual_dialog()
"""

_TRIGGER_APP = """
import streamlit as st
from manual_ui import maybe_open_manual, render_manual_trigger_button

st.session_state["runs"] = st.session_state.get("runs", 0) + 1
render_manual_trigger_button()
maybe_open_manual()
"""


def check_dialog_and_trigger() -> None:
    """M5 — 다이얼로그/버튼이 예외 없이 뜨고, 클릭이 rerun 없이 플래그만 세운다."""
    ui = _manual()

    at = AppTest.from_string(_DIALOG_APP, default_timeout=TIMEOUT_SEC)
    at.run()
    if len(at.exception) != 0:
        failures.append(f"M5: 설명서 다이얼로그가 예외를 냈다 — {at.exception}")
    dialog_text = "\n".join((m.value or "") for m in at.markdown)
    found = [t for t in TITLES if t in dialog_text]
    print(f"M5 다이얼로그: 예외 {len(at.exception)}건 · 본문에 잡힌 제목 {len(found)}/{len(TITLES)}")

    at2 = AppTest.from_string(_TRIGGER_APP, default_timeout=TIMEOUT_SEC)
    at2.run()
    if len(at2.exception) != 0:
        failures.append(f"M5: 트리거 버튼 렌더가 예외를 냈다 — {at2.exception}")
    if at2.session_state["runs"] != 1:
        failures.append(f"M5: 초기 실행 횟수가 1이 아니다 ({at2.session_state['runs']})")

    buttons = [b.key for b in at2.button]
    print(f"M5 트리거 버튼 keys: {buttons}")
    if "manual_trigger_btn" not in buttons:
        failures.append("M5: manual_trigger_btn이 렌더되지 않았다")
        return

    at2.button(key="manual_trigger_btn").click().run()
    runs = at2.session_state["runs"]
    # on_click 콜백이 먼저 돌아 플래그를 세우고, 같은 렌더 본문의 maybe_open_manual()이
    # 곧바로 소비해 다이얼로그를 연다 — 그래서 확인할 것은 '플래그가 남아있는지'가 아니라
    # '다이얼로그가 실제로 떴는지'다(플래그는 정상 동작에서 항상 비어 있다).
    printed = "\n".join((m.value or "") for m in at2.markdown)
    # "USER GUIDE" 표지 카드를 뺐으므로(2026-09-23) 대신 실제 항목 제목("타로점")으로
    # 다이얼로그가 열렸는지 확인한다 — 표지 문구가 아니라 실제 콘텐츠 렌더 여부가 핵심.
    dialog_shown = "타로점" in printed and "사용설명서" in printed
    print(f"M5 클릭 결과: runs={runs} · 다이얼로그 열림={dialog_shown} · 예외 {len(at2.exception)}건")
    if len(at2.exception) != 0:
        failures.append(f"M5: 클릭 시 예외 — {at2.exception}")
    if runs != 2:
        failures.append(f"M5: 클릭이 rerun을 유발했다(runs={runs}, 기대 2) — 안전 패턴 위반")
    if not dialog_shown:
        failures.append("M5: 클릭해도 설명서 다이얼로그가 열리지 않았다")


def check_module_not_wired() -> None:
    """M6 — 초안은 실제 앱 동작을 바꾸지 않는다: 어떤 진입점/화면도 manual_ui를 안 부른다.

    게시 전이므로 저장소 루트의 모든 *.py(초안 자신 제외)를 훑어 참조가 0건이어야 한다 —
    파일 하나만 보는 검사로는 다른 곳에 슬쩍 연결돼도 못 잡는다."""
    live = sorted(p for p in ROOT.glob("*.py") if p.name != "manual_ui.py")
    markers = ("manual_ui", "maybe_open_manual", "render_manual_trigger")
    offenders = [
        p.name
        for p in live
        if any(m in p.read_text(encoding="utf-8") for m in markers)
    ]
    print(f"M6 검사 파일 {len(live)}개 · manual_ui 참조 {len(offenders)}개 {offenders}")
    if offenders:
        failures.append(f"M6: 초안이 이미 다른 파일에 연결됐다(미연결 상태여야 함): {offenders}")


def check_all_pricing_keys_drive_text() -> None:
    """M7 — 설명서에 쓰인 **모든** PRICING 키가 문구를 실제로 움직인다(키별 하드코딩 금지)."""
    import legal_notices

    key_to_title = {
        "tarot_extra_draw": "타로점",
        "auto_per_unit": "자동조합",
        "thunder_per_game": "번개조합",
        "hedge_per_combo": "번호 검증 (전체·개별리셋)",
        "advanced_monthly": "고급필터",
        "advanced_3month": "고급필터",
    }
    for key, title in key_to_title.items():
        original = legal_notices.PRICING[key]
        try:
            legal_notices.PRICING[key] = 4321
            text = {s["title"]: s for s in _manual().manual_sections()}[title]["price"]
        finally:
            legal_notices.PRICING[key] = original
        ok = "4,321" in text
        print(f"M7 {'OK ' if ok else '!! '} {key:18} → {title} 문구 반영: {ok}")
        if not ok:
            failures.append(f"M7: PRICING[{key}] 변경이 문구에 반영되지 않는다: {text!r}")


def check_special_characters_are_safe() -> None:
    """M8 — 문구에 <, >, &, " 가 들어가도 태그가 주입되거나 짝이 깨지지 않는다.

    이 문구는 컨펌 후 사람이 계속 고치는 텍스트라(예: "1~5위 & 그룹") 특수문자가
    들어올 수 있다. 그대로 HTML에 붙으면 태그 주입/깨짐이 된다."""
    ui = _manual()
    hostile = {
        "no": "99",
        "icon": "🔮",
        "title": "<b>위험</b> & <script>x</script>",
        "badge": '제한 <없음> & "강조"',
        "summary": "요약 <i>기울임</i> & 값",
        "steps": ['1단계 <a href="#">링크</a>', "2단계 & 기호"],
        "price": "<b>9,999P</b>",
        "notes": ["주의 <script>alert(1)</script>"],
    }
    out = ui.manual_section_html(hostile)
    injected = (
        "<script>" in out or "<b>" in out or "<i>" in out or "<a href" in out
    )
    paired = out.count("<div") == out.count("</div>") and out.count("<ul") == out.count("</ul>")
    escaped = "&lt;b&gt;" in out and "&amp;" in out
    print(f"M8 태그주입 차단={not injected} · 태그짝={paired} · 이스케이프={escaped}")
    if injected:
        failures.append("M8: 문구의 태그가 그대로 HTML로 들어간다(주입 위험) — 이스케이프 필요")
    if not paired:
        failures.append("M8: 특수문자 때문에 태그 짝이 깨졌다")
    if not escaped:
        failures.append("M8: 특수문자가 이스케이프되지 않았다")

    # 이스케이프가 카드(manual_section_html)에만 적용되고 표지/목차
    # (manual_overview_html)에는 빠지는 실수를 막는다 — 같은 hostile 문구를
    # manual_sections()에 끼워 목차 경로도 독립적으로 확인한다.
    original_sections = ui.manual_sections
    ui.manual_sections = lambda: [hostile]
    try:
        overview = ui.manual_overview_html()
    finally:
        ui.manual_sections = original_sections
    ov_injected = "<script>" in overview or "<b>" in overview or "<i>" in overview
    ov_paired = overview.count("<div") == overview.count("</div>")
    ov_escaped = "&lt;b&gt;" in overview and "&amp;" in overview
    print(f"M8 표지/목차 경로: 주입 차단={not ov_injected} · 태그짝={ov_paired} · 이스케이프={ov_escaped}")
    if ov_injected:
        failures.append("M8(표지/목차): 문구의 태그가 그대로 들어간다 — 이스케이프 누락")
    if not ov_paired:
        failures.append("M8(표지/목차): 태그 짝이 깨졌다")
    if not ov_escaped:
        failures.append("M8(표지/목차): 특수문자가 이스케이프되지 않았다")


def main() -> int:
    with _db_isolation.isolated_db():
        check_structure()
        check_prices_follow_pricing()
        check_sales_window_matches_code()
        check_html_rendering()
        check_dialog_and_trigger()
        check_module_not_wired()
        check_all_pricing_keys_drive_text()
        check_special_characters_are_safe()
    print()
    if failures:
        for f in failures:
            try:
                print(f"FAIL {f}")
            except UnicodeEncodeError:
                # 콘솔 인코딩(cp949 등) 때문에 결과 출력 자체가 죽으면 검증 결과를 못 본다.
                print("FAIL " + f.encode("ascii", "replace").decode("ascii"))
        print(f"\n{len(failures)}건 실패")
        return 1
    print("M1~M8 전부 성립")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
