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
    {"screen": "tarot",
     "variants": [([f"지금 마음이 {m}?"], ["타로 한 장으로", "마음을 달래보세요."]) for m in MOODS]},
    {"screen": "auto",
     "variants": [
         (["아무 근거 없이", "무작위로 구매하고 계시나요?"],
          ["이제 로또신령에서 4차 필터링까지 거친", "한정 수량으로 새로운 꿈에 도전해 보세요."]),
         (["매주 감으로만", "번호를 고르고 계시나요?"],
          ["이제 로또신령에서 4차 필터링까지 거친", "한정 수량으로 새로운 꿈에 도전해 보세요."]),
         (["자동 번호, 운에만", "맡기고 계시나요?"],
          ["이제 로또신령에서 4차 필터링까지 거친", "한정 수량으로 새로운 꿈에 도전해 보세요."]),
     ]},
    {"screen": "thunder",
     "variants": [
         (["이번 주 좋은 꿈 꾸셨나요?"], ["가족 생일을 넣어서", "행운을 이어가 보세요."]),
         (["이번 주 특별한 날이 있으신가요?"], ["기념일 숫자를 넣어서", "나만의 행운을 만들어 보세요."]),
         (["꼭 넣고 싶은 숫자가 있으신가요?"], ["고정수로 넣고", "번개처럼 여러 게임을 뽑아 보세요."]),
     ]},
    {"screen": "hedge",
     "variants": [
         (["이번 주 복권 구매하셨나요?"], ["5등도 잘 안 맞는다면", "반대 조합으로 헷지를 해 보세요."]),
         (["산 번호, 매번 아쉬우셨나요?"], ["QR 한 번이면", "반대 조건 조합까지 바로 만들어요."]),
     ]},
    {"screen": "adv",
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
    shot = Image.open(SCREENS / f"{PAGES[page]['screen']}.jpg").convert("RGB")
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
