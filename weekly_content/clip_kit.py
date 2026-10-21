"""네이버 클립 수동 업로드용 묶음 — 2026-10-20 사용자 결정("클립용은 만들어주면 내 PC에 받아서 내가 올림").

네이버 클립은 공개 업로드 API 가 없어 자동 게시가 불가하다(확인 2026-10-21). 그래서 목·금·토 실행이 만든 세로 영상
({회차}_shorts.mp4) 옆에 '네이버클립_{회차}_{종류}.txt'(제목·설명·해시태그)를 같이 둔다. 둘 다 Actions 실행 기록의
Artifacts(zip)에 담기므로 PC 에서 받아 클립 크리에이터(PC 웹/앱)에 올리면 된다.
문구는 채널 문구 한 곳(cards.captions_all·pre_draw.captions)에서 가져온다 — 제목=유튜브 제목, 설명=인스타 문구.
"""
from __future__ import annotations

import json
from pathlib import Path

CLIP_TITLE_MAX = 40   # 클립 제목은 짧게(목록에서 잘리지 않게)


def write(out: Path, rnd: int, kind: str) -> Path | None:
    """out/{rnd}_captions.json 을 읽어 out/네이버클립_{rnd}_{kind}.txt 를 쓴다. 영상·문구가 없으면 건너뜀."""
    out = Path(out)
    cap_path = out / f"{rnd}_captions.json"
    if not cap_path.exists() or not (out / f"{rnd}_shorts.mp4").exists():
        return None
    caps = json.loads(cap_path.read_text(encoding="utf-8"))
    title = (caps.get("youtube_title") or f"{rnd}회 로또신령").strip()
    if len(title) > CLIP_TITLE_MAX:
        title = title[: CLIP_TITLE_MAX - 1].rstrip() + "…"
    body = (caps.get("instagram") or caps.get("facebook") or "").strip()
    path = out / f"네이버클립_{rnd}_{kind}.txt"
    path.write_text(
        f"[영상 파일] {rnd}_shorts.mp4\n\n[제목]\n{title}\n\n[설명]\n{body}\n",
        encoding="utf-8",
    )
    return path
