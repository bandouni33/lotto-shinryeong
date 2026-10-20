"""자동조합 생성 연출의 '배경 흔들림'(원래 CSS 영역별 흔들림과 같은 값)을 3초 반복 WebP 로 굽는다 — 2026-10-20.

사용자 지시 "배경 움직임은 원래대로 모두 유지": 10-10 사용자 지시 4차의 영역별 흔들림(하늘 고정, 땅·산·누각 살짝,
나무·꽃 바람에 휩쓸리듯)을 그대로 쓰되, 안드로이드 앱 WebView(소프트웨어 렌더링)에서도 보이게 그림 한 장으로 재생한다.
- 값: 옛 page_auto._SPIRIT2_QUAKE_LAYERS(커밋 6cc0db86) 그대로. px 는 화면 표시 크기(약 300px) 기준이라 원본 512px 로 ×1.7.
- 주기: 반복이 끊기지 않게 3초의 약수로 맞춤(1.7~2.1초 → 1.5초, 2.6~3.2초 → 3초).
- 인물은 고정(맨 위). 빛 효과 5종(make_spirit2_fx_variants.py)은 이 위에 따로 겹친다.
결과 → 홈페이지 저장소 fx/spirit2_quake.webp (바꾸면 page_auto 의 ?v= 올릴 것)
실행: python scripts/make_spirit2_quake_anim.py <출력.webp>
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
N, OUT, FPS, SEC = 512, 360, 20, 3.0
SCALE = 512 / 300
# (가림막, [(%, x px, y px, 회전 deg, 기울기 deg)], 원래 주기 s, 회전 중심 %)
LAYERS = (
    ("mtn_left", ((0, 0, 0, 0, 0), (30, -0.8, 0.4, 0, 0), (65, 0.7, -0.4, 0, 0), (100, 0, 0, 0, 0)), 1.9, (15, 40)),
    ("mtn_right", ((0, 0, 0, 0, 0), (35, 0.8, -0.3, 0, 0), (70, -0.7, 0.4, 0, 0), (100, 0, 0, 0, 0)), 2.1, (80, 45)),
    ("cliff_right", ((0, 0, 0, 0, 0), (40, -0.9, 0.3, 0, 0), (75, 0.6, -0.4, 0, 0), (100, 0, 0, 0, 0)), 1.7, (95, 80)),
    ("rail", ((0, 0, 0, 0, 0), (45, 0.6, 0.2, 0, 0), (100, 0, 0, 0, 0)), 1.8, (50, 100)),
    ("trees_left", ((0, 0, 0, 0, 0), (35, 1.5, 0, 0, -2.5), (55, 0.8, 0, 0, -1.2), (80, 1.8, 0, 0, -3), (100, 0, 0, 0, 0)), 3.0, (15, 70)),
    ("trees_right", ((0, 0, 0, 0, 0), (30, 1.2, 0, 0, -2), (60, 0.5, 0, 0, -0.8), (85, 1.5, 0, 0, -2.6), (100, 0, 0, 0, 0)), 3.2, (75, 70)),
    ("flowers_left", ((0, 0, 0, 0, 0), (30, 2.5, -0.5, 1.2, -4), (55, 1, 0, 0.4, -1.5), (80, 3, -0.5, 1.5, -5), (100, 0, 0, 0, 0)), 2.6, (0, 92)),
    ("trees_right_low", ((0, 0, 0, 0, 0), (35, 2, -0.4, 0.8, -3.5), (60, 0.8, 0, 0.3, -1.2), (85, 2.4, -0.4, 1, -4.2), (100, 0, 0, 0, 0)), 2.8, (92, 92)),
    ("building", ((0, 0, 0, 0, 0), (40, 0.9, 0.3, 0.15, 0), (75, -0.7, -0.3, -0.12, 0), (100, 0, 0, 0, 0)), 2.0, (10, 66)),
)


def loop_period(p: float) -> float:
    return 1.5 if p < 2.3 else 3.0


def ease(u: float) -> float:  # CSS ease-in-out 근사
    return u * u * (3 - 2 * u)


def keyval(frames, pct):
    for (p0, *a), (p1, *b) in zip(frames, frames[1:]):
        if p0 <= pct <= p1:
            u = ease((pct - p0) / ((p1 - p0) or 1))
            return [x + (y - x) * u for x, y in zip(a, b)]
    return list(frames[-1][1:])


def transform(img, x, y, rot, skew, origin):
    """CSS transform: translate(x,y) rotate(rot) skewX(skew), 중심 origin — 역변환 행렬로 계산."""
    ox, oy = origin[0] / 100 * N, origin[1] / 100 * N
    r, k = math.radians(rot), math.tan(math.radians(skew))
    c, s = math.cos(r), math.sin(r)
    # 정변환 M = R · K (K: x' = x + k*y), 점 p' = o + T + M (p - o)
    a, b, d, e = c, c * k - s, s, s * k + c
    det = a * e - b * d
    ia, ib, id_, ie = e / det, -b / det, -d / det, a / det
    tx, ty = ox + x, oy + y
    # 입력 p = o + M^-1 (p' - o - T)
    return img.transform(img.size, Image.AFFINE,
                         (ia, ib, ox - ia * tx - ib * ty, id_, ie, oy - id_ * tx - ie * ty),
                         resample=Image.BILINEAR)


def main(out_path: str) -> None:
    plate = Image.open(ROOT / "로또신령2_배경.jpg").convert("RGB")
    person = Image.open(ROOT / "로또신령2_인물.webp").convert("RGBA")
    masks = {n: Image.open(ROOT / "spirit2_layers" / f"{n}.png").split()[-1].resize((N, N), Image.BILINEAR)
             for n, *_ in LAYERS}
    frames = []
    for f in range(int(FPS * SEC)):
        t = f / FPS
        bg = plate.copy()
        for name, kf, period, origin in LAYERS:
            per = loop_period(period)
            x, y, rot, skew = keyval(kf, 100 * ((t % per) / per))
            x, y = x * SCALE, y * SCALE
            bg.paste(transform(plate, x, y, rot, skew, origin), (0, 0), transform(masks[name], x, y, rot, skew, origin))
        fr = bg.convert("RGBA")
        fr.alpha_composite(person)
        frames.append(fr.convert("RGB").resize((OUT, OUT), Image.LANCZOS))
    frames[0].save(out_path, save_all=True, append_images=frames[1:], duration=int(1000 / FPS), loop=0, quality=70, method=6)
    print(out_path, Path(out_path).stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "spirit2_quake.webp")
