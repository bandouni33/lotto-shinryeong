"""읽기 전용 — Turso DB 이름과 리전을 CLI 없이 확인해 본다.

turso CLI가 이 PC에 설치돼 있지 않아 `turso db show`를 쓸 수 없다. 대시보드에서
직접 보시려면 DB 이름이 필요하므로 .env에서 호스트만 뽑는다(인증 토큰은 읽지도
않고 출력하지도 않는다). 리전은 호스트 DNS에 남은 흔적으로 추정만 해본다 —
추정이므로 그렇게 표시한다.

실행: venv312\\Scripts\\python.exe scratch\\turso_hostcheck.py
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent


def read_url() -> tuple[str, str]:
    url = os.getenv("TURSO_DATABASE_URL") or ""
    if url:
        return url, "환경변수"
    env = ROOT / ".env"
    if not env.exists():
        return "", ".env 없음"
    for line in io.open(env, encoding="utf-8", errors="replace").read().splitlines():
        m = re.match(r"\s*TURSO_DATABASE_URL\s*=\s*(.+)", line)
        if m:
            return m.group(1).strip().strip('"').strip("'"), ".env"
    return "", ".env에 항목 없음"


def main() -> int:
    url, source = read_url()
    print(f"TURSO_DATABASE_URL 출처 = {source} / 설정됨 = {bool(url)}")
    host = urlparse(url).hostname or ""
    print(f"host = {host}")
    name = host.split(".")[0] if host else ""
    print(f"DB 이름 추정 = {name}   (대시보드 'Databases' 목록에서 이 이름을 찾으시면 됩니다)")
    print("\n참고: 토큰 값은 읽지 않았고 출력에도 넣지 않았습니다.")

    print("\n--- 리전 추정 (CLI 없이) ---")
    if not host:
        print("호스트를 못 찾아 리전 추정도 못 한다.")
        return 0
    nslookup = shutil.which("nslookup")
    if not nslookup:
        print("nslookup이 없다.")
        return 0
    proc = subprocess.run([nslookup, host], capture_output=True, text=True,
                          encoding="cp949", errors="replace", timeout=30)
    print(proc.stdout.strip()[:1500])
    region_hint = re.findall(r"[a-z]{2}-[a-z]+-\d", proc.stdout)
    if region_hint:
        print(f"호스트명에서 보이는 리전 흔적 = {sorted(set(region_hint))}")
    else:
        print("호스트명에 리전 코드가 안 보인다 — 이 방법으로는 리전을 못 정한다.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
