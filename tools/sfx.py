"""In-app sound effects for Origami Crane, synthesised with numpy (run with Blender's bundled python, which has numpy):

    $(ls /Applications/Blender.app/Contents/Resources/*/python/bin/python3.13) -I tools/sfx.py

Writes app/assets/sfx/*.wav (44.1 kHz mono 16-bit): crease_0..3 (paper crease, four variations), rewind, awaken, takeoff,
flutter, vanish, furin_0..2 (glass wind chime), ambience (seamless 24 s loop: soft wind, leaves, distant birds).
"""
import math
import os
import wave

import numpy as np

SR = 44100
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "assets", "sfx")
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(7)


def write(name, x, peak=0.89):
    x = np.asarray(x, np.float64)
    # trim the silent reverb tail and fade the last 60 ms (no clicks)
    nz = np.nonzero(np.abs(x) > np.max(np.abs(x)) * 1e-3)[0]
    if len(nz):
        x = x[: min(len(x), nz[-1] + int(0.05 * SR))]
    f = min(len(x), int(0.06 * SR))
    x[-f:] *= np.linspace(1, 0, f)
    m = np.max(np.abs(x)) or 1.0
    x = x / m * peak
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("SFX", name, f"{len(x) / SR:.2f}s")


def t_(d):
    return np.arange(int(d * SR)) / SR


def onepole(x, fc):
    """one-pole low-pass, fc may be an array (time-varying)"""
    fc = np.broadcast_to(np.asarray(fc, np.float64), x.shape)
    a = np.exp(-2 * math.pi * fc / SR)
    y = np.empty_like(x)
    s = 0.0
    for i in range(len(x)):
        s = (1 - a[i]) * x[i] + a[i] * s
        y[i] = s
    return y


def band(x, lo, hi):
    return onepole(x, hi) - onepole(x, lo)


def env(n, a, d):
    """attack a s, exponential decay d s (time constant)"""
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-np.maximum(0, t - a) / d)


def reverb(x, size=0.25, mix=0.25):
    """small room: a few feedback combs + allpass"""
    y = np.zeros(len(x) + int(SR * 1.2))
    y[: len(x)] = x
    out = np.zeros_like(y)
    for dl, g in ((0.0297, 0.77), (0.0371, 0.74), (0.0411, 0.72), (0.0437, 0.7)):
        d = int(dl * SR * (1 + size))
        c = y.copy()
        for i in range(d, len(c)):
            c[i] += g * c[i - d]
        out += c
    out /= 4
    return y * (1 - mix) + out * mix


# ── paper crease: crackle + papery hiss + soft thump ──
for k in range(4):
    n = int(0.32 * SR)
    noise = rng.standard_normal(n)
    crack = np.zeros(n)
    for _ in range(18 + 6 * k):
        i = int(rng.uniform(0.0, 0.12 + 0.02 * k) * SR)
        crack[i : i + 40] += rng.uniform(0.4, 1.0) * np.exp(-np.arange(min(40, n - i)) / 6)
    hiss = band(noise, 1800, 7500) * env(n, 0.004, 0.05 + 0.01 * k)
    crisp = band(crack * rng.standard_normal(n), 2500, 9000)
    thump = np.sin(2 * math.pi * (95 + 12 * k) * t_(0.32)) * env(n, 0.002, 0.045)
    write(f"crease_{k}", reverb(0.7 * hiss + 1.1 * crisp + 0.45 * thump, 0.1, 0.12))

# ── whoosh helpers ──
def whoosh(d, f0, f1, peak_at=0.6, rev=False):
    n = int(d * SR)
    u = np.linspace(0, 1, n)
    fc = f0 + (f1 - f0) * u
    e = np.where(u < peak_at, (u / peak_at) ** 2, ((1 - u) / (1 - peak_at)) ** 1.5)
    x = band(rng.standard_normal(n), fc * 0.35, fc) * e
    return x[::-1] if rev else x


# rewind: reversed airy whoosh + a rising sparkle
rw = whoosh(1.4, 600, 5200, 0.85)
tt = t_(1.4)
sp = sum(np.sin(2 * math.pi * f * tt) * np.exp(-((tt - 0.25 - 0.18 * i) ** 2) / 0.002) for i, f in enumerate([1568, 1760, 2093, 2349, 2637, 3136]))
write("rewind", reverb(rw + 0.18 * sp, 0.3, 0.3))

# awaken: soft bell arpeggio in D yo-scale (D E G A B), glassy partials, long tail
notes = [587.33, 659.25, 783.99, 880.0, 987.77, 1174.66]
d = 2.6
x = np.zeros(int(d * SR))
for i, f in enumerate(notes):
    st = int(i * 0.075 * SR)
    tt = t_(d - i * 0.075)
    tone = (np.sin(2 * math.pi * f * tt) + 0.35 * np.sin(2 * math.pi * f * 2.76 * tt) * np.exp(-tt / 0.4) + 0.12 * np.sin(2 * math.pi * f * 5.4 * tt) * np.exp(-tt / 0.15))
    x[st : st + len(tt)] += tone * np.exp(-tt / 0.9) * (0.9 - 0.08 * i)
x *= np.minimum(1, (len(x) - np.arange(len(x))) / (0.6 * SR))
write("awaken", reverb(x, 0.6, 0.35))

# takeoff: breathy rising whoosh + wing beats
n = int(1.6 * SR)
wb = np.zeros(n)
for i in range(6):
    st = int((0.1 + 0.2 * i) * SR)
    m = min(int(0.12 * SR), n - st)
    wb[st : st + m] += band(rng.standard_normal(m), 200, 1500) * env(m, 0.01, 0.04)
write("takeoff", reverb(whoosh(1.6, 300, 2400, 0.5) + 0.8 * wb, 0.3, 0.2))

# flutter: soft paper wing beats (one second, loopable-ish)
n = int(1.0 * SR)
fl = np.zeros(n)
for i in range(5):
    st = int(i * 0.2 * SR)
    m = min(int(0.15 * SR), n - st)
    fl[st : st + m] += band(rng.standard_normal(m), 300, 2500) * env(m, 0.015, 0.05) * (0.7 + 0.3 * rng.random())
write("flutter", fl)

# vanish: shimmering bloom (stacked detuned partials swelling then fading) + high sparkles
d = 2.4
tt = t_(d)
sh = np.zeros_like(tt)
for f in (1174.66, 1318.5, 1567.98, 1760.0, 2349.3):
    for dt in (-1.5, 1.5):
        sh += np.sin(2 * math.pi * (f + dt) * tt)
sh *= np.minimum(1, tt / 0.35) * np.exp(-np.maximum(0, tt - 0.35) / 0.7)
spk = np.zeros_like(tt)
for _ in range(40):
    c = rng.uniform(0.05, 1.6)
    f = rng.uniform(3000, 7000)
    spk += np.sin(2 * math.pi * f * tt) * np.exp(-((tt - c) ** 2) / 0.00003)
write("vanish", reverb(sh * 0.6 + spk * 0.5, 0.7, 0.4))

# furin: glass wind chime (inharmonic bell partials, clapper rattle)
for k, f in enumerate((2093.0, 2349.3, 2637.0)):
    d = 2.8
    tt = t_(d)
    x = np.zeros_like(tt)
    for j, st in enumerate((0.0, 0.11, 0.19)):
        m = tt >= st
        u = tt[m] - st
        a = (1.0, 0.45, 0.25)[j]
        x[m] += a * (np.sin(2 * math.pi * f * u) * np.exp(-u / 1.1) + 0.5 * np.sin(2 * math.pi * f * 2.32 * u) * np.exp(-u / 0.5) + 0.25 * np.sin(2 * math.pi * f * 4.1 * u) * np.exp(-u / 0.25))
    write(f"furin_{k}", reverb(x, 0.4, 0.25), 0.6)

# ambience: 24 s seamless loop — soft wind through leaves + a few distant birds
d = 24.0
n = int(d * SR)
tt = t_(d)
wind = onepole(onepole(band(rng.standard_normal(n), 80, 600), 700), 900) * (0.6 + 0.4 * np.sin(2 * math.pi * tt / 8.0) ** 2)
leaves = onepole(band(rng.standard_normal(n), 2000, 5000), 5000) * (0.05 + 0.06 * np.sin(2 * math.pi * tt / 6.0 + 1) ** 4)
birds = np.zeros(n)
for _ in range(9):
    c = rng.uniform(1, d - 2)
    for j in range(int(rng.integers(2, 5))):
        st = int((c + j * rng.uniform(0.09, 0.16)) * SR)
        m = int(0.08 * SR)
        u = np.arange(m) / SR
        f = rng.uniform(2800, 4200) + 1800 * u / 0.08 * rng.choice([-1, 1])
        birds[st : st + m] += np.sin(2 * math.pi * np.cumsum(f) / SR) * np.sin(math.pi * u / 0.08) * 0.25
amb = 3.0 * wind / (np.max(np.abs(wind)) or 1) + leaves / (np.max(np.abs(leaves)) or 1) * 0.35 + birds
fade = int(1.5 * SR)  # loop seam: crossfade the tail into the head
amb[:fade] = amb[:fade] * np.linspace(0, 1, fade) + amb[-fade:] * np.linspace(1, 0, fade)
amb = amb[: n - fade]
write("ambience", amb, 0.5)
