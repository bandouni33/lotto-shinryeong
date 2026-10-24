# -*- coding: utf-8 -*-
"""SNS 짧은 영상용 배경음악 — 코드로 직접 만드는 곡(저작권 문제 없음, 2026-10-24 사용자 지시 '음악 삽입 필수').
2026-10-24 추가 지시 '게시 때마다 바꿔서, 조금 빠르고 비트 있게': seed(게시물마다 다른 값)로 코드 진행·조성·빠르기
(120~132 BPM)·아르페지오 모양이 바뀌고, 리듬은 매 박 킥 + 2·4박 스네어 + 16분 하이햇으로 비트를 세웠다.
신스 패드 + 아르페지오, 시작 1초 페이드인·끝 2.5초 페이드아웃."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
# 코드 진행 후보(근음 기준 3화음, MIDI) — seed 로 하나 고르고 조성을 -3~+4 반음 옮긴다
PROGRESSIONS = [
    [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)],   # Am F C G
    [(48, 52, 55), (55, 59, 62), (57, 60, 64), (53, 57, 60)],   # C G Am F
    [(50, 53, 57), (58, 62, 65), (53, 57, 60), (48, 52, 55)],   # Dm Bb F C
    [(52, 55, 59), (48, 52, 55), (55, 59, 62), (50, 54, 57)],   # Em C G D
    [(57, 60, 64), (55, 59, 62), (53, 57, 60), (52, 56, 59)],   # Am G F E
]
ARP_SHAPES = [(0, 1, 2, 1), (0, 2, 1, 2), (2, 1, 0, 1), (0, 1, 2, 2)]


def write_wav(out: Path, dur: float, seed: int | str | None = None) -> Path:
    return _save(out, render(dur, seed if seed is not None else str(out)))


def whoosh(dur: float = 0.7):
    """'슥' 하고 넘어가는 소리 — 잡음을 저음→고음으로 쓸어 올리고 가운데서 가장 크게(2026-10-24 목요일 PPT 느낌)."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.default_rng(11).standard_normal(n)
    out = np.zeros(n)
    win = 256
    for s0 in range(0, n, win):   # 구간마다 1차 저역 통과 계수를 바꿔 '쉬익' 스윕
        k = min(0.95, 0.15 + 0.8 * s0 / n)
        y = out[s0 - 1] if s0 else 0.0
        for j in range(s0, min(n, s0 + win)):
            y = y + k * (noise[j] - y)
            out[j] = y
    env = np.sin(np.pi * t / dur) ** 2
    sig = out * env
    sig /= max(1e-9, float(np.abs(sig).max()))
    return np.stack([sig * 0.9, sig], axis=1) * 0.55


def write_medley(out: Path, durs: list[float], seed: str, xf: float = 0.6, whoosh_at: list[float] | None = None,
                 styles: list[str] | None = None, sparkle_at: list[float] | None = None) -> Path:
    """장(페이지)이 바뀔 때마다 다른 곡 — 2026-10-24 사용자 지시(목요일 게시물). 곡 사이는 xf 초 겹쳐 자연스럽게.
    whoosh_at(초) 이 있으면 그 순간마다 '슥' 소리를, sparkle_at 이면 '반짝' 소리를 얹는다.
    styles(장마다 STYLES 이름) 가 있으면 장마다 다른 장르의 곡(이웃한 장끼리 대비)."""
    n_xf = int(xf * SR)
    parts = [render_style(d + xf, f"{seed}:{i}", styles[i]) if styles else render(d + xf, f"{seed}:{i}")
             for i, d in enumerate(durs)]
    out_arr = parts[0]
    for p in parts[1:]:
        ramp = np.linspace(0, 1, n_xf)[:, None]
        mixed = out_arr[-n_xf:] * (1 - ramp) + p[:n_xf] * ramp
        out_arr = np.concatenate([out_arr[:-n_xf], mixed, p[n_xf:]])
    if whoosh_at:
        out_arr = out_arr / (max(1e-9, float(np.abs(out_arr).max())) / 0.75)
        w = whoosh()
        for t0 in whoosh_at:
            s0 = max(0, int((t0 - 0.15) * SR))
            e0 = min(len(out_arr), s0 + len(w))
            out_arr[s0:e0] += w[: e0 - s0]
    for t0 in sparkle_at or []:
        sp = sparkle()
        s0 = max(0, int(t0 * SR))
        e0 = min(len(out_arr), s0 + len(sp))
        out_arr[s0:e0] += sp[: e0 - s0]
    return _save(out, out_arr)


def _save(out: Path, mix) -> Path:
    mix = mix / (max(1e-9, float(np.abs(mix).max())) / 0.8)
    pcm = (mix * 32767).astype(np.int16)
    out = Path(out)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return out


def render(dur: float, seed: int | str):
    import zlib

    key = zlib.crc32(str(seed).encode("utf-8"))
    pick = np.random.default_rng(key)
    bpm = int(pick.integers(120, 133))
    shift = int(pick.integers(-3, 5))
    chords = [tuple(m + shift for m in c) for c in PROGRESSIONS[int(pick.integers(len(PROGRESSIONS)))]]
    shape = ARP_SHAPES[int(pick.integers(len(ARP_SHAPES)))]
    beat = 60 / bpm
    n = int(SR * dur)
    mix = np.zeros((n, 2))

    def note(f):
        return 440.0 * 2 ** ((f - 69) / 12)

    bar = 4 * beat

    def env(length, a=0.01, r=0.3):
        k = np.arange(length) / SR
        return np.minimum(1, k / a) * np.exp(-k / r)

    for b in range(int(dur / bar) + 1):
        ch = chords[b % 4]
        s0 = int(b * bar * SR)
        L = min(int(bar * SR * 1.1), n - s0)
        if L <= 0:
            break
        k = np.arange(L) / SR
        sig = np.zeros(L)
        for m in ch:
            f = note(m)
            sig += 0.5 * np.sin(2 * np.pi * f * k) + 0.15 * np.sin(2 * np.pi * 2 * f * k + 0.3)
        sig *= np.minimum(1, k / 0.4) * np.minimum(1, (L / SR - k) / 0.4) * 0.09
        mix[s0:s0 + L, 0] += sig
        mix[s0:s0 + L, 1] += sig * 0.92

    step = beat / 2
    for i in range(int(dur / step)):
        ch = chords[int(i * step / bar) % 4]
        f = note(ch[shape[i % 4]] + (24 if i % 8 == 7 else 12))
        s0 = int(i * step * SR)
        L = min(int(0.45 * SR), n - s0)
        if L <= 0:
            break
        k = np.arange(L) / SR
        sig = (np.sin(2 * np.pi * f * k) + 0.3 * np.sin(2 * np.pi * 2 * f * k)) * env(L, 0.005, 0.18) * 0.07
        pan = 0.5 + 0.3 * np.sin(i * 0.7)
        mix[s0:s0 + L, 0] += sig * (1 - pan) * 2
        mix[s0:s0 + L, 1] += sig * pan * 2

    # 리듬(1마디 뒤부터): 매 박 킥, 2·4박 스네어, 16분 하이햇(강약), 베이스(근음 8분)
    rng = np.random.default_rng(key)
    for i in range(int(dur / beat)):
        tt = i * beat
        if tt < bar:
            continue
        s0 = int(tt * SR)
        L = min(int(0.3 * SR), n - s0)
        if L > 0:   # 킥
            k = np.arange(L) / SR
            f = 120 * np.exp(-k * 20) + 48
            mix[s0:s0 + L] += (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-k * 11) * 0.42)[:, None]
        if i % 2 == 1:   # 스네어
            L = min(int(0.18 * SR), n - s0)
            if L > 0:
                k = np.arange(L) / SR
                sn = (rng.standard_normal(L) * 0.6 + np.sin(2 * np.pi * 190 * k)) * np.exp(-k * 22) * 0.16
                mix[s0:s0 + L] += sn[:, None]
        for q in range(4):   # 16분 하이햇
            s1 = int((tt + q * beat / 4) * SR)
            L = min(int(0.04 * SR), n - s1)
            if L > 0:
                amp = 0.035 if q % 2 == 0 else 0.018
                mix[s1:s1 + L] += (rng.standard_normal(L) * np.exp(-np.arange(L) / SR * 110) * amp)[:, None]
        ch = chords[int(tt / bar) % 4]
        for h in (0, 0.5):   # 베이스
            s1 = int((tt + h * beat) * SR)
            L = min(int(beat / 2 * SR), n - s1)
            if L > 0:
                k = np.arange(L) / SR
                bs = np.sin(2 * np.pi * note(ch[0] - 12) * k) * np.minimum(1, k / 0.005) * np.exp(-k * 6) * 0.22
                mix[s1:s1 + L] += bs[:, None]

    fade = np.ones(n)
    fi, fo = min(SR, n), min(int(2.5 * SR), n)
    fade[:fi] = np.linspace(0, 1, fi)
    fade[-fo:] = np.minimum(fade[-fo:], np.linspace(1, 0, fo))
    mix *= fade[:, None]
    return mix


# ── 2026-10-24 목요일 '페이지마다 반전 느낌 나게 다른 음악(살짝 비트 있게)' — 장르(스타일)별 곡 ──
# 이웃한 장끼리 장조↔단조·느림↔빠름이 엇갈리게 배치(thursday.music_styles). 같은 seed = 같은 곡.
MAJOR = [PROGRESSIONS[1], [(53, 57, 60), (48, 52, 55), (55, 59, 62), (57, 60, 64)],   # C G Am F / F C G Am
         [(48, 52, 55), (57, 60, 64), (53, 57, 60), (55, 59, 62)]]                     # C Am F G
MINOR = [PROGRESSIONS[0], PROGRESSIONS[2], PROGRESSIONS[4]]                           # Am F C G / Dm Bb F C / Am G F E
STYLES = {
    # 몽환(단조·느림): 반박자 스네어, 종소리 아르페지오, 패드 크게
    "dreamy": dict(prog=MINOR, bpm=(94, 102), kick=(0, 2.5), snare=(2,), hat=8, swing=0.0, bass="long",
                   arp=("bell", 8), pad=0.13),
    # 밝음(장조·빠름): 매 박 킥, 2·4 스네어, 16분 하이햇, 사각파 아르페지오
    "bright": dict(prog=MAJOR, bpm=(126, 134), kick=(0, 1, 2, 3), snare=(1, 3), hat=16, swing=0.0, bass="eighth",
                   arp=("square", 8), pad=0.08),
    # 칠(장조·느림): 힙합 킥, 스윙 하이햇, 일렉 피아노
    "chill": dict(prog=MAJOR, bpm=(98, 106), kick=(0, 1.5, 2.75), snare=(1, 3), hat=8, swing=0.18, bass="kick",
                  arp=("epiano", 4), pad=0.10),
    # 웅장(단조·빠름): 네 박 킥 + 박수, 오프비트 하이햇, 옥타브 베이스, 16분 톱니 아르페지오
    "epic": dict(prog=MINOR, bpm=(130, 138), kick=(0, 1, 2, 3), snare=(1, 3), hat=-1, swing=0.0, bass="octave",
                 arp=("saw", 16), pad=0.10),
    # 펑키(장조·중간): 싱코페이션 킥·베이스, 16분 하이햇, 짧게 튕기는 소리
    "funky": dict(prog=MAJOR, bpm=(112, 120), kick=(0, 0.75, 2, 2.5), snare=(1, 3), hat=16, swing=0.0,
                  bass="synco", arp=("pluck", 8), pad=0.07),
}


def _tone(kind: str, f: float, k):
    w = 2 * np.pi * f * k
    if kind == "bell":
        return (np.sin(w) + 0.4 * np.sin(2.76 * w) * np.exp(-k * 6)) * np.exp(-k * 3.5)
    if kind == "square":
        return (np.sin(w) + np.sin(3 * w) / 3 + np.sin(5 * w) / 5) * np.exp(-k * 7)
    if kind == "epiano":
        return (np.sin(w) + 0.5 * np.sin(w * 1.003) + 0.25 * np.sin(2 * w)) * np.exp(-k * 2.5)
    if kind == "saw":
        return sum(np.sin(h * w) / h for h in range(1, 7)) * np.exp(-k * 10)
    return (np.sin(w) + 0.5 * np.sin(2 * w)) * np.exp(-k * 14)   # pluck


def render_style(dur: float, seed: int | str, style: str):
    import zlib

    st = STYLES[style]
    key = zlib.crc32(f"{style}:{seed}".encode("utf-8"))
    pick = np.random.default_rng(key)
    bpm = int(pick.integers(st["bpm"][0], st["bpm"][1] + 1))
    shift = int(pick.integers(-3, 5))
    chords = [tuple(m + shift for m in c) for c in st["prog"][int(pick.integers(len(st["prog"])))]]
    shape = ARP_SHAPES[int(pick.integers(len(ARP_SHAPES)))]
    beat = 60 / bpm
    bar = 4 * beat
    n = int(SR * dur)
    mix = np.zeros((n, 2))
    rng = np.random.default_rng(key)

    def note(m):
        return 440.0 * 2 ** ((m - 69) / 12)

    def add(t0, sig, pan=0.5):
        s0 = int(t0 * SR)
        if s0 >= n:
            return
        sig = sig[: n - s0]
        mix[s0:s0 + len(sig), 0] += sig * (1 - pan) * 2
        mix[s0:s0 + len(sig), 1] += sig * pan * 2

    def ks(sec):
        return np.arange(int(sec * SR)) / SR

    nbar = int(dur / bar) + 1
    for b in range(nbar):   # 패드
        ch = chords[b % 4]
        k = ks(bar * 1.1)
        sig = sum(0.5 * np.sin(2 * np.pi * note(m) * k) + 0.12 * np.sin(2 * np.pi * 2 * note(m) * k + 0.3) for m in ch)
        sig = sig * np.minimum(1, k / 0.4) * np.minimum(1, (k[-1] - k) / 0.4 + 1e-3) * st["pad"]
        add(b * bar, sig)
    tone, per_bar = st["arp"]   # 아르페지오
    step = bar / per_bar
    for i in range(int(dur / step)):
        ch = chords[int(i * step / bar) % 4]
        k = ks(min(0.6, step * 2.2))
        f = note(ch[shape[i % 4]] + (24 if i % 8 == 7 else 12))
        add(i * step, _tone(tone, f, k) * np.minimum(1, k / 0.004) * 0.06, 0.5 + 0.3 * np.sin(i * 0.7))
    for b in range(nbar):   # 리듬(첫 마디는 쉬고 들어감)
        if b == 0:
            continue
        t_bar = b * bar
        ch = chords[b % 4]
        for kb in st["kick"]:
            k = ks(0.3)
            f = 120 * np.exp(-k * 20) + 48
            add(t_bar + kb * beat, np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-k * 11) * 0.42)
        for sb in st["snare"]:
            k = ks(0.18)
            sn = (rng.standard_normal(len(k)) * 0.7 + 0.6 * np.sin(2 * np.pi * 190 * k)) * np.exp(-k * 22) * 0.16
            add(t_bar + sb * beat, sn)
        if st["hat"] == -1:   # 오프비트 오픈 하이햇
            for q in range(4):
                k = ks(0.12)
                add(t_bar + (q + 0.5) * beat, rng.standard_normal(len(k)) * np.exp(-k * 30) * 0.05)
        else:
            per = st["hat"] // 4
            for q in range(4 * per):
                tq = t_bar + q * beat / per + (st["swing"] * beat / per if q % 2 else 0)
                k = ks(0.04)
                add(tq, rng.standard_normal(len(k)) * np.exp(-k * 110) * (0.035 if q % 2 == 0 else 0.018))
        root = note(ch[0] - 12)
        if st["bass"] == "long":
            hits = [(0, bar * 0.95)]
        elif st["bass"] == "kick":
            hits = [(kb * beat, beat * 0.9) for kb in st["kick"]]
        elif st["bass"] == "synco":
            hits = [(x * beat, beat * 0.4) for x in (0, 0.75, 1.5, 2, 2.5, 3.25)]
        else:
            hits = [(x * beat / 2, beat * 0.45) for x in range(8)]
        for j, (t0, ln) in enumerate(hits):
            k = ks(ln)
            f = root * (2 if st["bass"] == "octave" and j % 2 else 1)
            add(t_bar + t0, np.sin(2 * np.pi * f * k) * np.minimum(1, k / 0.005) *
                np.minimum(1, (k[-1] - k) / 0.02 + 1e-3) * np.exp(-k * (1.5 if st["bass"] == "long" else 6)) * 0.22)
    fade = np.ones(n)
    fi, fo = min(int(0.6 * SR), n), min(int(1.5 * SR), n)
    fade[:fi] = np.linspace(0, 1, fi)
    fade[-fo:] = np.minimum(fade[-fo:], np.linspace(1, 0, fo))
    mix *= fade[:, None]
    return mix / (max(1e-9, float(np.abs(mix).max())) / 0.8)   # 장마다 크기를 맞춰 이어 붙였을 때 들쭉날쭉 없게


def sparkle(dur: float = 0.9):
    """'반짝' 빛 소리(높은 종소리 몇 개가 위로) — 빛 효과 장면 전환에 얹는다."""
    n = int(dur * SR)
    out = np.zeros((n, 2))
    for j, m in enumerate((88, 91, 95, 100)):
        s0 = int(j * 0.06 * SR)
        k = np.arange(n - s0) / SR
        sig = np.sin(2 * np.pi * 440 * 2 ** ((m - 69) / 12) * k) * np.exp(-k * 7) * 0.18
        out[s0:, 0] += sig * (1.2 - j * 0.15)
        out[s0:, 1] += sig * (0.8 + j * 0.15)
    return out
