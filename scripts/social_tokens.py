# -*- coding: utf-8 -*-
"""SNS 자동 게시용 키 발급 도우미 — 사용자 PC 에서 1회 실행(2026-10-17).

출력되는 값은 GitHub 저장소 Settings → Secrets and variables → Actions → Secrets 에 직접 넣는다.
값을 채팅·파일·깃에 남기지 말 것(이 스크립트도 화면에만 출력하고 저장하지 않는다).

  python scripts/social_tokens.py meta     # 페이스북 페이지 + 인스타 → META_PAGE_ID, META_PAGE_TOKEN, IG_USER_ID
  python scripts/social_tokens.py threads  # 스레드 → THREADS_USER_ID, THREADS_TOKEN(60일, 이후 자동 갱신)
  python scripts/social_tokens.py youtube  # 유튜브 → YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
"""
from __future__ import annotations

import sys
import time

import requests

GRAPH = "https://graph.facebook.com/v25.0"
THREADS = "https://graph.threads.net"


def _clipboard() -> str:
    try:
        import subprocess
        return subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                              capture_output=True, text=True, timeout=10).stdout or ""
    except Exception:
        return ""


def _ask(label: str, secret: bool = True) -> str:
    """2026-10-17: 숨김 입력은 윈도우에서 붙여넣기가 깨졌다 → 보이는 입력 + '그냥 Enter = 클립보드에서 읽기'.
    공백·따옴표·제어문자를 지우고, 비어 있으면 다시 묻는다."""
    for _ in range(3):
        raw = input(f"{label} — 복사해 두고 그냥 Enter(또는 붙여넣기 후 Enter): ")
        if not raw.strip():
            raw = _clipboard()
        val = "".join(ch for ch in raw if ch.isprintable()).strip().strip("'\"").replace(" ", "")
        if val:
            if secret:
                print(f"  → 입력됨({len(val)}자, 앞 4자 {val[:4]}…)")
            return val
        print("  (비어 있습니다 — 다시 복사한 뒤 Enter)")
    sys.exit(f"{label} 입력이 없어 중단합니다.")


def meta() -> None:
    print("Graph API 탐색기에서 받은 '사용자 액세스 토큰'(짧은 토큰)과 앱 ID·앱 시크릿을 넣으세요.")
    app_id = _ask("앱 ID", secret=False)
    app_secret = _ask("앱 시크릿")
    short = _ask("사용자 액세스 토큰")
    r = requests.get(f"{GRAPH}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret,
        "fb_exchange_token": short}, timeout=60).json()
    if "access_token" not in r:
        sys.exit(f"장기 토큰 교환 실패: {r}")
    pages = requests.get(f"{GRAPH}/me/accounts", params={"access_token": r["access_token"]}, timeout=60).json()
    rows = pages.get("data") or []
    if not rows:
        sys.exit(f"관리하는 페이지가 없습니다: {pages}")
    for i, p in enumerate(rows):
        print(f"  [{i}] {p['name']}")
    p = rows[int(input("로또신령 페이지 번호: ") or 0)]
    ig = requests.get(f"{GRAPH}/{p['id']}", params={"fields": "instagram_business_account",
                                                   "access_token": p["access_token"]}, timeout=60).json()
    print("\n=== GitHub Secrets 에 넣을 값 ===")
    print("META_PAGE_ID    =", p["id"])
    print("META_PAGE_TOKEN =", p["access_token"])
    print("IG_USER_ID      =", (ig.get("instagram_business_account") or {}).get("id", "(인스타 연결 안 됨 — 페이지에 인스타 연결 후 다시)"))


def threads() -> None:
    print("Meta 앱의 Threads 사용 사례 → '사용자 토큰 생성기'에서 받은 토큰과 Threads 앱 시크릿을 넣으세요.")
    secret = _ask("Threads 앱 시크릿")
    short = _ask("Threads 사용자 토큰")
    r = requests.get(f"{THREADS}/access_token", params={
        "grant_type": "th_exchange_token", "client_secret": secret, "access_token": short}, timeout=60).json()
    tok = r.get("access_token") or short
    me = requests.get(f"{THREADS}/v1.0/me", params={"fields": "id,username", "access_token": tok}, timeout=60).json()
    print("\n=== GitHub Secrets 에 넣을 값 ===")
    print("THREADS_USER_ID =", me.get("id"), f"(@{me.get('username')})")
    print("THREADS_TOKEN   =", tok)


def youtube() -> None:
    print("구글 클라우드 콘솔 → OAuth 클라이언트(유형: 'TV 및 입력이 제한된 기기')의 ID·시크릿을 넣으세요.")
    cid = _ask("클라이언트 ID", secret=False)
    csec = _ask("클라이언트 보안 비밀")
    d = requests.post("https://oauth2.googleapis.com/device/code", data={
        "client_id": cid, "scope": "https://www.googleapis.com/auth/youtube"}, timeout=60).json()
    if "device_code" not in d:
        sys.exit(f"기기 코드 발급 실패: {d}")
    print(f"\n1) 브라우저에서 {d['verification_url']} 를 열고\n2) 코드 {d['user_code']} 입력\n"
          "3) '로또신령' 유튜브 채널(브랜드 계정)을 고르고 허용")
    while True:
        time.sleep(int(d.get("interval", 5)))
        t = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": cid, "client_secret": csec, "device_code": d["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}, timeout=60).json()
        if "refresh_token" in t:
            break
        if t.get("error") not in ("authorization_pending", "slow_down"):
            sys.exit(f"승인 실패: {t}")
    print("\n=== GitHub Secrets 에 넣을 값 ===")
    print("YT_CLIENT_ID      =", cid)
    print("YT_CLIENT_SECRET  =", csec)
    print("YT_REFRESH_TOKEN  =", t["refresh_token"])


if __name__ == "__main__":
    {"meta": meta, "threads": threads, "youtube": youtube}[sys.argv[1] if len(sys.argv) > 1 else "meta"]()
