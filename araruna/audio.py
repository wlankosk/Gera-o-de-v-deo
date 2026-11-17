#!/usr/bin/env python3
"""Trilha sintetizada + SFX sincronizados com render.py. Saída: WAV 48 kHz estéreo."""
import sys, wave
import numpy as np

SR, DUR = 48000, 37.0
N = int(SR * DUR)
OUT = sys.argv[1] if len(sys.argv) > 1 else "trilha.wav"
rng = np.random.default_rng(1)
L = np.zeros(N); Rr = np.zeros(N)
tt = np.arange(N) / SR

def add(sig, t0, pan=0.0, gain=1.0):
    i = int(t0 * SR); n = min(len(sig), N - i)
    if n <= 0: return
    L[i:i + n] += sig[:n] * gain * (1 - max(pan, 0))
    Rr[i:i + n] += sig[:n] * gain * (1 + min(pan, 0))

def lp(x, a):  # passa-baixa de 1 polo
    y = np.empty_like(x); acc = 0.0
    for i in range(len(x)):
        acc += a * (x[i] - acc); y[i] = acc
    return y

def env(n, att, rel):
    e = np.ones(n); a = int(att * SR); r = int(rel * SR)
    if a: e[:a] = np.linspace(0, 1, a)
    if r: e[-r:] *= np.linspace(1, 0, r) ** 2
    return e

def note(f): return 440 * 2 ** ((f - 69) / 12)

# --- pad: Am  F  C  G  (2 compassos cada, ~4,6 s) ---
chords = [[57, 60, 64, 69], [53, 57, 60, 65], [48, 55, 60, 64], [55, 59, 62, 67]]
step = 4.6
pad = np.zeros(N)
k = 0; t0 = 0.0
while t0 < DUR:
    ch = chords[k % 4]
    n = int((step + 1.2) * SR); t = np.arange(n) / SR
    s = np.zeros(n)
    for m in ch:
        f = note(m)
        for det in (-0.12, 0.12):
            s += np.sin(2 * np.pi * f * (1 + det / 100) * t + rng.random() * 6)
        s += 0.3 * np.sin(2 * np.pi * f * 2 * t)
    s *= env(n, 1.0, 1.2) / len(ch)
    i = int(t0 * SR); m = min(n, N - i); pad[i:i + m] += s[:m]
    t0 += step; k += 1
build = np.clip((tt - 2) / 16, 0, 1) * 0.5 + 0.5
add(pad * build * (1 - np.clip((tt - 35.5) / 1.5, 0, 1)), 0, 0, 0.16)

# --- baixo pulsando a partir do Paraná ---
bass = np.zeros(N)
k = 0; t0 = 9.2
while t0 < 36:
    root = chords[int(t0 / step) % 4][0] - 12
    n = int(0.42 * SR); t = np.arange(n) / SR
    s = np.sin(2 * np.pi * note(root) * t) * np.exp(-t * 6)
    i = int(t0 * SR); m = min(n, N - i); bass[i:i + m] += s[:m]
    t0 += 0.575; k += 1
add(bass, 0, 0, 0.22)

# --- arpejo brilhante na cena da cidade ---
t0 = 19.2; k = 0
while t0 < 35.8:
    ch = chords[int(t0 / step) % 4]
    m = ch[k % 4] + 12
    n = int(0.5 * SR); t = np.arange(n) / SR
    s = (np.sin(2 * np.pi * note(m) * t) + 0.3 * np.sin(4 * np.pi * note(m) * t)) * np.exp(-t * 7)
    add(s, t0, 0.35 if k % 2 else -0.35, 0.07)
    t0 += 0.2875; k += 1

# --- SFX ---
def whoosh(d=1.6, up=True):
    n = int(d * SR); x = rng.standard_normal(n)
    t = np.linspace(0, 1, n)
    sweep = (0.02 + 0.25 * t) if up else (0.27 - 0.25 * t)
    y = np.empty(n); acc = 0.0
    for i in range(n):
        acc += sweep[i] * (x[i] - acc); y[i] = acc
    e = np.sin(np.pi * t) ** 2
    return y * e * 3

def boom(f=48, d=1.8):
    n = int(d * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * f * t * (1 + 0.6 * np.exp(-t * 8))) * np.exp(-t * 2.6)

def chime(f=1760, d=1.4):
    n = int(d * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 4)) * np.exp(-t * 3.5)

def bell(f=392, d=3.2):
    n = int(d * SR); t = np.arange(n) / SR
    parts = [(1, 1), (2.0, .6), (2.4, .4), (3.0, .3), (4.2, .2), (0.5, .5)]
    return sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t * (1.2 + r)) for r, a in parts) / 2

def squawk(d=0.32):
    n = int(d * SR); t = np.arange(n) / SR
    f = 900 + 500 * np.sin(np.pi * t / d) - 300 * t / d
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sign(np.sin(ph)) * 0.4 + np.sin(2 * ph) * 0.4 + 0.25 * rng.standard_normal(n)
    return lp(s, 0.35) * np.sin(np.pi * t / d) ** 0.7

def flap(d=0.12):
    n = int(d * SR); x = rng.standard_normal(n)
    return lp(x, 0.08) * np.exp(-np.arange(n) / SR * 40) * 4

add(whoosh(2.4), 0.2, 0, 0.35)                 # globo girando
for t0, pan in ((6.0, -0.2), (9.4, 0.2), (13.0, -0.2)):
    add(whoosh(1.8), t0, pan, 0.5)               # zooms
for t0 in (6.4, 10.8, 14.6):
    add(chime(1568), t0, 0.2, 0.18)              # títulos do mapa
add(boom(55, 1.6), 15.7, 0, 0.7)                 # pin cai
add(chime(2093, 1.0), 15.7, -0.2, 0.12)
add(whoosh(1.4, True), 17.8, 0, 0.7)             # mergulho
add(boom(42, 2.2), 19.15, 0, 0.9)                # portal
add(chime(2637, 2.0), 19.15, 0.3, 0.15)
for i, t0 in enumerate((19.6, 20.5, 21.6)):
    add(squawk(), t0, -0.4 + 0.4 * i, 0.22)      # arara
for i in range(26):
    add(flap(), 19.0 + i * 0.35, -0.5 + i / 26, 0.10)
add(bell(392), 23.3, 0, 0.30)                    # sino da matriz
add(bell(392), 24.5, 0, 0.18)
add(chime(1760), 26.8, -0.2, 0.15)
add(whoosh(1.2), 26.2, 0, 0.35)                  # tilt pro campo
add(chime(1976), 30.3, 0.2, 0.15)
add(boom(50, 2.0), 33.4, 0, 0.7)                 # card final
add(chime(2349, 1.6), 35.3, 0, 0.2)              # CTA

# ambiência de campo (vento leve) na cena
wind = lp(rng.standard_normal(N), 0.01) * 6
add(wind * np.clip((tt - 19) * 2, 0, 1) * (1 - np.clip((tt - 35) / 2, 0, 1)), 0, 0, 0.05)

st = np.stack([L, Rr], 1)
st /= np.abs(st).max() * 1.12
fade = np.clip((DUR - tt) / 0.6, 0, 1)[:, None]
st *= fade
with wave.open(OUT, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st * 32767).astype("<i2").tobytes())
