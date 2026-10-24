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


def write_medley(out: Path, durs: list[float], seed: str, xf: float = 0.6, whoosh_at: list[float] | None = None) -> Path:
    """장(페이지)이 바뀔 때마다 다른 곡 — 2026-10-24 사용자 지시(목요일 게시물). 곡 사이는 xf 초 겹쳐 자연스럽게.
    whoosh_at(초) 이 있으면 그 순간마다 '슥' 소리를 얹는다."""
    n_xf = int(xf * SR)
    parts = [render(d + xf, f"{seed}:{i}") for i, d in enumerate(durs)]
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
