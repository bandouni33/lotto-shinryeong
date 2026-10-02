"""eas.json 제출 프로필의 불변식 — beta 트랙 고정 (2026-10-02).

배경: 지시는 "`eas submit --platform android --latest --track beta` — --track을 빼면
기본값이 production이라 바로 정식 출시된다"였는데, 설치된 eas-cli 21.0.2에는 그 플래그가
없다(--help 확인 → "Nonexistent flag: --track"). 즉 **트랙을 정하는 자리는 eas.json의
제출 프로필 하나뿐**이고, 그 프로필이 곧 "정식 출시를 막는 장치"가 된다. 장치가 조용히
풀리면(프로필 이름 변경·track 오타·기본값 의존) 다음 제출이 production으로 나간다.

  J1. eas.json이 JSON으로 파싱되고 cli/build/submit이 그대로 있다.
  J2. 테스터 제출에 쓰는 beta 프로필이 track을 'beta'로 **명시**한다(기본값 의존 금지).
  J3. 모든 submit 프로필의 android.track은 문서상 enum(production|beta|alpha|internal)이다
      — 오타 난 트랙명은 EAS가 에러 없이 기본값으로 흘릴 수 있다.
  J4. HEAD 대비 변경은 submit.beta 추가뿐이다: HEAD에 있던 값(빌드 프로필의
      APK/스토어 설정·버전코드 자동증가, submit.production의 ios ascAppId)은 그대로다
      — 이 변경이 빌드 설정이나 iOS에 손을 대지 않았다는 것을 값으로 증명한다.
  J5. iOS 제출 설정(ascAppId)이 이번에도 그대로다(별도 실행 항목으로 못 박아 둔다).

pytest 없음(이 프로젝트 규칙) — 표준 assert + `__main__` 러너.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
EAS_REL = "LottoShinryeong/eas.json"
EAS_JSON = ROOT / EAS_REL
ALLOWED_TRACKS = {"production", "beta", "alpha", "internal"}
BETA_PROFILE = "beta"
IOS_ASC_APP_ID = "6807004547"


def _load_current() -> dict:
    return json.loads(EAS_JSON.read_text(encoding="utf-8"))


def _load_head() -> dict:
    shown = subprocess.run(
        ["git", "show", f"HEAD:{EAS_REL}"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert shown.returncode == 0, f"HEAD의 eas.json을 읽지 못했다: {shown.stderr[:200]}"
    return json.loads(shown.stdout)


def _flatten(node, prefix: str = "") -> dict:
    """중첩 JSON을 '경로 -> 값'으로 펴서 값 단위로 비교한다(키 순서에 기대지 않는다)."""
    flat: dict = {}
    if isinstance(node, dict):
        for key, value in node.items():
            flat.update(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    else:
        flat[prefix] = node
    return flat


# ── J1: 파일이 성립하는가 ────────────────────────────────────────────────────
def test_J1_eas_json_parses_with_expected_sections() -> None:
    cur = _load_current()
    assert isinstance(cur, dict), f"eas.json 최상위가 객체가 아니다: {type(cur).__name__}"
    for key in ("cli", "build", "submit"):
        assert key in cur, f"eas.json에 {key} 섹션이 없다"
    assert isinstance(cur["submit"], dict), "submit이 프로필 객체가 아니다"
    print(f"  (J1 eas.json 파싱됨 - submit 프로필: {sorted(cur['submit'])}")


# ── J2: 정식 출시를 막는 장치가 실제로 걸려 있는가 ───────────────────────────
def test_J2_the_beta_profile_pins_the_beta_track() -> None:
    submit = _load_current()["submit"]
    assert BETA_PROFILE in submit, (
        f"'{BETA_PROFILE}' 제출 프로필이 없다 - `--profile beta`가 production 기본 프로필로 흘러 정식 출시된다"
    )
    android = submit[BETA_PROFILE].get("android") or {}
    assert android.get("track") == "beta", (
        f"beta 프로필의 track이 'beta'로 명시돼 있지 않다: {android!r}"
    )
    print(f"  (J2 submit.{BETA_PROFILE}.android.track = 'beta' 명시 확인)")


# ── J3: 트랙 이름 오타 방지 ─────────────────────────────────────────────────
def test_J3_every_profile_track_is_a_known_track_name() -> None:
    submit = _load_current()["submit"]
    seen = {}
    for name, profile in submit.items():
        android = (profile or {}).get("android") or {}
        if "track" in android:
            seen[name] = android["track"]
            assert android["track"] in ALLOWED_TRACKS, (
                f"submit.{name}.android.track={android['track']!r}는 문서상 enum이 아니다: {sorted(ALLOWED_TRACKS)}"
            )
    assert seen, "어느 프로필에도 android.track이 없으면 트랙이 기본값(production)으로 나간다"
    print(f"  (J3 트랙 명시 프로필: {seen} - 전부 허용 enum)")


# ── J4: 변경 범위가 submit.beta 추가뿐인가 ───────────────────────────────────
def test_J4_only_the_beta_submit_block_was_added_since_head() -> None:
    head = _flatten(_load_head())
    cur = _flatten(_load_current())

    changed = {path: (value, cur[path]) for path, value in head.items() if cur.get(path) != value}
    assert not changed, f"HEAD에 있던 값이 바뀌었다(빌드 설정·iOS 포함): {changed!r}"

    added = [path for path in cur if path not in head]
    stray = [path for path in added if not path.startswith(f"submit.{BETA_PROFILE}.")]
    assert not stray, f"submit.{BETA_PROFILE} 밖에 값이 추가됐다: {stray!r}"
    if added:
        print(f"  (J4 변경 범위: 추가 {len(added)}개 경로, 전부 submit.{BETA_PROFILE} 아래 - 기존 값 변경 0건)")
    else:
        # eas.json이 커밋된 뒤에는 'HEAD 대비 추가'가 없다 — 그때 이 테스트는 "기존 값이
        # 하나도 안 바뀌었다"만 주장한다(트랙 고정 자체는 J2가 계속 지킨다).
        print("  (J4 HEAD와 동일: 기존 값 변경 0건 - beta 프로필은 이미 커밋된 상태)")


# ── J5: iOS 제출 설정 불변 ──────────────────────────────────────────────────
def test_J5_ios_submit_config_is_untouched() -> None:
    submit = _load_current()["submit"]
    production = submit.get("production") or {}
    asc = (production.get("ios") or {}).get("ascAppId")
    assert asc == IOS_ASC_APP_ID, f"iOS 제출 설정이 바뀌었다: {asc!r}"
    assert production.get("ios") == (_load_head()["submit"]["production"].get("ios")), (
        "submit.production.ios가 HEAD와 다르다"
    )
    for name, profile in submit.items():
        assert (profile or {}).get("ios") == (_load_head()["submit"].get(name, {}).get("ios")), (
            f"submit.{name}.ios가 HEAD와 다르다 - 이번 변경은 Android 트랙만 다룬다"
        )
    print(f"  (J5 iOS 제출 설정: submit.production.ios.ascAppId = {asc} (HEAD와 동일))")


def _main() -> int:
    tests = [
        test_J1_eas_json_parses_with_expected_sections,
        test_J2_the_beta_profile_pins_the_beta_track,
        test_J3_every_profile_track_is_a_known_track_name,
        test_J4_only_the_beta_submit_block_was_added_since_head,
        test_J5_ios_submit_config_is_untouched,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
        sys.stdout.flush()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.stdout.flush()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
