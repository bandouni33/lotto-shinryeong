# -*- coding: utf-8 -*-
"""목요일 게시물 5장 — 2026-10-24 사용자 컨셉("5페이지로 문구만 바꿔가며 매주 진행").

각 장 = 위쪽 문구(감성·질문형) + 아래 앱 실제 화면(2026-10-23 실기기 녹화에서 자른 weekly_content/screens/*.jpg).
  1P 타로      — "지금 마음이 ○○하신가요? 타로 한 장으로 마음을 달래보세요."(○○ = 매주 바뀜)
  2P 자동조합  — 무작위 구매 → 4차 필터링을 거친 한정 수량
  3P 번개조합  — 좋은 꿈·가족 생일로 행운 잇기
  4P 번호 검증 — 5등도 잘 안 맞으면 반대 조합으로 헷지
  5P 고급필터  — 1차 → 엑셀 2차 → 원하는 수량 3차(역대 유력 패턴 상위 우선)
문구는 회차로 정해지는 변형(VARIANTS) 중 하나 — 같은 회차는 항상 같은 문구(재실행해도 동일).
영상은 장이 바뀔 때마다 배경음악도 바뀐다(run_weekly.make_shorts(medley=True)).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from weekly_content import cards
from weekly_content.cards import GOLD, H, W, WHITE, _canvas, _center, font

SCREENS = Path(__file__).resolve().parent / "screens"
LABEL = "로또신령"
TOTAL = 5

# 1P 감정 단어(매주 바뀜 — 사용자 예시: 불편·복잡·힘듦·혼란·지침·우울)
MOODS = ["불편하신가요", "복잡하신가요", "힘드신가요", "혼란스러우신가요", "지치셨나요", "우울하신가요", "무거우신가요"]

PAGES = [
    {"screens": ["tarot", "tarot_4", "tarot_2", "tarot_5", "tarot_3", "tarot_6"],
     "variants": [([f"지금 마음이 {m}?"], ["타로 한 장으로", "마음을 달래보세요."]) for m in MOODS]},
    {"screens": ["auto", "auto_3", "auto_2", "auto_4"],
     "variants": [
         (["아무 근거 없이", "무작위로 구매하고 계시나요?"],
          ["이제 로또신령에서 4차 필터링까지 거친", "한정 수량으로 새로운 꿈에 도전해 보세요."]),
         (["매주 감으로만", "번호를 고르고 계시나요?"],
          ["이제 로또신령에서 4차 필터링까지 거친", "한정 수량으로 새로운 꿈에 도전해 보세요."]),
         (["자동 번호, 운에만", "맡기고 계시나요?"],
          ["이제 로또신령에서 4차 필터링까지 거친", "한정 수량으로 새로운 꿈에 도전해 보세요."]),
     ]},
    {"screens": ["thunder", "thunder_3", "thunder_2", "thunder_4", "thunder_5", "thunder_6"],
     "variants": [
         (["이번 주 좋은 꿈 꾸셨나요?"], ["가족 생일을 넣어서", "행운을 이어가 보세요."]),
         (["이번 주 특별한 날이 있으신가요?"], ["기념일 숫자를 넣어서", "나만의 행운을 만들어 보세요."]),
         (["꼭 넣고 싶은 숫자가 있으신가요?"], ["고정수로 넣고", "번개처럼 여러 게임을 뽑아 보세요."]),
     ]},
    {"screens": ["hedge", "hedge_3", "hedge_2", "hedge_4"],
     "variants": [
         (["이번 주 복권 구매하셨나요?"], ["5등도 잘 안 맞는다면", "반대 조합으로 헷지를 해 보세요."]),
         (["산 번호, 매번 아쉬우셨나요?"], ["QR 한 번이면", "반대 조건 조합까지 바로 만들어요."]),
     ]},
    {"screens": ["adv", "adv_2", "adv_5", "adv_3", "adv_6", "adv_4"],
     "variants": [
         (["수동으로 구매하고 계신가요?"],
          ["경우의 수를 좁혀가는 1차 필터링,", "나만의 스킬이 있다면 엑셀 업로드로 2차 필터링,",
           "그래도 많으면 원하는 수량으로 3차 필터링까지.", "역대 유력 패턴 상위 순서로 필요한 수량만 가져가세요."]),
     ]},
]


FIRST_ROUND = 1247   # 첫 게시 회차 — 이 회차는 각 장의 첫 문구(사용자 원문), 이후 매주 다음 변형으로


def page_text(page: int, rnd: int) -> tuple[list[str], list[str]]:
    vs = PAGES[page]["variants"]
    return vs[(rnd - FIRST_ROUND) % len(vs)]


def screen_for(page: int, rnd: int) -> str:
    """2026-10-24 사용자 지시 '기능 창도 다양화해서 매주 다른 화면': 기능마다 화면 여러 장을 매주 돌려 쓴다.
    화면 출처: 10-23 실기기 녹화 + 10-24 사용자 기능별 홍보 영상 5편(타로·자동조합·번개조합·번호검증·고급필터)."""
    sc = PAGES[page]["screens"]
    return sc[(rnd - FIRST_ROUND) % len(sc)]


def _rounded(im: Image.Image, r: int) -> Image.Image:
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, im.width - 1, im.height - 1], r, fill=255)
    out = Image.new("RGBA", im.size)
    out.paste(im, (0, 0), m)
    return out


def card(page: int, rnd: int) -> Image.Image:
    head, body = page_text(page, rnd)
    im = _canvas()
    d = ImageDraw.Draw(im)
    y = 110
    for ln in head:
        _center(d, y, ln, font(60, "Black"), GOLD)
        y += 80
    y += 16
    bf = font(35 if len(body) > 3 else 40, "Medium")
    for ln in body:
        _center(d, y, ln, bf, WHITE)
        y += 54 if len(body) > 3 else 60
    top = y + 34
    bottom = cards.FOOT_Y - 36
    # 앱 화면: 남은 높이에 맞춰 폭 900 안에서 위쪽부터 보이게
    shot = Image.open(SCREENS / f"{screen_for(page, rnd)}.jpg").convert("RGB")
    w = 900
    shot = shot.resize((w, int(shot.height * w / shot.width)))
    h = min(shot.height, bottom - top)
    shot = shot.crop((0, 0, w, h))
    x = (W - w) // 2
    shadow = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([30, 30, w + 30, h + 30], 28, fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))
    im.paste(shadow, (x - 30, top - 22), shadow)
    rs = _rounded(shot, 28)
    im.paste(rs, (x, top), rs)
    ImageDraw.Draw(im).rounded_rectangle([x, top, x + w - 1, top + h - 1], 28, outline=(233, 196, 106), width=3)
    cards._footer(im, page + 1, TOTAL, LABEL)
    return im


def build(rnd: int) -> list[Image.Image]:
    return [card(i, rnd) for i in range(TOTAL)]


# ── 영상 연출(2026-10-24 사용자 수정 제안) ──
# "기능별 기본 유지(매주 변경사항: 감성 부분·음악·페이지 변경 스킬)" → 장 구성은 그대로, 매주 회차로
#   ① 장 넘김 효과 ② 장별 음악 장르 ③ 줌 방향 이 돌아가며 바뀐다(같은 회차 = 항상 같은 연출).
# "글자 수에 맞게 속도 늘려도 될 듯(1분)" → 장 시간은 글자 수에 비례, 전체 약 60초.
VIDEO_SEC = 60.0
XF = 1.2
# PPT 느낌 넘김 효과(ffmpeg xfade) — 매주 이 중 4개(서로 다름)
TRANSITIONS = ["circleopen",   # 중앙에서 둥글게 열리며 등장
               "fadewhite",    # 빛이 번쩍하며 넘어감(+'반짝' 소리)
               "smoothup",     # 아래에서 떠오름
               "zoomin",       # 확 다가오며 전환
               "radial",       # 시계 방향으로 쓸어 넘김
               "horzopen",     # 가운데에서 위아래로 펼쳐짐
               "coverup",      # 다음 장이 아래에서 날아 들어와 덮음
               "dissolve"]     # 반짝이는 입자로 스며듦
LIGHT = {"fadewhite"}
# 이웃한 장끼리 장조↔단조·느림↔빠름이 엇갈리는 순서(bgm.STYLES). 매주 시작점만 돈다.
MUSIC_ORDER = ["dreamy", "bright", "chill", "epic", "funky"]
MOTIONS = ["in", "in_top", "out"]   # 장마다 살짝 줌인 / 글자 쪽으로 줌인 / 살짝 줌아웃


def video_plan(rnd: int) -> dict:
    w = (rnd - FIRST_ROUND) % 1000
    chars = [len("".join(h + b)) for h, b in (page_text(i, rnd) for i in range(TOTAL))]
    raw = [6 + 0.11 * c for c in chars]
    scale = (VIDEO_SEC + XF * (TOTAL - 1)) / sum(raw)
    secs = [round(r * scale, 2) for r in raw]
    trans = [TRANSITIONS[(w * 3 + i) % len(TRANSITIONS)] for i in range(TOTAL - 1)]
    styles = [MUSIC_ORDER[(w + i) % len(MUSIC_ORDER)] for i in range(TOTAL)]
    motions = [MOTIONS[(w + i) % len(MOTIONS)] for i in range(TOTAL)]
    return {"secs": secs, "xf": XF, "trans": trans, "styles": styles, "motions": motions, "light": sorted(LIGHT)}
