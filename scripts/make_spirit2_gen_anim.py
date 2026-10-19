"""조합 생성 3초 연출을 '움직이는 그림 한 장'(애니메이션 WebP)으로 미리 굽는다 — 2026-10-20.

왜: 안드로이드 앱 WebView 는 androidLayerType='software'(깜빡임 대응)라, CSS 로 겹친 층 15개+(가림막·섞기·회전)를
실시간 합성하지 못해 실기기에서 연출이 안 보이거나 깨졌다(사용자 영상 10-20). 그림 한 장 재생은 소프트웨어 렌더링에서도
가볍다. 3초 동안 끊김 없이 반복(loop)되게 모든 주기를 3초의 약수로 맞춘다.

구성(원 기준 좌표, 512px 원본에서 계산 후 축소): 영역별 배경 흔들림(spirit2_layers 가림막) → 머리 뒤 빛줄기 회전·후광 맥박·
기운 고리 → 인물(고정) → 손 위 구슬 빛 → 빛 알갱이. 시작 섬광은 화면 쪽 CSS 한 겹.

실행: python scripts/make_spirit2_gen_anim.py <출력.webp>
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
N = 512
OUT = 360
FPS = 20
SEC = 3.0
FRAMES = int(FPS * SEC)
HEAD = (0.45 * N, 0.27 * N)
ORB = (0.60 * N, 0.76 * N)

# (가림막, [(시점 0~1, dx, dy, 기울기deg)], 주기 s, 회전 중심(비율)) — 주기는 3초의 약수
REGIONS = (
    ("mtn_left", ((0, 0, 0, 0), (.3, -1.6, .8, 0), (.65, 1.4, -.8, 0), (1, 0, 0, 0)), 1.5, (.15, .40)),
    ("mtn_right", ((0, 0, 0, 0), (.35, 1.6, -.6, 0), (.7, -1.4, .8, 0), (1, 0, 0, 0)), 1.5, (.80, .45)),
    ("cliff_right", ((0, 0, 0, 0), (.4, -1.8, .6, 0), (.75, 1.2, -.8, 0), (1, 0, 0, 0)), 1.0, (.95, .80)),
    ("rail", ((0, 0, 0, 0), (.45, 1.2, .4, 0), (1, 0, 0, 0)), 1.0, (.5, 1.0)),
    ("trees_left", ((0, 0, 0, 0), (.35, 3, 0, -4), (.55, 1.6, 0, -2), (.8, 3.6, 0, -5), (1, 0, 0, 0)), 1.5, (.15, .70)),
    ("trees_right", ((0, 0, 0, 0), (.3, 2.4, 0, -3.5), (.6, 1, 0, -1.4), (.85, 3, 0, -4.4), (1, 0, 0, 0)), 1.5, (.75, .70)),
    ("flowers_left", ((0, 0, 0, 0), (.3, 5, -1, -6), (.55, 2, 0, -2.5), (.8, 6, -1, -7.5), (1, 0, 0, 0)), 1.0, (0, .92)),
    ("trees_right_low", ((0, 0, 0, 0), (.35, 4, -.8, -5), (.6, 1.6, 0, -2), (.85, 4.8, -.8, -6), (1, 0, 0, 0)), 1.0, (.92, .92)),
    ("building", ((0, 0, 0, 0), (.4, 1.8, .6, 0), (.75, -1.4, -.6, 0), (1, 0, 0, 0)), 1.5, (.10, .66)),
)


def ease(u: float) -> float:
    return u * u * (3 - 2 * u)


def keyval(frames, p):
    for (p0, *a), (p1, *b) in zip(frames, frames[1:]):
        if p0 <= p <= p1:
            u = ease((p - p0) / (p1 - p0 or 1))
            return [x + (y - x) * u for x, y in zip(a, b)]
    return list(frames[-1][1:])


def affine(img, dx, dy, skew_deg, origin):
    ox, oy = origin[0] * N, origin[1] * N
    k = math.tan(math.radians(skew_deg))
    # 출력 (x,y) ← 입력 (x - dx - k*(y-oy), y - dy)
    return img.transform(img.size, Image.AFFINE, (1, -k, -dx + k * oy, 0, 1, -dy), resample=Image.BILINEAR)


def screen(base: Image.Image, light: Image.Image) -> Image.Image:
    return ImageChops.screen(base, light)


def radial(cx, cy, stops, scale=1.0):
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    d = np.hypot(xx - cx, yy - cy) / (N * scale)
    rgb = np.zeros((N, N, 3), np.float32)
    ds = [s[0] for s in stops]
    for c in range(3):
        rgb[..., c] = np.interp(d, ds, [s[1][c] * s[2] for s in stops])
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))


def rays_base():
    big = 2 * N
    im = Image.new("L", (big, big), 0)
    dr = ImageDraw.Draw(im)
    cx = cy = big / 2
    for i in range(24):
        a0 = math.radians(i * 15)
        a1 = math.radians(i * 15 + 4.5)
        r = big
        dr.polygon([(cx, cy), (cx + r * math.cos(a0), cy + r * math.sin(a0)), (cx + r * math.cos(a1), cy + r * math.sin(a1))], fill=255)
    im = im.filter(ImageFilter.GaussianBlur(3))
    yy, xx = np.mgrid[0:big, 0:big].astype(np.float32)
    d = np.hypot(xx - cx, yy - cy) / N
    fall = np.interp(d, [0, .06, .25, .55], [1, 1, .55, 0])
    return Image.fromarray((np.array(im, np.float32) * fall).astype(np.uint8))


def main(out_path: str) -> None:
    plate = Image.open(ROOT / "로또신령2_배경.jpg").convert("RGB")
    person = Image.open(ROOT / "로또신령2_인물.webp").convert("RGBA")
    masks = {n: Image.open(ROOT / "spirit2_layers" / f"{n}.png").split()[-1].resize((N, N), Image.BILINEAR)
             for n, *_ in REGIONS}
    rays = rays_base()
    rng = random.Random(7)
    sparks = [(rng.uniform(.15, .85) * N, rng.uniform(2.5, 5.0), rng.random(), rng.uniform(-14, 14)) for _ in range(16)]
    frames = []
    for f in range(FRAMES):
        t = f / FPS
        bg = plate.copy()
        for name, kf, period, origin in REGIONS:
            dx, dy, sk = keyval(kf, (t % period) / period)
            moved = affine(plate, dx, dy, sk, origin)
            m = affine(masks[name], dx, dy, sk, origin)
            bg.paste(moved, (0, 0), m)
        # 빛줄기: 3초에 15도(빛살 간격) 회전 → 끊김 없는 반복, 세기는 1.5초 맥박
        ang = 15 * (t / SEC)
        big = rays.rotate(-ang, resample=Image.BILINEAR)
        sx, sy = int(N - HEAD[0]), int(N - HEAD[1])
        rmask = big.crop((sx, sy, sx + N, sy + N))
        pulse = .75 + .25 * math.sin(2 * math.pi * t / 1.5)
        ray_rgb = Image.merge("RGB", [rmask.point(lambda v, c=c: int(v * c * pulse)) for c in (1.0, .92, .62)])
        bg = screen(bg, ray_rgb)
        # 후광 맥박(1.5초)
        hs = .85 + .2 * math.sin(2 * math.pi * t / 1.5)
        halo = radial(*HEAD, [(0, (255, 250, 220), 1), (.07 * hs, (255, 225, 140), .95), (.17 * hs, (255, 180, 70), .55),
                              (.32 * hs, (255, 150, 50), 0), (2, (0, 0, 0), 0)])
        bg = screen(bg, halo)
        # 기운 고리(1초마다 퍼짐)
        u = (t % 1.0) / 1.0
        r0 = .04 + .5 * u
        ring = radial(*HEAD, [(0, (0, 0, 0), 0), (max(r0 - .03, 0), (0, 0, 0), 0), (r0, (255, 230, 150), 1 - u),
                              (r0 + .025, (255, 200, 90), (1 - u) * .4), (r0 + .06, (0, 0, 0), 0), (2, (0, 0, 0), 0)])
        bg = screen(bg, ring)
        frame = bg.convert("RGBA")
        frame.alpha_composite(person)
        frame = frame.convert("RGB")
        # 손 위 구슬 빛(0.75초)
        os_ = .8 + .3 * (0.5 + 0.5 * math.sin(2 * math.pi * t / .75))
        orb = radial(*ORB, [(0, (255, 255, 235), .95), (.05 * os_, (255, 220, 120), .75), (.11 * os_, (120, 200, 255), .3),
                            (.2 * os_, (0, 0, 0), 0), (2, (0, 0, 0), 0)])
        frame = screen(frame, orb)
        # 빛 알갱이(1.5초 주기, 아래→위)
        sp = Image.new("RGB", (N, N), 0)
        d = ImageDraw.Draw(sp)
        for x, size, ph, drift in sparks:
            u = ((t / 1.5) + ph) % 1.0
            y = N * .96 - u * N * .62
            xx = x + drift * u
            a = min(1.0, u / .15) * (1 - max(0.0, (u - .7) / .3))
            s = size * (.6 + .6 * u)
            c = (int(255 * a), int(235 * a), int(150 * a))
            d.ellipse((xx - s * 2.2, y - s * 2.2, xx + s * 2.2, y + s * 2.2), fill=(int(c[0] * .35), int(c[1] * .3), int(c[2] * .2)))
            d.ellipse((xx - s, y - s, xx + s, y + s), fill=c)
        frame = screen(frame, sp.filter(ImageFilter.GaussianBlur(1.2)))
        frames.append(frame.resize((OUT, OUT), Image.LANCZOS))
    frames[0].save(out_path, save_all=True, append_images=frames[1:], duration=int(1000 / FPS), loop=0,
                   quality=66, method=6)
    print(out_path, Path(out_path).stat().st_size // 1024, "KB", FRAMES, "frames")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "spirit2_gen.webp")
