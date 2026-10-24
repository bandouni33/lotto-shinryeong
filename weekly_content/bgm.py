# -*- coding: utf-8 -*-
"""SNS 짧은 영상용 배경음악 — 코드로 직접 만드는 곡(저작권 문제 없음, 2026-10-24 사용자 지시 '음악 삽입 필수').
4마디 코드 진행(Am-F-C-G) 반복: 신스 패드 + 8분음 아르페지오 + 부드러운 킥/하이햇, 시작 1초 페이드인·끝 2.5초 페이드아웃.
홍보 영상 40초판(2026-10-24)에 쓴 곡과 같은 생성식이다."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
BPM = 112


def write_wav(out: Path, dur: float) -> Path:
    beat = 60 / BPM
    n = int(SR * dur)
    mix = np.zeros((n, 2))

    def note(f):
        return 440.0 * 2 ** ((f - 69) / 12)

    chords = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]   # Am F C G
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
        f = note([ch[0] + 12, ch[1] + 12, ch[2] + 12, ch[1] + 24][i % 4])
        s0 = int(i * step * SR)
        L = min(int(0.45 * SR), n - s0)
        if L <= 0:
            break
        k = np.arange(L) / SR
        sig = (np.sin(2 * np.pi * f * k) + 0.3 * np.sin(2 * np.pi * 2 * f * k)) * env(L, 0.005, 0.18) * 0.07
        pan = 0.5 + 0.3 * np.sin(i * 0.7)
        mix[s0:s0 + L, 0] += sig * (1 - pan) * 2
        mix[s0:s0 + L, 1] += sig * pan * 2

    rng = np.random.default_rng(7)
    for i in range(int(dur / beat)):
        tt = i * beat
        if tt < 2 * bar:
            continue
        s0 = int(tt * SR)
        if i % 2 == 0:
            L = min(int(0.35 * SR), n - s0)
            k = np.arange(L) / SR
            f = 110 * np.exp(-k * 18) + 45
            mix[s0:s0 + L] += (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-k * 9) * 0.32)[:, None]
        for h in (0, 0.5):
            s1 = int((tt + h * beat) * SR)
            L = min(int(0.05 * SR), n - s1)
            if L > 0:
                mix[s1:s1 + L] += (rng.standard_normal(L) * np.exp(-np.arange(L) / SR * 80) * 0.025)[:, None]

    fade = np.ones(n)
    fi, fo = min(SR, n), min(int(2.5 * SR), n)
    fade[:fi] = np.linspace(0, 1, fi)
    fade[-fo:] = np.minimum(fade[-fo:], np.linspace(1, 0, fo))
    mix *= fade[:, None]
    mix /= max(1e-9, float(np.abs(mix).max())) / 0.8
    pcm = (mix * 32767).astype(np.int16)
    out = Path(out)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return out
