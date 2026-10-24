# -*- coding: utf-8 -*-
"""회차 부적 — 당첨번호로만 정해지는 한 장뿐인 부적 그림(2026-10-18 사용자 승인: 채널별 특색).

  · 45개 자리를 원으로 두고, 그 회차 당첨번호 6개를 붓선으로 잇는다 → 회차마다 모양이 다르다(같은 번호면 같은 그림)
  · 보너스는 점선, 가운데 '이번 주 주인공'(number_story.headline), 아래 붉은 도장 = 회차
  · 인스타 캐러셀 첫 장·짧은 영상 첫 장·홈페이지 회차 페이지에 같은 그림을 쓴다
실행(확인용): python -m weekly_content.talisman 1246 out.png
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from weekly_content import cards  # noqa: E402

W, H = 1080, 1350
PAPER = (236, 206, 120)
INK = (176, 30, 24)
DARK = (58, 36, 14)


def _serif(size: int) -> ImageFont.FreeTypeFont:
    for p in sorted(Path("/usr/share/fonts").rglob("NotoSerifCJK-Bold.ttc")):
        return ImageFont.truetype(str(p), size, index=1)
    return cards.font(size, "Bold")


def _paper(rng: random.Random) -> Image.Image:
    im = Image.new("RGB", (W, H), PAPER)
    noise = Image.effect_noise((W // 4, H // 4), 28).resize((W, H)).filter(ImageFilter.GaussianBlur(3))
    im = Image.blend(im, Image.merge("RGB", (noise, noise, noise)), 0.10)
    d = ImageDraw.Draw(im)
    for _ in range(26):   # 종이 결
        y = rng.randint(0, H)
        d.line([(0, y), (W, y + rng.randint(-30, 30))], fill=(225, 192, 104), width=rng.randint(1, 3))
    return im


def _brush(d: ImageDraw.ImageDraw, pts, rng: random.Random, width: int, fill=INK):
    """붓선 — 같은 선을 조금씩 흔들어 여러 번 그어 먹 번짐처럼."""
    for k in range(5):
        jit = [(x + rng.uniform(-3, 3), y + rng.uniform(-3, 3)) for x, y in pts]
        d.line(jit, fill=fill, width=max(2, width - k * 2), joint="curve")


def build(rnd: int, nums: list[int], bonus: int, *, star_line: str = "", date_text: str = "") -> Image.Image:
    rng = random.Random(f"lotto-shinryeong-talisman-{rnd}-{sorted(nums)}-{bonus}")
    im = _paper(rng)
    d = ImageDraw.Draw(im)
    # 테두리(이중 붉은 선)
    d.rectangle([40, 40, W - 40, H - 40], outline=INK, width=8)
    d.rectangle([62, 62, W - 62, H - 62], outline=INK, width=3)
    # 머리글
    f_head = _serif(64)
    d.text((110, 150), "로또신령 符", font=f_head, fill=INK, anchor="lm")
    d.text((112, 228), f"제{rnd}회" + (f" · {date_text}" if date_text else ""), font=_serif(34), fill=DARK, anchor="lm")
    # 45자리 원
    cx, cy, R = W // 2, 610, 285
    pos = {n: (cx + R * math.sin(2 * math.pi * (n - 1) / 45), cy - R * math.cos(2 * math.pi * (n - 1) / 45))
           for n in range(1, 46)}
    for n, (x, y) in pos.items():
        d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=DARK)
    d.ellipse([cx - R - 22, cy - R - 22, cx + R + 22, cy + R + 22], outline=INK, width=4)
    # 당첨번호 붓선: 6개 모두를 서로 잇는 가는 선(별 무늬) + 바깥 굵은 선(작은 수 → 큰 수 → 처음으로)
    s = sorted(nums)
    for i, a in enumerate(s):
        for b in s[i + 1:]:
            _brush(d, [pos[a], pos[b]], rng, 5, fill=(196, 70, 52))
    path = [pos[n] for n in s] + [pos[s[0]]]
    _brush(d, path, rng, 16)
    # 보너스 점선
    bx, by = pos[bonus]
    nx, ny = pos[s[-1]]
    for t in range(0, 20, 2):
        a, b = t / 20, (t + 1) / 20
        d.line([(nx + (bx - nx) * a, ny + (by - ny) * a), (nx + (bx - nx) * b, ny + (by - ny) * b)], fill=DARK, width=5)
    # 번호 글자(원 바깥)
    f_n = _serif(40)
    prev, lift = None, 0
    for n in sorted(s + [bonus]):
        x, y = pos[n]
        lift = (lift + 1) % 2 if prev is not None and n - prev <= 2 else 0   # 붙은 번호는 안·밖으로 번갈아
        prev = n
        rr = R + 58 + 46 * lift
        ox, oy = cx + rr * (x - cx) / R, cy + rr * (y - cy) / R
        d.ellipse([x - 13, y - 13, x + 13, y + 13], fill=INK if n != bonus else DARK)
        d.text((ox, oy), str(n), font=f_n, fill=INK if n != bonus else DARK, anchor="mm")
    # 가운데 印
    d.text((cx, cy), "印", font=_serif(110), fill=(176, 30, 24), anchor="mm")
    # 주인공 한 줄
    if star_line:
        d.text((W // 2, 1110), star_line, font=_serif(42), fill=DARK, anchor="mm")
    d.text((W // 2, 1172), f"{' '.join(map(str, s))}  +  {bonus}", font=_serif(38), fill=DARK, anchor="mm")
    # 도장(회차)
    seal = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    sd = ImageDraw.Draw(seal)
    sd.rounded_rectangle([8, 8, 192, 192], 18, outline=INK + (235,), width=10)
    sd.text((100, 72), "神靈", font=_serif(52), fill=INK + (235,), anchor="mm")
    sd.text((100, 138), str(rnd), font=_serif(50), fill=INK + (235,), anchor="mm")
    seal = seal.rotate(rng.uniform(-9, 9), expand=True, resample=Image.BICUBIC)
    im.paste(seal, (W - 300, 82), seal)
    return im


if __name__ == "__main__":
    rnd = int(sys.argv[1])
    import json

    data = json.loads((ROOT / "site_data" / "data.json").read_text(encoding="utf-8"))
    row = next(r for r in data["draws"] if r[0] == rnd)
    build(rnd, row[2:8], row[8], star_line=data["headline"]["title"] if data["headline"]["round"] == rnd else "",
          date_text=row[1].replace("-", ".")).save(sys.argv[2])
