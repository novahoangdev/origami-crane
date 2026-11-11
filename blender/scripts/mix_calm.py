# Calm piano soundtrack for the Origami Crane X clip (v5, after the user's review of v4: "the music still snags and is a bit
# unpleasant"). v4 bent its tempo around every fold, modulated twice (D → C → E) and brought in horns and a flute for the
# flight; this one stays put, the way the calm piano of the soap-bubbles garden clip does:
#
#   one steady tempo (~73 BPM, 4/4, the bar derived from the clip so the end card lands on a downbeat), one key (D major),
#   no drums, no modulation. An eight-bar progression Gmaj7 – D/F♯ – Em7 – Asus4 | Bm7 – Gmaj7 – D/A – Asus4, then the
#   first four again, resolving to a rolled Dadd9 on the end card.
#   - felt piano (additive: slightly inharmonic partials, three detuned unisons beating slowly, two-stage decay, a soft
#     hammer): the left hand rolls a slow broken chord under the pedal, the right hand sings a short simple tune while the
#     paper is folded and a second one while the crane flies
#   - strings: a warm, slow ensemble pad, ppp in the room, opening a little when the crane takes off
#   - celesta: three rising notes when the crane wakes up, three falling ones when it fades into the sunset
#   - no sound effects but a few faint distant birds
#
#   /Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 blender/scripts/mix_calm.py \
#       --beats blender/scripts/beats/v5.json
# Writes the WAV named by the beat sheet "audio" (−16 LUFS integrated, true peak ≤ −1 dBTP, 48 kHz stereo 24-bit).
# v6 (user: "still loud, noisy, unpleasant"): −16 LUFS, softer bass + a low shelf, a lighter left hand, no noise SFX.
import json, math, os, re, shutil, subprocess, sys, wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth_audio as sa  # noqa: E402

argv = sys.argv[1:]
arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
ROOT = sa.ROOT
BEATS = json.load(open(os.path.join(ROOT, arg("--beats", "blender/scripts/beats/v5.json"))))
OUT = os.path.join(ROOT, arg("--out", BEATS["audio"]))
EV = BEATS["events"]
SR = 48000
CARD_AT = float(BEATS["app_end"])
CARD = float(BEATS.get("card", 3.0))
DUR = CARD_AT + CARD + 0.4
N = int(DUR * SR)
db = lambda x: 10 ** (x / 20)
ns = lambda sec: int(round(sec * SR))
hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)
band = lambda x, lo, hi: sa.band(x, lo, hi, SR)
rng = np.random.default_rng(11)

F = [float(x) for x in EV["folds"]]
AW, TK, VA = float(EV["awaken"]), float(EV["takeoff"]), float(EV["vanish"])
T0 = 0.35                       # first downbeat (the wide shot)
BARS = int(BEATS.get("bars", 0)) or max(4, round((CARD_AT - T0) / 3.27))   # ~73 BPM whatever the length (12 for the demo)
BAR = (CARD_AT - T0) / BARS     # the card chord lands on the downbeat after the last bar
BEAT = BAR / 4
bar_of = lambda t: (t - T0) / BAR

# (bass, left-hand broken chord, strings voicing)
PROG = [
    (43, [55, 62, 66, 71], [59, 62, 66, 71]),   # Gmaj7
    (42, [54, 62, 66, 69], [57, 62, 66, 69]),   # D/F♯
    (40, [52, 59, 62, 67], [59, 62, 64, 67]),   # Em7
    (45, [57, 64, 67, 69], [57, 62, 64, 69]),   # Asus4
    (47, [54, 59, 62, 66], [59, 62, 66, 69]),   # Bm7
    (43, [55, 59, 62, 66], [59, 62, 66, 71]),   # Gmaj7
    (45, [57, 62, 66, 69], [57, 62, 66, 69]),   # D/A
    (45, [57, 64, 67, 69], [57, 61, 64, 69]),   # Asus4 → A
]
CARD_CH = (38, [50, 57, 64, 66, 69, 74, 76, 78])   # Dadd9, wide
# right-hand tunes: (bar in phrase, beat, midi, beats long, velocity); D major pentatonic, stepwise, long notes
TUNE_A = [
    (0, 0.0, 74, 1.5, 0.48), (0, 1.5, 76, 0.5, 0.4), (0, 2.0, 78, 2.0, 0.48),
    (1, 0.0, 81, 1.5, 0.5), (1, 1.5, 78, 0.5, 0.4), (1, 2.0, 74, 2.0, 0.44),
    (2, 0.0, 76, 1.0, 0.46), (2, 1.0, 74, 1.0, 0.42), (2, 2.0, 71, 2.0, 0.44),
    (3, 0.0, 69, 3.0, 0.42),
]
TUNE_B = [
    (0, 0.0, 78, 1.5, 0.48), (0, 1.5, 81, 0.5, 0.42), (0, 2.0, 83, 2.0, 0.5),
    (1, 0.0, 81, 1.0, 0.46), (1, 1.0, 78, 1.0, 0.42), (1, 2.0, 74, 2.0, 0.44),
    (2, 0.0, 76, 1.5, 0.44), (2, 1.5, 78, 0.5, 0.4), (2, 2.0, 76, 2.0, 0.42),
    (3, 0.0, 74, 1.0, 0.42), (3, 1.0, 76, 3.0, 0.4),
]


def at(bar, beat):
    return T0 + bar * BAR + beat * BEAT + float(rng.normal(0, 0.007))


def put(buf, sig, t, gain=1.0, pan=0.0):
    i = ns(t)
    if i >= len(buf):
        return
    if i < 0:
        sig, i = sig[-i:], 0
    sig = sig[:len(buf) - i] * gain
    if sig.ndim == 1:
        buf[i:i + len(sig), 0] += sig * math.sqrt((1 - pan) / 2) * 1.414
        buf[i:i + len(sig), 1] += sig * math.sqrt((1 + pan) / 2) * 1.414
    else:
        buf[i:i + len(sig)] += sig


def piano(m, held, vel=0.5):
    """One felt-piano note held for `held` s (key or pedal), then damped."""
    f0 = hz(m)
    ring = min(held + 0.35, 7.0)
    t = np.arange(ns(ring)) / SR
    B = 0.00018 * (f0 / 261.6) ** 0.5
    T1 = 0.5 * (261.6 / f0) ** 0.45
    T2 = 5.5 * (261.6 / f0) ** 0.55
    tilt = 1.95 - 0.9 * vel
    x = np.zeros(len(t))
    for n in range(1, 18):
        fn = n * f0 * math.sqrt(1 + B * n * n)
        if fn > 8000:
            break
        a = (1.0 / n ** tilt) * (0.3 + abs(math.sin(math.pi * n * 0.13)))
        env = 0.55 * np.exp(-t / (T1 / n ** 0.5)) + 0.45 * np.exp(-t / (T2 / n ** 0.7))
        det = fn * 0.0007 * (1 + 0.3 * float(rng.random()))
        ph = float(rng.random()) * 6.28
        x += a * env * (np.sin(2 * np.pi * fn * t + ph) * 0.5 + np.sin(2 * np.pi * (fn + det) * t + ph + 1.1) * 0.3
                        + np.sin(2 * np.pi * (fn - det * 0.8) * t + ph + 2.3) * 0.2)
    knock = band(rng.standard_normal(min(len(t), ns(0.03))), 200, 1600 + 2000 * vel)
    knock *= np.exp(-np.arange(len(knock)) / SR / 0.006) * 0.02 * vel   # a faint felt touch, not a click
    x[:len(knock)] += knock
    x *= np.minimum(t / 0.002, 1)
    damp = np.where(t < held, 1.0, np.exp(-(t - held) / 0.12))
    return x * damp * vel * 0.16


def strings(ms, sec, att=2.0, rel=2.2):
    n = ns(sec)
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    for k, m in enumerate(ms):
        for v in range(4):
            f = hz(m) * (1 + (v - 1.5) * 0.0016)
            vib = 1 + 0.0014 * np.sin(2 * np.pi * (4.6 + 0.3 * v) * t + float(rng.random()) * 6)
            ph = 2 * np.pi * np.cumsum(f * vib) / SR + float(rng.random()) * 6
            x = sum(np.sin(h * ph) / h ** 1.35 for h in range(1, 8))
            pan = -0.6 + 1.2 * ((k * 4 + v) / max(1, len(ms) * 4 - 1))
            out[:, 0] += x * math.sqrt((1 - pan) / 2)
            out[:, 1] += x * math.sqrt((1 + pan) / 2)
    env = np.minimum(t / att, 1) ** 1.5 * np.clip((sec - t) / rel, 0, 1) ** 1.2
    out *= env[:, None] / (len(ms) * 4)
    return np.stack([band(out[:, c], 150, 2400) for c in range(2)], 1)


def celesta(m, vel=0.5):
    t = np.arange(ns(2.2)) / SR
    f = hz(m)
    x = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / d) for r, a, d in ((1, 1, 1.0), (2.0, 0.22, 0.3), (4.0, 0.08, 0.12)))
    return x * np.minimum(t / 0.003, 1) * 0.11 * vel


def reverb(x, sec=3.0):
    ir = sa.hall_ir(SR, sec + 1.2, sec, 0.9, 0.024, seed=3)
    return sa.convolve(x, ir)


# ═════════════ score ═════════════
pf, st, ce = (np.zeros((N, 2)) for _ in range(3))
tk_bar, va_bar = bar_of(TK), bar_of(VA)
for bar in range(BARS):
    root, lh, sv = PROG[bar % 8]
    # the dynamic arc: hushed in the room, a little fuller while it flies, softer again as it fades into the sunset
    dyn = 0.44 if bar < 1 else 0.5 if bar < int(tk_bar) else 0.53 if bar < int(va_bar) else 0.48
    hold_end = at(bar + 1, 0.0) - 0.05
    t0 = at(bar, 0.0)
    put(pf, piano(root, hold_end - t0, dyn * 0.8), t0, 0.55, -0.35)
    for k, beat in enumerate((1.0, 2.0, 2.5, 3.0)):
        m = lh[k]
        tt = at(bar, beat)
        put(pf, piano(m, max(0.3, hold_end - tt), dyn * (0.7 if k % 2 else 0.8)), tt, 1.0, -0.2 + 0.08 * (m - 50) / 4)
    # strings: one long swell per two bars
    if bar % 2 == 0:
        g = 0.45 if bar < int(tk_bar) else 0.62 if bar < int(va_bar) else 0.5
        s0 = at(bar, 0.0)
        put(st, strings(sv, min(2 * BAR + 1.4, CARD_AT - s0 + 0.5)), s0, g)
# the tunes: while the paper is folded (from the first fold's bar) and while the crane flies
for start, tune in ((int(bar_of(F[0])), TUNE_A), (int(round(tk_bar)), TUNE_B)):
    for b_, beat, m, length, v in tune:
        bar = start + b_
        if bar >= BARS:
            continue
        put(pf, piano(m, length * BEAT, v), at(bar, beat), 1.0, 0.25)
# celesta on the two moments, on the next half beat
for when, notes in ((AW, (81, 86, 90)), (VA, (90, 86, 81))):
    b = math.ceil((when - T0) / (BEAT / 2) + 0.05)
    for k, m in enumerate(notes):
        put(ce, celesta(m, 0.6 - 0.1 * k), T0 + (b + k) * BEAT / 2, 1.0, 0.3 - 0.3 * k)
# the end card: a rolled Dadd9 ringing out under a soft string chord
card = np.zeros((N, 2))
root, notes = CARD_CH
put(card, piano(root, CARD + 0.3, 0.5), CARD_AT, 1.0, -0.3)
for k, m in enumerate(notes):
    put(card, piano(m, CARD + 0.3 - 0.06 * k, 0.42 + 0.02 * k), CARD_AT + 0.07 * k, 1.0, -0.4 + 0.1 * k)
put(card, strings([57, 62, 66, 69], CARD + 1.0, att=0.8, rel=1.4), CARD_AT, 0.5)

dry = pf + st * 0.9 + ce + card
music = dry + reverb(pf * 0.8 + st + ce + card) * 0.3

# ═════════════ SFX (very soft) + garden bed ═════════════
# (v5 review: "still loud and noisy": no paper crinkles, whoosh or breeze noise any more, only a few faint birds)
amb = np.zeros((N, 2))
for k, (t_, pan) in enumerate(((2.0, -0.7), (11.5, 0.6), (21.0, -0.5), (33.5, 0.7))):
    put(amb, band(sa.bird(SR, 90 + k), 1800, 4800), t_, 0.012, pan)
amb[ns(CARD_AT):] *= np.linspace(1, 0.3, N - ns(CARD_AT))[:, None]

mix = music + amb * db(-8)
for c in range(2):
    X = np.fft.rfft(mix[:, c])
    f = np.fft.rfftfreq(N, 1 / SR)
    m = 1 / (1 + (60 / np.maximum(f, 1)) ** 4)                  # high-pass 60 Hz
    m *= db(-5) + (1 - db(-5)) / (1 + (160 / np.maximum(f, 1)) ** 2)   # −5 dB low shelf: no boom
    m *= db(-4) + (1 - db(-4)) / (1 + (f / 7000) ** 2)          # ease off the top: nothing bright or harsh
    m /= 1 + (f / 14000) ** 6
    mix[:, c] = np.fft.irfft(X * m, N)
mix[:ns(0.25)] *= np.linspace(0, 1, ns(0.25))[:, None]
mix[-ns(0.3):] *= np.linspace(1, 0, ns(0.3))[:, None]

# ═════════════ master: −14 LUFS, true peak ≤ −1 dBTP ═════════════
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"


def write_wav24(path, x):
    a = np.round(np.clip(x, -1, 1) * 8388607).astype("<i4")
    with wave.open(path, "wb") as w_:
        w_.setnchannels(2)
        w_.setsampwidth(3)
        w_.setframerate(SR)
        w_.writeframes(a.view(np.uint8).reshape(-1, 4)[:, :3].tobytes())


def ebur128(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    summ = r[r.rindex("Summary:"):]
    return [float(re.search(pat, summ).group(1)) for pat in (r"I:\s*(-?[\d.]+) LUFS", r"Peak:\s*(-?[\d.]+) dBFS")]


def soft_limit(x, ceil):
    """Gentle peak control: a smooth knee above 0.7 × ceil (the mix is quiet and sparse, it rarely engages)."""
    k = 0.7 * ceil
    a = np.abs(x)
    over = a > k
    y = x.copy()
    y[over] = np.sign(x[over]) * (k + (ceil - k) * np.tanh((a[over] - k) / (ceil - k)))
    return y


LUFS = -16.0   # quieter than the usual −14 (v5 review: too loud)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
x = mix * 0.3 / max(1e-6, np.abs(mix).max())
for _ in range(4):
    write_wav24(OUT, x)
    I_, TP_ = ebur128(OUT)
    if abs(I_ - LUFS) < 0.1 and TP_ <= -1.0:
        break
    x = soft_limit(x * db(LUFS - I_), db(-1.3))
write_wav24(OUT, x)
I_, TP_ = ebur128(OUT)
json.dump({"bpm": round(60 / BEAT, 1), "bar_s": round(BAR, 4), "t0": T0, "bars": BARS, "card_at": CARD_AT,
           "lufs": I_, "true_peak": TP_}, open(OUT[:-4] + ".json", "w"), indent=1)
print(f"CALM {os.path.relpath(OUT, ROOT)}: {60 / BEAT:.1f} BPM, bar {BAR:.3f} s, {I_:.1f} LUFS, peak {TP_:.1f} dBFS")
