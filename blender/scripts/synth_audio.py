# Origami Crane sound effects, synthesised instruments and the sampled-instrument loader for the clip music.
# Ported from ../soap-bubbles/blender/scripts/synth_audio.py (DSP helpers, felt / pluck notes, birds, reverb).
#
# Used two ways:
#   1. imported by mix_clip.py (the X clip mix): every generator takes the sample rate (+ a seed) and returns mono float
#      arrays; the Sampler classes (load_piano / load_strings / load_flute / load_horns) read the Logic / GarageBand
#      factory sample libraries of this Mac at mix time (nothing is copied into the repo) and render notes as stereo.
#   2. run directly: writes one-shots for a possible in-app use to render/sfx/ (mono 44.1 kHz 16-bit WAV, peak −1 dBFS):
#        crease_1..crease_4  soft paper crease (crinkle + muffled pat + finger slide), four pitches
#        rustle              the sheet sliding under the finger (before a crease)
#        rewind              reverse whoosh with sparkle (old storyboard)
#        furin               glassy wind-chime ding
#        awaken              magical chime swell (old clip)
#        flutter             one flap-flap-glide of paper wings
#        whoosh              gentle airy take-off whoosh
#        bloom               soft shimmer of light (the crane vanishing in the sky)
#      `--app` writes them to app/assets/sfx/ instead (only when the app owner asks for it).
#
# Run with Blender's bundled Python (has numpy):
#   /Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 blender/scripts/synth_audio.py [--app]
import glob, math, os, re, shutil, struct, subprocess, sys, wave

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


# ───────────────────────── basic DSP ─────────────────────────
def tt(sec, sr):
    return np.arange(int(round(sec * sr))) / sr


def band(x, lo, hi, sr):
    """FFT band-pass with soft (4th order-ish) edges; lo or hi may be None."""
    if len(x) < 4:
        return x
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    m = np.ones_like(f)
    if lo:
        m /= 1 + (lo / np.maximum(f, 1)) ** 4
    if hi:
        m /= 1 + (f / hi) ** 4
    return np.fft.irfft(X * m, len(x))


def peak_eq(x, f0, gain_db, q, sr):
    """Gentle FFT bell boost/cut (formants, presence)."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    g = 10 ** (gain_db / 20)
    bw = f0 / q
    m = 1 + (g - 1) / (1 + ((f - f0) / (bw / 2)) ** 2)
    return np.fft.irfft(X * m, len(x))


def fades(x, sr, a=0.001, r=0.01):
    x = x.copy()
    na, nr = max(1, int(a * sr)), max(1, int(r * sr))
    na, nr = min(na, len(x)), min(nr, len(x))
    x[:na] *= np.linspace(0, 1, na)
    x[-nr:] *= np.linspace(1, 0, nr)
    return x


def glide(f, sr):
    """Phase of a sine with per-sample frequency f (Hz)."""
    return 2 * np.pi * np.cumsum(f) / sr


def place(dst, src, at, sr, gain=1.0):
    i = int(round(at * sr))
    if i >= len(dst) or i + len(src) <= 0:
        return
    s = src * gain
    if i < 0:
        s, i = s[-i:], 0
    s = s[: len(dst) - i]
    dst[i:i + len(s)] += s


def reverb(x, sr, decay=2.4, mix=0.32, seed=9):
    """Cheap convolution reverb: exponentially decaying filtered noise IR (mono)."""
    rng = np.random.default_rng(seed)
    n = int(decay * sr)
    ir = band(rng.standard_normal(n), 300, 7000, sr) * np.exp(-np.arange(n) / sr / (decay / 6.9))
    ir /= np.sqrt(np.sum(ir ** 2))
    L = len(x) + n
    y = np.fft.irfft(np.fft.rfft(x, L) * np.fft.rfft(ir, L), L)[:len(x)]
    return x * (1 - mix) + y * mix


def noise_sweep(sr, seed, level, f_lo, f_hi, q=1.6, seg=1024):
    """Band of noise whose centre follows a per-sample curve between f_lo and f_hi (level 0..1 sets both loudness and
    position in the band). Overlap-added Hann segments."""
    rng = np.random.default_rng(seed)
    n = len(level)
    nz = rng.standard_normal(n)
    out = np.zeros(n)
    win = np.hanning(seg)
    for i in range(0, max(1, n - seg), seg // 4):
        lv = float(level[i:i + seg].mean())
        if lv < 1e-4:
            continue
        fc = f_lo * (f_hi / f_lo) ** min(1.0, lv)
        out[i:i + seg] += band(nz[i:i + seg], fc / q, fc * q, sr) * win * 0.5
    return out * level


# ───────────────────────── instruments ─────────────────────────
def koto(sr, f, dur=1.6, bright=0.55, seed=0, bend=True):
    """Plucked koto / shamisen-ish string: Karplus-Strong (block-vectorised), bright pick noise, a little "press" bend up
    into the note (koto players push the string), a nasal body formant around 1.1 kHz and a faint buzz (sawari)."""
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    L = max(2, int(round(sr / f)))
    y = np.zeros(n + L + 1)
    exc = rng.uniform(-1, 1, L)
    exc = band(np.concatenate([exc, exc]), 60, 2500 + 9000 * bright, sr)[:L]  # brighter pick = more highs in the burst
    y[:L] = exc
    decay = 0.996 ** (440 / f) ** 0.25
    pos = L
    while pos < n + L:
        e = min(pos + L, n + L)
        prev = y[pos - L:e - L]
        prev2 = y[pos - L - 1:e - L - 1] if pos - L - 1 >= 0 else np.concatenate([[0], y[pos - L:e - L - 1]])
        y[pos:e] = decay * (0.5 + 0.08 * bright) * prev + decay * (0.5 - 0.08 * bright) * prev2[:e - pos]
        pos = e
    x = y[L:L + n]
    if bend:                                      # pitch "press": read the buffer slightly slower at the start
        t = np.arange(n) / sr
        rate = 1 - 0.012 * np.exp(-t / 0.05)
        idx = np.clip(np.cumsum(rate), 0, n - 2)
        i0 = idx.astype(int)
        x = x[i0] + (x[i0 + 1] - x[i0]) * (idx - i0)
    x = peak_eq(x, 1100, 4, 1.4, sr)
    x += np.tanh(x * 3) * 0.04                    # sawari buzz
    t = np.arange(n) / sr
    pick = band(rng.standard_normal(n), 2000, 9000, sr) * np.exp(-t / 0.004) * 0.25 * bright
    x = (x / (np.max(np.abs(x)) + 1e-9) + pick) * np.exp(-t / (dur * 0.45))
    return fades(x, sr, 0.0005, 0.05)


def marimba(sr, f, vel=1.0, seed=0):
    """Soft marimba bar: fundamental + tuned 4th/10th partials that die fast, a soft mallet knock."""
    rng = np.random.default_rng(seed)
    dec = 0.55 * (440 / f) ** 0.45
    t = tt(min(1.6, dec * 4), sr)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t / dec)
    x += 0.3 * np.sin(2 * np.pi * f * 3.93 * t + 0.3) * np.exp(-t / (dec * 0.16))
    if f * 9.2 < 16000:
        x += 0.08 * np.sin(2 * np.pi * f * 9.2 * t + 0.9) * np.exp(-t / (dec * 0.05))
    knock = band(rng.standard_normal(len(t)), 600, 3500, sr) * np.exp(-t / 0.0025) * 0.15
    return fades((x + knock) * np.minimum(t / 0.0015, 1) * 0.42 * vel, sr, 0.0, 0.03)


def kalimba(sr, f, vel=1.0, seed=0):
    """Kalimba tine: sine with a soft inharmonic overtone and a tiny metallic tick."""
    rng = np.random.default_rng(seed)
    t = tt(1.3, sr)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.42)
    x += 0.16 * np.sin(2 * np.pi * f * 5.95 * t) * np.exp(-t / 0.045)
    x += 0.08 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t / 0.2)
    tick = band(rng.standard_normal(len(t)), 2500, 8000, sr) * np.exp(-t / 0.0015) * 0.1
    return fades((x + tick) * np.minimum(t / 0.0015, 1) * 0.35 * vel, sr, 0.0, 0.05)


def glock(sr, f, vel=1.0, sec=1.8):
    t = tt(sec, sr)
    x = sum(a * np.sin(2 * np.pi * f * r * t + r) * np.exp(-t / d) for r, a, d in ((1, 1, 0.9), (2.76, 0.3, 0.25), (5.4, 0.12, 0.08), (8.93, 0.05, 0.04)))
    return fades(x * np.minimum(t / 0.0008, 1) * 0.3 * vel, sr, 0.0, 0.08)


def felt(sr, f, dur=0.9):
    """Felt-hammer music-box note: sine + a whisper of 2nd/3rd harmonic, 9 ms attack, slow vibrato."""
    t = tt(dur, sr)
    vib = 1 + 0.0025 * np.sin(2 * np.pi * 5.0 * t) * np.minimum(t / 0.25, 1)
    ph = glide(f * vib, sr)
    x = np.sin(ph) + 0.08 * np.sin(2 * ph + 0.3) * np.exp(-t / 0.15) + 0.025 * np.sin(3 * ph) * np.exp(-t / 0.08)
    env = (1 - np.exp(-t / 0.009)) * np.exp(-t / (dur * 0.3))
    return fades(x * env, sr, 0.0, 0.05)


# ───────────────────────── paper ─────────────────────────
def crinkle(sr, seed, dur=0.12, lo=1800, hi=9000, density=260, amp=1.0):
    """Crisp paper crinkle: a dense cloud of tiny band-limited clicks (fibres snapping), louder at the start."""
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    out = np.zeros(n)
    t = np.arange(n) / sr
    k = int(density * dur)
    times = np.sort(rng.uniform(0, dur, k) ** 1.6 / dur ** 0.6)
    for t0 in times:
        i = int(t0 * sr)
        ln = int(rng.uniform(0.0004, 0.0018) * sr)
        if i + ln >= n:
            continue
        out[i:i + ln] += rng.standard_normal(ln) * np.hanning(ln) * rng.uniform(0.3, 1.0)
    out = band(out, lo, hi, sr)
    return out * np.exp(-t / (dur * 0.45)) * amp


def crease(sr, seed, pitch=1.0):
    """One fold landing: a crisp crinkle as the crease is pressed, a soft low thump (the flap landing on the stack) and a
    short dry "zip" of a finger running along the fold. `pitch` (≈0.85–1.2) shifts the bands and the thump."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(0.42 * sr))
    place(out, crinkle(sr, seed, 0.13, 1600 * pitch, 8500 * pitch, 300), 0.0, sr, 0.9)
    t = tt(0.16, sr)
    fth = 140 * pitch
    thump = np.sin(glide(fth * (0.7 + 0.3 * np.exp(-t / 0.02)), sr)) * np.exp(-t / 0.035) * np.minimum(t / 0.002, 1)
    thump += band(rng.standard_normal(len(t)), 200, 900, sr) * np.exp(-t / 0.012) * 0.25
    place(out, thump, 0.004, sr, 0.75)
    nz = 0.11
    zl = np.clip(np.arange(int(nz * sr)) / sr / nz, 0, 1)
    zip_ = noise_sweep(sr, seed + 3, np.sin(np.pi * zl) ** 2 * 0.8, 2500 * pitch, 6000 * pitch, 1.3, 256)
    place(out, zip_, 0.03, sr, 0.35)
    out /= np.max(np.abs(out)) + 1e-9            # peak 1: the crinkle's peaks vary a lot with the seed
    return fades(out, sr, 0.0, 0.03)


def rustle(sr, seed, dur=0.45, amp=1.0):
    """Paper sliding / lifting under the finger before a crease: soft airy noise with a few small crinkles."""
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    u = np.arange(n) / n
    lv = np.sin(np.pi * u) ** 1.5 * (0.6 + 0.4 * u)
    out = noise_sweep(sr, seed, lv, 1200, 5000, 1.5, 512) * 0.6
    for _ in range(int(rng.integers(3, 6))):
        place(out, crinkle(sr, int(rng.integers(1e6)), 0.04, 2500, 9000, 400), float(rng.uniform(0.1, dur * 0.9)), sr, 0.35)
    return fades(out * amp, sr, 0.01, 0.05)


# ───────────────────────── magic / air ─────────────────────────
def tinkle(sr, rng, f=None, dur=None, amp=1.0):
    """One glint: a tiny glassy ping (two inharmonic partials), very short."""
    f = f or float(rng.uniform(3200, 7200))
    dur = dur or float(rng.uniform(0.05, 0.12))
    t = tt(dur * 1.6, sr)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t / (dur * 0.35))
    x += 0.3 * np.sin(2 * np.pi * f * 2.71 * t) * np.exp(-t / (dur * 0.15))
    return fades(x * np.minimum(t / 0.002, 1) * amp, sr, 0.0, 0.004)


def sparkle(sr, seed, n=7, spread=0.32, lo=3200, hi=7400, amp=0.35, rising=False, notes=None):
    """n glints over `spread` seconds getting quieter (rising=True: accelerating and getting louder, like a reverse);
    notes: optional list of frequencies to pick from (keeps the glints in key)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int((spread + 0.25) * sr))
    times = np.sort(rng.uniform(0.008, spread, n) ** 1.4 / spread ** 0.4)
    if rising:
        times = np.sort(spread - times)
    for k, t0 in enumerate(times):
        w = k / max(1, n - 1)
        a = amp * ((0.35 + 0.65 * w) if rising else (1 - 0.65 * w)) * float(rng.uniform(0.6, 1.0))
        f = float(rng.choice(notes)) if notes is not None else float(rng.uniform(lo, hi))
        place(out, tinkle(sr, rng, f, amp=a), t0, sr)
    return out


def shimmer(sr, seed, dur, level=None, lo=2200, hi=5200, k=6):
    """Glassy shimmer: a few high partials with slow tremolo, following an optional envelope."""
    rng = np.random.default_rng(seed)
    t = tt(dur, sr)
    x = np.zeros(len(t))
    for _ in range(k):
        f = float(rng.uniform(lo, hi))
        x += np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * (0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(1.5, 4.5) * t + rng.uniform(0, 6)))
    x /= k
    e = np.ones(len(t)) if level is None else level[:len(t)]
    return fades(x * e, sr, 0.05, 0.2)


def reverse_whoosh(sr, seed, dur=1.5):
    """The rewind: a whoosh played "backwards" (swells up, band rising, cuts off with a soft suck) + a reversed
    sparkle accelerating into the end + a cascade of soft paper flips as the folds open."""
    n = int(dur * sr)
    u = np.arange(n) / n
    lv = u ** 2.2 * (1 - np.clip((u - 0.96) / 0.04, 0, 1))
    out = noise_sweep(sr, seed, lv, 500, 6500, 1.6, 1024) * 1.2
    out += band(np.random.default_rng(seed + 1).standard_normal(n), 100, 400, sr) * lv * 0.18
    sp = sparkle(sr, seed + 2, n=22, spread=dur * 0.95, lo=3000, hi=8200, amp=0.3, rising=True)
    place(out, sp[:n], 0.0, sr)
    rng = np.random.default_rng(seed + 3)
    for k in range(14):                           # the folds flipping open, faster toward the end
        t0 = dur * (1 - (1 - (k + rng.uniform(0, 0.6)) / 14) ** 0.7) * 0.95
        place(out, crinkle(sr, seed + 10 + k, 0.05, 2000, 8000, 300), t0, sr, 0.22 + 0.2 * k / 14)
    return fades(out, sr, 0.05, 0.02)


def furin(sr, seed, f=2093.0):
    """Glass wind chime (furin): a struck glass bell = inharmonic partials with slow beating, a clapper tick, long ring."""
    rng = np.random.default_rng(seed)
    t = tt(2.6, sr)
    x = np.zeros(len(t))
    for r, a, d in ((1.0, 1.0, 0.9), (1.0062, 0.6, 1.1), (2.32, 0.35, 0.5), (4.25, 0.16, 0.22), (6.8, 0.07, 0.1)):
        x += a * np.sin(2 * np.pi * f * r * t + rng.uniform(0, 6)) * np.exp(-t / d)
    tick = band(rng.standard_normal(len(t)), 3000, 10000, sr) * np.exp(-t / 0.0012) * 0.4
    x = (x + tick) * np.minimum(t / 0.0008, 1)
    # a second, softer strike (the clapper bounces)
    out = np.zeros(len(t) + int(0.25 * sr))
    place(out, x, 0.0, sr, 0.3)
    place(out, x, float(rng.uniform(0.13, 0.2)), sr, 0.14)
    return fades(out, sr, 0.0, 0.3)


def chime_swell(sr, seed, notes, dur=2.4):
    """The awakening: a glassy shimmer swelling up, a fast rising glockenspiel run on `notes` (Hz) and a soft bell chord
    blooming at the top."""
    out = np.zeros(int((dur + 1.6) * sr))
    u = np.clip(np.arange(int(dur * sr)) / sr / dur, 0, 1)
    env = np.sin(np.pi * u) ** 1.2
    place(out, shimmer(sr, seed, dur, env, 2500, 6500, 8), 0.0, sr, 0.5)
    for k, f in enumerate(notes):
        place(out, glock(sr, f, 0.5 + 0.4 * k / len(notes), 1.6), 0.03 + k * 0.055, sr, 0.8)
    for k, f in enumerate(notes[-3:]):
        place(out, felt(sr, f / 2, 2.2), 0.05 + 0.02 * k, sr, 0.3)
    place(out, sparkle(sr, seed + 1, n=14, spread=1.1, lo=3500, hi=8000, amp=0.25), 0.3, sr)
    return fades(reverb(out, sr, 2.2, 0.3, seed), sr, 0.0, 0.3)


def flap(sr, seed, amp=1.0):
    """One paper wing beat: a short soft "fwup" of air with a papery edge."""
    rng = np.random.default_rng(seed)
    n = int(0.16 * sr)
    u = np.arange(n) / n
    lv = np.sin(np.pi * np.clip(u / 0.75, 0, 1)) ** 2
    x = noise_sweep(sr, seed, lv * 0.7, 300, 1800, 1.8, 256)
    place(x, crinkle(sr, seed + 1, 0.06, 2500, 7500, 200, 0.12), 0.01, sr)
    x += band(rng.standard_normal(n), 80, 300, sr) * lv * 0.25
    return fades(x * amp, sr, 0.005, 0.03)


def flutter(sr, seed, dur, rate=2.2, amp=1.0):
    """Wings while it flies: flap-flap-glide pattern (two beats then a glide), slightly irregular."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int((dur + 0.3) * sr))
    t = 0.0
    k = 0
    cyc = 1.0 / rate
    while t < dur:
        for j in range(2):
            place(out, flap(sr, seed + k, float(rng.uniform(0.7, 1.0)) * amp), t + j * cyc * 0.42, sr)
            k += 1
        t += cyc * float(rng.uniform(1.6, 2.1))
    return out


def whoosh(sr, seed, dur=0.9, lo=250, hi=3000, peak=0.45):
    """Breathy whoosh passing by: band rising then falling, peak at `peak` of the length."""
    n = int(dur * sr)
    u = np.arange(n) / n
    lv = np.where(u < peak, (u / peak) ** 1.8, ((1 - u) / (1 - peak)) ** 1.4)
    x = noise_sweep(sr, seed, lv, lo, hi, 1.7, 1024)
    x = peak_eq(x, 1100, 3, 1.0, sr)               # breathy "hh"
    x += band(np.random.default_rng(seed + 1).standard_normal(n), 70, 260, sr) * lv * 0.12
    return fades(x, sr, 0.02, 0.05)


def bloom(sr, seed, notes):
    """The vanish: a bright soft flash = shimmering sparkle bloom (dense glints spreading out), an airy swell and a high bell
    chord on `notes` (Hz)."""
    out = np.zeros(int(3.2 * sr))
    place(out, sparkle(sr, seed, n=40, spread=1.6, lo=3000, hi=9000, amp=0.32), 0.0, sr)
    u = np.clip(np.arange(int(2.0 * sr)) / sr / 2.0, 0, 1)
    env = np.minimum(u / 0.04, 1) * np.exp(-u * 3)
    place(out, shimmer(sr, seed + 1, 2.0, env, 3000, 8000, 10), 0.0, sr, 0.5)
    place(out, whoosh(sr, seed + 2, 0.8, 1500, 7000, 0.12), 0.0, sr, 0.35)
    for k, f in enumerate(notes):
        place(out, glock(sr, f, 0.6, 2.4), 0.01 + 0.03 * k, sr, 0.5)
    return fades(reverb(out, sr, 2.6, 0.35, seed), sr, 0.0, 0.4)


# ───────────────────────── ambience ─────────────────────────
def bird(sr, seed):
    """Distant garden bird: two or three quick FM chirps (very quiet in the mix)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(0.7 * sr))
    t0 = 0.0
    for _ in range(int(rng.integers(2, 4))):
        d = float(rng.uniform(0.06, 0.11))
        t = tt(d, sr)
        u = t / d
        f = float(rng.uniform(2600, 3600)) * (1 + 0.35 * np.sin(np.pi * u)) * (1 + 0.04 * np.sin(2 * np.pi * 45 * t))
        place(out, np.sin(glide(f, sr)) * np.sin(np.pi * u) ** 2, t0, sr)
        t0 += d + float(rng.uniform(0.04, 0.09))
    return out


def higurashi(sr, seed, dur=3.0):
    """Evening cicada (higurashi) far away: a 'kana-kana-kana' of fast trilled tones falling slowly in pitch and level."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int((dur + 0.3) * sr))
    t0, k = 0.0, 0
    f0 = float(rng.uniform(4300, 4900))
    while t0 < dur:
        d = 0.11
        t = tt(d, sr)
        u = t / d
        f = f0 * (1 - 0.06 * u) * (1 - 0.05 * t0 / dur)
        am = 0.5 + 0.5 * np.sin(2 * np.pi * 95 * t)
        place(out, np.sin(glide(f, sr)) * am * np.sin(np.pi * u) ** 1.5 * (1 - 0.6 * t0 / dur), t0, sr)
        t0 += 0.135 + 0.01 * np.sin(k)
        k += 1
    return out


# ───────────────────────── soft, natural SFX (the v4 clip) ─────────────────────────
def grain_env(sr, rng, n, density, g_lo=0.002, g_hi=0.009, decay=None):
    """Smooth crackle envelope: many overlapping Hann grains (2–9 ms, never shorter, so no clicks) with random, mostly
    small amplitudes (exponential distribution = a few louder snaps among many soft ones)."""
    env = np.zeros(n)
    k = max(1, int(density * n / sr))
    pos = rng.uniform(0, 1, k) ** (1.0 if decay is None else decay)
    for p, a in zip(pos, rng.exponential(1.0, k)):
        ln = int(rng.uniform(g_lo, g_hi) * sr)
        i = int(p * (n - ln - 1))
        if i >= 0 and ln > 2:
            env[i:i + ln] += np.hanning(ln) * min(a, 3.0)
    return env


def paper_crinkle(sr, seed, dur=0.2, lo=700, hi=5200, density=420, amp=1.0):
    """Soft paper crinkle: band-limited noise under a smooth grain envelope (fibres giving way), front-loaded,
    soft-saturated so no single grain pokes out."""
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    env = grain_env(sr, rng, n, density, decay=1.5)
    x = band(rng.standard_normal(n), lo, hi, sr) * env
    x = np.tanh(x / (np.percentile(np.abs(x), 99.5) + 1e-9)) * np.exp(-np.arange(n) / sr / (dur * 0.6))
    return fades(band(x, None, hi * 0.95, sr) * amp, sr, 0.004, 0.03)


def paper_crease(sr, seed, pitch=1.0):
    """One fold landing, natural and quiet: a short soft crinkle as the crease is pressed, a muffled "pat" of the flap on
    the stack and a finger sliding along the fold. `pitch` (≈0.9–1.15) moves the bands a little."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(0.5 * sr))
    place(out, paper_crinkle(sr, seed, 0.16, 650 * pitch, 4800 * pitch, 380), 0.0, sr, 0.8)
    t = tt(0.07, sr)                                 # the pat: low-passed noise puff, 4 ms rise (no click)
    pat = band(rng.standard_normal(len(t)), 90, 700, sr) * (1 - np.exp(-t / 0.004)) * np.exp(-t / 0.018)
    place(out, pat / (np.abs(pat).max() + 1e-9), 0.006, sr, 0.35)
    n = int(0.22 * sr)                               # the finger running along the fold
    u = np.arange(n) / n
    slide = noise_sweep(sr, seed + 3, np.sin(np.pi * u) ** 2 * 0.7, 900 * pitch, 2600 * pitch, 1.6, 512)
    place(out, slide, 0.05, sr, 0.3)
    out /= np.abs(out).max() + 1e-9
    return fades(out, sr, 0.003, 0.08)


def paper_slide(sr, seed, dur=0.45, amp=1.0):
    """The sheet lifting / sliding under the finger before a crease: airy, dark-ish noise with a few soft crinkles."""
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    u = np.arange(n) / n
    lv = np.sin(np.pi * u) ** 1.6 * (0.6 + 0.4 * u)
    out = noise_sweep(sr, seed, lv, 500, 2600, 1.6, 1024) * 0.7
    for _ in range(int(rng.integers(2, 4))):
        place(out, paper_crinkle(sr, int(rng.integers(1e6)), 0.06, 900, 4200, 300), float(rng.uniform(0.1, dur * 0.8)),
              sr, 0.25)
    return fades(out * amp, sr, 0.02, 0.06)


def air_whoosh(sr, seed, dur=1.3, lo=180, hi=1600, peak=0.4):
    """Gentle airy whoosh (take-off): a dark noise band rising then falling, no hiss on top."""
    n = int(dur * sr)
    u = np.arange(n) / n
    lv = np.where(u < peak, np.sin(np.pi / 2 * u / peak) ** 2, np.cos(np.pi / 2 * (u - peak) / (1 - peak)) ** 1.6)
    x = noise_sweep(sr, seed, lv, lo, hi, 1.8, 2048)
    x += band(np.random.default_rng(seed + 1).standard_normal(n), 60, 220, sr) * lv * 0.1
    return fades(band(x, None, 4000, sr), sr, 0.05, 0.1)


def light_shimmer(sr, seed, freqs, dur=3.0):
    """Soft shimmer of light (the vanish): slowly blooming, gently beating sine partials on `freqs` (Hz, in key) with a
    whisper of air; nothing struck, no glints."""
    rng = np.random.default_rng(seed)
    t = tt(dur, sr)
    x = np.zeros(len(t))
    for k, f in enumerate(freqs):
        a0 = 0.08 * k
        e = np.clip((t - a0) / 0.5, 0, 1) ** 2 * np.exp(-np.maximum(t - a0, 0) / (dur * 0.35))
        for d in (-0.0015, 0.0015):
            x += np.sin(2 * np.pi * f * (1 + d) * t + rng.uniform(0, 6)) * e * (1 + 0.3 * np.sin(2 * np.pi * rng.uniform(2, 4) * t))
    x /= max(1, len(freqs))
    u = np.clip(t / dur, 0, 1)
    air = band(rng.standard_normal(len(t)), 1500, 5000, sr) * np.sin(np.pi * u ** 0.5) ** 2 * 0.12
    return fades(band(x + air, 200, 7000, sr), sr, 0.05, 0.4)


# ───────────────────────── sampled instruments (Logic / GarageBand libraries, read at mix time) ─────────────────────────
# Nothing is copied into the repo: the mix reads the factory sample libraries of this Mac. Pitch = resampling from the
# nearest sampled note (4-point Hermite), sustain loops from the WAV `smpl` chunks, release envelopes per note.
LOGIC = "/Library/Application Support/Logic"
GB_FILES = "/Library/Application Support/GarageBand/Instrument Library/Sampler/Sampler Files"
PIANO_EXS = f"{LOGIC}/Sampler Instruments/01 Acoustic Pianos/Steinway Grand Piano 2.exs"
PIANO_CAF = f"{LOGIC}/EXS Factory Samples/01 Acoustic Pianos/Steinway Piano_consolidated.caf"
NOTE_PC = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


def note_midi(name):
    """'C#4' → 61 (C4 = 60)."""
    m = re.fullmatch(r"([A-G]#?)(-?\d)", name)
    return NOTE_PC[m[1]] + 12 * (int(m[2]) + 1)


def ffmpeg_decode(path, sr=44100):
    """Any audio file → float32 stereo at `sr` (fallback for formats the fast readers below do not handle)."""
    ff = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    raw = subprocess.run([ff, "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(sr), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, "<f4").reshape(-1, 2)


def read_wav(path):
    """RIFF WAV → (float32 stereo, sr, smpl pitch (MIDI + fraction) or None, (loop start, loop end) or None)."""
    d = open(path, "rb").read()
    o, ch, sr, bits, data, pitch, loop = 12, 2, 44100, 16, None, None, None
    while o + 8 <= len(d):
        cid, sz = d[o:o + 4], struct.unpack("<I", d[o + 4:o + 8])[0]
        b = d[o + 8:o + 8 + sz]
        if cid == b"fmt ":
            _, ch, sr, _, _, bits = struct.unpack("<HHIIHH", b[:16])
        elif cid == b"data":
            data = b
        elif cid == b"smpl" and len(b) >= 36:
            f = struct.unpack("<9I", b[:36])
            pitch = f[3] + f[4] / 2 ** 32
            if f[7] and len(b) >= 60:
                lp = struct.unpack("<6I", b[36:60])
                loop = (lp[2], lp[3])
        o += 8 + sz + (sz & 1)
    if bits == 16:
        x = np.frombuffer(data, "<i2").reshape(-1, ch).astype(np.float32) / 32768
    elif bits == 24:
        a = np.frombuffer(data, np.uint8).reshape(-1, 3).astype(np.int32)
        v = (a[:, 0] | (a[:, 1] << 8) | (a[:, 2] << 16))
        x = (np.where(v >= 1 << 23, v - (1 << 24), v).astype(np.float32) / 8388608).reshape(-1, ch)
    else:
        x, sr = ffmpeg_decode(path), 44100
    if x.shape[1] == 1:
        x = np.repeat(x, 2, 1)
    return x[:, :2], sr, pitch, loop


def parse_exs(path):
    """Logic EXS24 instrument: 84-byte chunk headers (uint32 sig, uint32 size, uint32 id, 4 bytes, 'TBOS', 64-byte name),
    then `size` data bytes; chunk type = sig >> 24 (0x41 zone, 0x42 group). Zone data: [1] root key, [6]/[7] key low/high,
    [9]/[10] velocity low/high, int32 LE at 12 = sample start (frames into the consolidated file), [88] group index.
    Group data: [5]/[6] velocity low/high. (Layout checked against the audio: every zone's segment has the pitch of its
    root key, see Sampler.check.)"""
    d = open(path, "rb").read()
    o, zones, groups = 0, [], []
    while o + 84 <= len(d):
        sig, size, cid = struct.unpack_from("<III", d, o)
        name = d[o + 20:o + 84].split(b"\0")[0].decode("latin1")
        b = d[o + 84:o + 84 + size]
        kind = (sig >> 24) & 0xFF
        if kind == 0x41 and len(b) > 88:
            zones.append(dict(root=b[1], lo=b[6], hi=b[7], vlo=b[9], vhi=b[10], start=struct.unpack_from("<i", b, 12)[0],
                              group=b[88], name=name))
        elif kind == 0x42 and len(b) > 6:
            groups.append(dict(id=cid, name=name, vlo=b[5], vhi=b[6]))
        o += 84 + size
    return zones, groups


def caf_pcm16(path):
    """Memory-map the PCM data of a 16-bit linear-PCM CAF (big- or little-endian) → int16 (frames, channels), sr.
    None when the file is something else."""
    with open(path, "rb") as f:
        if f.read(8)[:4] != b"caff":
            return None
        off, desc = 8, None
        while True:
            f.seek(off)
            h = f.read(12)
            if len(h) < 12:
                return None
            typ, size = h[:4], struct.unpack(">q", h[4:])[0]
            if typ == b"desc":
                desc = struct.unpack(">d4sIIIII", f.read(32))
            if typ == b"data":
                sr, fmt, flags, _, _, ch, bits = desc
                if fmt != b"lpcm" or bits != 16 or flags & 1:
                    return None
                dt = "<i2" if flags & 2 else ">i2"
                return np.memmap(path, dtype=dt, mode="r", offset=off + 16).reshape(-1, ch), int(sr)
            off += 12 + size


class Zone:
    def __init__(self, pitch, lo, hi, get, sr, loop=None, name=""):
        self.pitch, self.lo, self.hi, self._get, self.sr, self.loop, self.name = pitch, lo, hi, get, sr, loop, name
        self._x = None

    @property
    def x(self):
        if self._x is None:
            self._x = self._get()
        return self._x


def hermite(x, pos):
    """4-point Hermite interpolation of x (n, 2) at fractional positions pos."""
    i = np.floor(pos).astype(np.int64)
    f = (pos - i)[:, None]
    xp = np.concatenate([x[:1], x, x[-1:], x[-1:]])     # pad so i-1 .. i+2 always exist
    i = i + 1
    xm1, x0, x1, x2 = xp[i - 1], xp[i], xp[i + 1], xp[i + 2]
    c1 = 0.5 * (x1 - xm1)
    c2 = xm1 - 2.5 * x0 + 2 * x1 - 0.5 * x2
    c3 = 0.5 * (x2 - xm1) + 1.5 * (x0 - x1)
    return ((c3 * f + c2) * f + c1) * f + x0


def looped(x, loop, need, xf=0.04, sr=44100):
    """Extend a sample past its end by repeating its sustain loop (equal-power crossfade at every join)."""
    ls, le = loop
    le = min(le, len(x))
    if le - ls < sr * 0.2 or need <= le:
        return x
    n = int(xf * sr)
    out = [x[:le]]
    seg = x[ls:le]
    have = le
    w = np.sin(np.linspace(0, np.pi / 2, n))[:, None]
    while have < need + n:
        prev = out[-1]
        head = prev[-n:] * w[::-1] + seg[:n] * w
        out[-1] = prev[:-n]
        out += [head, seg[n:]]
        have += len(seg) - n
    return np.concatenate(out)


class Sampler:
    """A set of sampled zones; note() renders one note as float stereo at `sr_out`."""

    def __init__(self, zones, name, sr_out=48000, tune=0.0):
        self.zones, self.name, self.sr_out, self.tune = zones, name, sr_out, tune

    def zone(self, m):
        inside = [z for z in self.zones if z.lo <= m <= z.hi]
        return min(inside or self.zones, key=lambda z: abs(z.pitch - m))

    def note(self, m, dur, rel=0.3, att=0.0, offset=0.0, lp=None):
        """`dur` seconds held, then a smooth release of `rel` s; `att` = extra fade-in (soft bowing / breath), `offset`
        = seconds skipped into the sample (legato: start past the attack), `lp` = optional low-pass Hz (soft touch)."""
        z = self.zone(m)
        sr = self.sr_out
        ratio = 2 ** ((m - z.pitch + self.tune / 100) / 12) * z.sr / sr
        n = int((dur + rel) * sr)
        p0 = offset * z.sr
        x = z.x
        if z.loop and p0 + n * ratio + 4 > len(x):
            x = looped(x, z.loop, int(p0 + n * ratio) + 8, sr=z.sr)
        n = max(16, min(n, int((len(x) - 4 - p0) / ratio)))
        y = hermite(x, p0 + np.arange(n) * ratio)
        t = np.arange(n) / sr
        e = np.ones(n)
        if att > 0:
            e *= np.sin(np.pi / 2 * np.clip(t / att, 0, 1)) ** 2
        r = np.clip((t - dur) / max(rel, 1e-3), 0, 1)
        e *= (1 - r) ** 2 * np.exp(-3 * r)                 # release: fast at first, smooth to zero
        e[:min(n, 24)] *= np.linspace(0, 1, min(n, 24))  # 0.5 ms de-click
        e[-min(n, 960):] *= np.linspace(1, 0, min(n, 960))  # 20 ms fade at the end of the sample
        y = y * e[:, None]
        if lp:
            y = np.stack([band(y[:, c], None, lp, sr) for c in range(2)], 1)
        return y

    def check(self, notes=(57, 60, 69)):
        """Sanity check of the zone layout: measured pitch (cents off the root) of a few zones."""
        out = []
        for m in notes:
            z = self.zone(m)
            seg = z.x[int(0.1 * z.sr):int(1.6 * z.sr)].mean(1)
            f_exp = 440 * 2 ** ((z.pitch - 69) / 12)
            X = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 8 * len(seg)))
            f = np.fft.rfftfreq(8 * len(seg), 1 / z.sr)
            sel = np.where((f > f_exp * 0.94) & (f < f_exp * 1.06))[0]
            i = sel[np.argmax(X[sel])]
            a, b, c = np.log(X[i - 1:i + 2] + 1e-12)
            fm = f[i] + 0.5 * (a - c) / (a - 2 * b + c) * (f[1] - f[0])
            out.append(1200 * math.log2(fm / f_exp))
        return out


def load_piano(sr_out=48000, vmax=39):
    """Steinway grand (Logic "Steinway Grand Piano 2"): the soft velocity layer (groups with velocity ≤ `vmax`, not the
    pedal-noise groups), whose zones run to the next zone's start in the consolidated CAF (full natural decay). Tuned to
    A440 by the measured offset of the middle zones (the piano is stretch-tuned ~+7 cents in the middle)."""
    zs, gs = parse_exs(PIANO_EXS)
    soft = {g["id"] for g in gs if g["vhi"] <= vmax and "pedal" not in g["name"].lower()}
    starts = sorted({z["start"] for z in zs})
    pcm = caf_pcm16(PIANO_CAF)
    if pcm is None:
        full = ffmpeg_decode(PIANO_CAF)
        pcm = ((full * 32768).astype(np.int16), 44100)
    mm, sr = pcm
    zones = []
    for z in zs:
        if z["group"] not in soft:
            continue
        k = starts.index(z["start"])
        end = starts[k + 1] if k + 1 < len(starts) else len(mm)
        get = (lambda s=z["start"], e=end: np.asarray(mm[s:e], np.float32) / 32768)
        zones.append(Zone(z["root"], z["lo"], z["hi"], get, sr, None, z["name"]))
    p = Sampler(zones, "piano", sr_out)
    cents = p.check()
    p.tune = -float(np.median(cents))
    p.checked = cents
    return p


def load_wav_dir(folder, pattern, name, sr_out=48000, pick=None):
    """GarageBand sampler folder: one sustained note per WAV (note name in the file name, exact pitch + loop from the
    smpl chunk). `pick(filename)` filters the files (dynamics / articulation)."""
    zones = []
    for p in sorted(glob.glob(os.path.join(folder, "*.wav"))):
        fn = os.path.basename(p)
        m = re.search(pattern, fn)
        if not m or (pick and not pick(fn)):
            continue
        x, sr, pitch, loop = read_wav(p)
        pitch = pitch if pitch is not None else note_midi(m[1])
        zones.append(Zone(pitch, -1, -1, (lambda x=x: x), sr, loop, fn))
    return Sampler(zones, name, sr_out)


def load_strings(sr_out=48000, loud=False):
    """String Ensemble: names like '25n7aC4 M.wav' (index, dynamic n/m/f, section, note); soft set = n + m, loud = f."""
    return load_wav_dir(f"{GB_FILES}/String Ensemble", r"^\d+[nmf]\d[ab]([A-G]#?\d)", "strings", sr_out,
                        (lambda f: re.match(r"^\d+f", f)) if loud else (lambda f: re.match(r"^\d+[nm]", f)))


def load_flute(sr_out=48000):
    return load_wav_dir(f"{GB_FILES}/Flute Solo/Flute_LV_na_sus_mf", r"_([A-G]#?\d)\.wav$", "flute", sr_out)


def load_horns(sr_out=48000):
    return load_wav_dir(f"{GB_FILES}/French Horns/French Horns_nA_sus_mf", r"_([A-G]#?\d)\.wav$", "horns", sr_out)


def hall_ir(sr, sec=4.2, rt_lo=2.9, rt_hi=0.9, pre=0.022, seed=3):
    """Stereo hall impulse response: decorrelated noise per channel whose decay time falls with frequency (RT60 `rt_lo`
    below ~500 Hz down to `rt_hi` at 8 kHz, so the tail is warm, never hissy), a handful of soft early reflections,
    `pre` s pre-delay. Energy-normalised."""
    rng = np.random.default_rng(seed)
    n = int(sec * sr)
    t = np.arange(n) / sr
    edges = [0, 250, 500, 1000, 2000, 4000, 8000, None]
    ir = np.zeros((n, 2))
    for ch in range(2):
        for lo, hi in zip(edges[:-1], edges[1:]):
            fc = math.sqrt(max(lo, 60) * (hi or 14000))
            rt = rt_lo if fc < 500 else rt_lo * (rt_hi / rt_lo) ** min(1.0, math.log2(fc / 500) / 4)
            ir[:, ch] += band(rng.standard_normal(n), lo or None, hi, sr) * np.exp(-6.9 * t / rt)
        ir[:, ch] *= np.clip((t - pre) / 0.04, 0, 1)
        for k in range(10):                                  # early reflections 10–70 ms
            d = pre * 0.5 + rng.uniform(0.008, 0.07)
            ir[int(d * sr), ch] += rng.uniform(0.3, 0.7) * (1 - d / 0.09) * 6
        ir[:, ch] = band(ir[:, ch], 120, 9000, sr)
    return ir / np.sqrt((ir ** 2).sum() / 2)


def convolve(x, ir):
    """FFT convolution of stereo x (n, 2) with a stereo IR (m, 2), cut to len(x)."""
    L = len(x) + len(ir)
    nf = 1 << (L - 1).bit_length()
    return np.stack([np.fft.irfft(np.fft.rfft(x[:, c], nf) * np.fft.rfft(ir[:, c], nf), nf)[:len(x)] for c in range(2)], 1)


# ───────────────────────── one-shot export ─────────────────────────
def save_wav(x, path, sr=44100, peak_db=-1.0):
    x = x / (np.max(np.abs(x)) or 1) * 10 ** (peak_db / 20)
    a = np.round(np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(a.tobytes())
    return os.path.getsize(path)


def trim(x, sr, floor_db=-60):
    """Cut the silent tail (keeps files small), with a short fade."""
    thr = np.max(np.abs(x)) * 10 ** (floor_db / 20)
    idx = np.where(np.abs(x) > thr)[0]
    end = min(len(x), (idx[-1] if len(idx) else len(x)) + int(0.01 * sr))
    return fades(x[:end], sr, 0.0, 0.01)


YO = [293.66, 329.63, 392.0, 440.0, 493.88]     # D yo scale (D E G A B), D4..B4


def export_one_shots(out_dir):
    sr = 44100
    os.makedirs(out_dir, exist_ok=True)
    hi = [f * 4 for f in YO] + [YO[0] * 8]
    sounds = {
        **{f"crease_{k + 1}.wav": paper_crease(sr, 100 + k, p) for k, p in enumerate((0.9, 1.0, 1.08, 1.16))},
        "rustle.wav": paper_slide(sr, 7),
        "rewind.wav": reverse_whoosh(sr, 11),
        "furin.wav": furin(sr, 13),
        "awaken.wav": chime_swell(sr, 17, [f * 2 for f in YO] + hi),
        "flutter.wav": flutter(sr, 19, 0.8),
        "whoosh.wav": air_whoosh(sr, 23),
        "bloom.wav": light_shimmer(sr, 29, [YO[0] * 4, YO[3] * 4, YO[4] * 4]),
    }
    for name, x in sounds.items():
        x = trim(x, sr)
        size = save_wav(x, os.path.join(out_dir, name), sr)
        print(f"SFX {name:14s} {len(x) / sr:5.2f}s {size / 1024:6.1f} KB")


if __name__ == "__main__":
    export_one_shots(os.path.join(ROOT, "app", "assets", "sfx") if "--app" in sys.argv else os.path.join(ROOT, "render", "sfx"))
