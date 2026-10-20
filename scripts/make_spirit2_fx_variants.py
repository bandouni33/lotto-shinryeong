"""자동조합 생성 연출 — 신령 이미지는 그대로, 위에 겹치는 투명 빛 효과 5종(애니메이션 WebP, 3초 반복) — 2026-10-20.

v1 후광·빛줄기(인물 뒤) / v2 빛 알갱이 상승 / v3 손 위 구슬 빛 폭발 / v4 테두리 기운 고리 / v5 별똥별(인물 뒤).
안드로이드 앱 WebView 가 소프트웨어 렌더링이라 CSS 겹층 대신 그림 한 장 재생(page_auto.SPIRIT2_GEN_FX_URL).
결과 파일은 홈페이지 저장소 fx/spirit2_fx_v*.webp 에 올린다(바꾸면 page_auto 의 ?v= 올릴 것). pv_* 폴더는 미리보기.
실행: python scripts/make_spirit2_fx_variants.py <출력폴더> [앱 저장소 경로]
"""
from __future__ import annotations
import math, random, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent if len(sys.argv) < 3 else Path(sys.argv[2])
N, OUT, FPS, SEC = 512, 360, 20, 3.0
F = int(FPS * SEC)
HEAD = (0.45 * N, 0.27 * N)
ORB = (0.60 * N, 0.76 * N)
GOLD = np.array([255, 214, 110], np.float32)
WHITE = np.array([255, 250, 225], np.float32)
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)

def person_alpha():
    a = Image.open(ROOT / "로또신령2_인물.webp").convert("RGBA").split()[-1]
    return np.array(a, np.float32) / 255.0
PA = None

def layer(intensity, color=GOLD, core=None):
    """intensity(0~1 배열) → RGBA. core: 중심부를 흰빛으로 섞는 비율 배열."""
    rgb = np.repeat(color[None, None, :], N, 0).repeat(N, 1) if False else np.broadcast_to(color, (N, N, 3)).copy()
    if core is not None:
        rgb = rgb * (1 - core[..., None]) + WHITE * core[..., None]
    a = np.clip(intensity, 0, 1)
    return np.dstack([rgb, a * 255]).astype(np.uint8)

def over(dst, src):
    """RGBA 배열 알파 합성."""
    sa = src[..., 3:4] / 255.0; da = dst[..., 3:4] / 255.0
    oa = sa + da * (1 - sa)
    rgb = (src[..., :3] * sa + dst[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6)
    return np.dstack([rgb, oa * 255]).astype(np.uint8)

def empty():
    return np.zeros((N, N, 4), np.uint8)

def dist(c):
    return np.hypot(xx - c[0], yy - c[1]) / N

def behind(arr):
    arr = arr.astype(np.float32); arr[..., 3] *= (1 - PA); return arr.astype(np.uint8)

# ── 1 후광·빛줄기(인물 뒤) ──
def v1(t):
    d = dist(HEAD); ang = np.degrees(np.arctan2(yy - HEAD[1], xx - HEAD[0]))
    rot = 15 * t / SEC
    ray = (np.cos(np.radians((ang - rot) * 24)) > 0.55).astype(np.float32)
    ray = np.array(Image.fromarray((ray * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)), np.float32) / 255
    pulse = .8 + .2 * math.sin(2 * math.pi * t / 1.5)
    rays = ray * np.interp(d, [0, .05, .25, .5], [0, .85, .4, 0]) * pulse
    hs = .9 + .15 * math.sin(2 * math.pi * t / 1.5)
    halo = np.interp(d, [0, .06 * hs, .16 * hs, .3 * hs], [.95, .85, .4, 0])
    a = np.maximum(rays, halo)
    return behind(layer(a, core=np.interp(d, [0, .08, .2], [1, .6, 0])))

# ── 2 빛 알갱이 상승(앞) ──
rng = random.Random(3)
SP = [(rng.uniform(.06, .94) * N, rng.uniform(4, 8), rng.random(), rng.uniform(-22, 22), rng.choice([1.0, 1.5, 3.0])) for _ in range(40)]
def v2(t):
    im = Image.new("RGBA", (N, N)); d = ImageDraw.Draw(im)
    for x, s, ph, dr, per in SP:
        u = ((t / per) + ph) % 1.0
        y = N * 1.02 - u * N * 0.95; xx_ = x + dr * math.sin(u * math.pi * 2)
        a = min(1, u / .12) * (1 - max(0, (u - .75) / .25)); tw = .6 + .4 * math.sin(t * 14 + x)
        r = s * (.7 + .5 * u)
        d.ellipse((xx_ - r * 2.6, y - r * 2.6, xx_ + r * 2.6, y + r * 2.6), fill=(255, 200, 90, int(120 * a)))
        d.ellipse((xx_ - r, y - r, xx_ + r, y + r), fill=(255, 245, 200, int(255 * a * tw)))
    return np.array(im.filter(ImageFilter.GaussianBlur(1)))

# ── 3 구슬 빛 폭발(앞) ──
def v3(t):
    d = dist(ORB); ang = np.degrees(np.arctan2(yy - ORB[1], xx - ORB[0]))
    u = (t % 1.0)
    core = np.interp(d, [0, .05 + .03 * math.sin(2 * math.pi * t / .5), .16], [1, .8, 0])
    burst_r = .03 + .55 * u
    spikes = (np.cos(np.radians(ang * 16 + 40 * t)) > .7).astype(np.float32)
    burst = spikes * np.clip(1 - np.abs(d - burst_r) / .08, 0, 1) * (1 - u)
    ring = np.clip(1 - np.abs(d - burst_r * .9) / .015, 0, 1) * (1 - u) * .8
    a = np.maximum.reduce([core, burst, ring])
    return layer(a, color=np.array([255, 225, 140], np.float32), core=np.interp(d, [0, .05, .12], [1, .5, 0]))

# ── 4 기운 고리(원 테두리 혜성 + 중심에서 퍼지는 고리) ──
def v4(t):
    c = (N / 2, N / 2); d = dist(c); ang = (np.degrees(np.arctan2(yy - c[1], xx - c[0])) + 360) % 360
    a = np.zeros((N, N), np.float32)
    for k in range(2):
        head = (360 * t / 1.5 + 180 * k) % 360
        behind_deg = (head - ang) % 360
        tail = np.clip(1 - behind_deg / 140, 0, 1) ** 1.5
        band = np.clip(1 - np.abs(d - .465) / .03, 0, 1)
        a = np.maximum(a, tail * band)
    u = (t % 1.0)
    r = .05 + .45 * u
    a = np.maximum(a, np.clip(1 - np.abs(d - r) / .02, 0, 1) * (1 - u) * .7)
    return layer(a, core=(a > .85).astype(np.float32) * .6)

# ── 5 별똥별(하늘, 인물 뒤) ──
rng5 = random.Random(9)
ST = [(rng5.uniform(-.2, .9), rng5.uniform(-.25, .25), rng5.random(), rng5.choice([.75, 1.0, 1.5])) for _ in range(12)]
def v5(t):
    im = Image.new("RGBA", (N, N)); d = ImageDraw.Draw(im)
    for x0, y0, ph, per in ST:
        u = ((t / per) + ph) % 1.0
        hx = (x0 + u * .9) * N; hy = (y0 + u * .7) * N
        L = 120
        for i in range(22):
            f = i / 22
            a = int(255 * (1 - f) * min(1, u / .1) * (1 - max(0, (u - .8) / .2)))
            r = 5.5 * (1 - f) + 1.0
            px, py = hx - L * f * .79, hy - L * f * .61
            d.ellipse((px - r, py - r, px + r, py + r), fill=(255, 235 - int(40 * f), 170 - int(60 * f), a))
    arr = np.array(im.filter(ImageFilter.GaussianBlur(1.3)))
    return behind(arr)

VARIANTS = {"v1": v1, "v2": v2, "v3": v3, "v4": v4, "v5": v5}

def main(outdir: str):
    global PA
    PA = person_alpha()
    base = Image.open(ROOT / "로또신령2.jpg").convert("RGBA")
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    for name, fn in VARIANTS.items():
        frames = []; prev = []
        for f in range(F):
            t = f / FPS
            frames.append(Image.fromarray(fn(t), "RGBA").resize((OUT, OUT), Image.LANCZOS))
        frames[0].save(out / f"spirit2_fx_{name}.webp", save_all=True, append_images=frames[1:], duration=int(1000 / FPS),
                       loop=0, quality=70, method=6, lossless=False, alpha_quality=70)
        # 미리보기(정지 이미지 위 합성)
        pv = out / f"pv_{name}"; pv.mkdir(exist_ok=True)
        b = base.resize((OUT, OUT))
        for i, fr in enumerate(frames):
            Image.alpha_composite(b, fr).convert("RGB").save(pv / f"{i:03d}.png")
        print(name, (out / f"spirit2_fx_{name}.webp").stat().st_size // 1024, "KB")

if __name__ == "__main__":
    main(sys.argv[1])
