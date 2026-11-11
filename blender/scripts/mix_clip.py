# Audio for the Origami Crane X clip: a calm, cinematic piece on real sampled instruments (Steinway grand, string
# ensemble, solo flute, French horns from the Logic / GarageBand factory libraries of this Mac, read at mix time) + soft,
# natural SFX on the demo events. Mastered for X (−14 LUFS integrated, true peak ≤ −1 dBTP, 48 kHz stereo 24-bit).
#
#   Music: D major with a yo-pentatonic melody (D E G A B), 6/8, no drums or beat. The tempo map is derived from the beat
#     sheet events, so every cue lands on the picture whatever the measured times are:
#       pulse P = fitted fold period (one fold = one dotted quarter = 3 eighths; a 6/8 bar = 2 folds). Every fold is an
#         anchor of the map (folds 2, 4, … 14 on bar lines, fold14 = awaken = a downbeat), so the per-fold piano notes
#         sit on the folds even if they are unevenly spaced.
#       intro: round((bar 0 − 0.15) / 2P) bars before bar 0 (= one pulse before fold1, i.e. the end of the zoom),
#         squeezed to start ≥ 0.15 s, plus an optional two-eighth pickup when there is room before it.
#       awakening: awaken → takeoff = round(gap / 2P) bar(s) (≥ 1); flight: takeoff → vanish = round(gap / 1.7P)
#         bars (2..6, the flight runs a little faster); coda: vanish → app_end = round(gap / 2P) bar(s); card: 1 bar.
#       Inside each section the eighths are spread evenly, so the events can move by a second or more: the section
#         bar counts change and the phrases are picked to fit (see FLIGHT_SETS / pre_plan()).
#     Opening (zoom into the sheet): solo piano motif "D E A | G E D | E D B A | B…" over a ppp string pad.
#     Folding: the motif continues, piano broken-chord arpeggios (I – ii – IV – Vsus | I6 – vi – IV/ii – Vsus–V), the
#       strings build voice by voice; a very soft high piano note on every fold (chord tone, climbing).
#     Awakening: lift to C (bVII) – D (bVII of the new key) with a high piano "celesta" sweep and a string swell, a flute
#       pickup into the take-off. Flight: E major tutti, the flute carries the motif (violins an octave below, horns,
#       piano arpeggios, cellos/basses), climbing to E6 on the vanish. Vanish: everything resolves on E, the piano
#       echoes the motif up high; the end card = a rolled Eadd9 whose notes follow the title letters, ringing out.
#   SFX (times from the beat sheet "events", app seconds): per fold a soft paper slide + a natural crease (smooth grain
#     crinkle, muffled pat, finger slide; no clicks), a gentle airy whoosh on take-off and a fainter one on the climb, a
#     soft shimmer of light on the vanish, a very low garden bed (breeze, a few distant birds).
#   Times are app seconds (t = 0 = demo clock start); promo.sh trims the first app_start seconds to match the picture.
#
#   /Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 blender/scripts/mix_clip.py \
#       --beats blender/scripts/beats/v4.json [--out render/audio/mix_v4.wav]
# Writes the WAV named by the beat sheet "audio" (default) + a .json next to it with the tempo map, measured loudness and
# harshness figures (spectral centroid, energy above 6 kHz, peaks).
import json, math, os, re, shutil, subprocess, sys, wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synth_audio as sa  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
arg = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
ROOT = sa.ROOT
BEATS_PATH = os.path.join(ROOT, arg("--beats", "blender/scripts/beats/v4.json"))
BEATS = json.load(open(BEATS_PATH))
OUT = os.path.join(ROOT, arg("--out", BEATS.get("audio", "render/audio/mix_v4.wav")))
EV = BEATS["events"]
MUS = BEATS.get("music", {})
SR = 48000
CARD_AT = float(BEATS["app_end"])
CARD = float(BEATS.get("card", 3.0))
DUR = CARD_AT + CARD + 0.4
N = int(DUR * SR)
rng = np.random.default_rng(7)
db = lambda x: 10 ** (x / 20)
ns = lambda sec: int(round(sec * SR))
tm = np.arange(N) / SR
hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)
band = lambda x, lo, hi: sa.band(x, lo, hi, SR)

# ═════════════ 0. TEMPO MAP (from the events) ═════════════
F = [float(x) for x in EV["folds"]]
P = float(np.polyfit(np.arange(len(F)), F, 1)[0]) if len(F) >= 3 else 1.4
P = min(max(P, 0.9), 2.0)
AW = float(EV.get("awaken", F[-1]))
TK = float(EV.get("takeoff", AW + 2.4))
VA = float(EV.get("vanish", CARD_AT - 2.4))
CLIMB = EV.get("climb")
NFB = (len(F) + 1) // 2                   # folding bars (two folds per 6/8 bar, the last fold = the awakening downbeat)
gA = 6 * NFB                              # global eighth index of the awakening (bar 0 = g 0)
anch = {gA: AW}
lag = max(0, round((AW - F[-1]) / P))
FOLD_G = []
for i, f in enumerate(reversed(F)):
    g = gA - 3 * (i + lag)
    FOLD_G.append(g)
    if g != gA and f < AW - 0.2 and f < min(anch.values()) - 0.2:
        anch[g] = f
FOLD_G = FOLD_G[::-1]
g_first = min(anch)
if 0 not in anch:
    anch[0] = anch[g_first] - g_first * P / 3
BAR0 = anch[0]
N_INTRO = max(0, round((BAR0 - 0.15) / (2 * P)))
if N_INTRO:
    anch[-6 * N_INTRO] = max(0.15, BAR0 - 2 * P * N_INTRO)
nA = max(1, round((TK - AW) / (2 * P)))
gT = gA + 6 * nA
nF = int(np.clip(round((VA - TK) / (1.7 * P)), 2, 6))
gV = gT + 6 * nF
nC = max(1, round((CARD_AT - VA) / (2 * P)))
gE = gV + 6 * nC
anch.update({gT: TK, gV: VA, gE: CARD_AT, gE + 6: CARD_AT + CARD})
GK = np.array(sorted(anch), float)
GT = np.array([anch[g] for g in sorted(anch)])
assert np.all(np.diff(GT) > 0.05), f"tempo map not monotonic: {list(zip(GK, GT))}"


def T(g):
    """Global eighth index → app second (linear between anchors, extrapolated at both ends)."""
    if g <= GK[0]:
        return float(GT[0] - (GK[0] - g) * (GT[1] - GT[0]) / (GK[1] - GK[0]))
    if g >= GK[-1]:
        return float(GT[-1] + (g - GK[-1]) * (GT[-1] - GT[-2]) / (GK[-1] - GK[-2]))
    return float(np.interp(g, GK, GT))


q_bpm = lambda t0, t1, eighths: 60 / ((t1 - t0) / eighths * 2)
SECTIONS = {
    "intro": (T(-6 * N_INTRO), BAR0), "folding": (BAR0, AW), "awakening": (AW, TK), "flight": (TK, VA),
    "coda": (VA, CARD_AT), "card": (CARD_AT, CARD_AT + CARD)}
print(f"MIX tempo map: fold pulse {P:.3f}s → 6/8, eighth {P / 3:.3f}s (quarter {60 / (2 * P / 3):.1f} BPM) | intro {N_INTRO} "
      f"bar(s) from {T(-6 * N_INTRO):.2f}s, bar 0 {BAR0:.2f}s, folding {NFB} bars, awaken {AW:.2f}s ({nA} bar, ♩ "
      f"{q_bpm(AW, TK, 6 * nA):.0f}), flight {TK:.2f}s ({nF} bars, ♩ {q_bpm(TK, VA, 6 * nF):.0f}), vanish {VA:.2f}s "
      f"({nC} bar, ♩ {q_bpm(VA, CARD_AT, 6 * nC):.0f}), card {CARD_AT:.2f}s")

# ═════════════ 1. SCORE ═════════════
# piano broken chords (one 6/8 bar = 6 eighths; a half-bar chord uses notes 0, 1, 3) and string voicings (bass, tenor,
# alto, soprano). D major for the opening and the folds, C – D (bVII of E) on the awakening, E major for the flight.
ARP = {
    "D": [50, 57, 64, 66, 64, 57], "Em7": [52, 59, 62, 67, 62, 59], "Gmaj7": [43, 50, 57, 59, 66, 59],
    "Asus4": [45, 52, 57, 62, 64, 62], "A": [45, 52, 57, 61, 64, 61], "D/F#": [42, 50, 57, 62, 64, 57],
    "Bm7": [47, 54, 57, 62, 66, 62], "C": [48, 55, 62, 64, 67, 64], "Dw": [50, 57, 62, 66, 69, 66],
    "E": [52, 59, 66, 68, 66, 59], "F#m7": [54, 61, 64, 69, 64, 61], "C#m7": [49, 56, 59, 64, 68, 64],
    "G#m7": [44, 51, 59, 63, 66, 63], "Amaj7": [45, 52, 59, 61, 68, 61], "Bsus4": [47, 54, 59, 64, 66, 64],
    "B": [47, 54, 59, 63, 66, 63]}
STR = {
    "D": [38, 57, 66, 74], "Em7": [40, 59, 67, 74], "Gmaj7": [43, 59, 66, 74], "Asus4": [45, 57, 64, 74],
    "A": [45, 57, 64, 73], "D/F#": [42, 57, 66, 74], "Bm7": [47, 57, 66, 74], "C": [36, 55, 64, 74],
    "Dw": [38, 57, 66, 74], "E": [40, 59, 68, 76], "F#m7": [42, 57, 64, 73], "C#m7": [37, 56, 64, 71],
    "G#m7": [44, 59, 63, 71], "Amaj7": [45, 56, 64, 73], "Bsus4": [47, 59, 64, 71], "B": [47, 59, 63, 71]}
YO = {2, 4, 7, 9, 11}                     # D yo pentatonic pitch classes (D E G A B)

# opening + folding: 8 bars (chords, piano melody as (eighth, length, MIDI)); the motif D E A | G E D | E D B A | B
PRE = [
    ([(0, "D")], [(0, 2, 74), (2, 1, 76), (3, 3, 81)]),
    ([(0, "Em7")], [(0, 2, 79), (2, 1, 76), (3, 3, 74)]),
    ([(0, "Gmaj7")], [(0, 2, 76), (2, 1, 74), (3, 2, 71), (5, 1, 69)]),
    ([(0, "Asus4")], [(0, 4, 71), (4, 1, 69), (5, 1, 71)]),
    ([(0, "D/F#")], [(0, 2, 74), (2, 1, 76), (3, 3, 81)]),
    ([(0, "Bm7")], [(0, 2, 83), (2, 1, 81), (3, 3, 78)]),
    ([(0, "Gmaj7"), (3, "Em7")], [(0, 2, 76), (2, 1, 79), (3, 2, 83), (5, 1, 81)]),
    ([(0, "Asus4"), (3, "A")], [(0, 3, 81), (3, 1, 83), (4, 1, 85), (5, 1, 86)]),
]
PICKUP = [(-2, 1, 69), (-1, 1, 71)]


def pre_plan(n):
    """The 8 opening/folding bars fitted to n bars: extra bars in front = held D bars, fewer = drop from the middle
    (the last bar, the build into the awakening, always stays)."""
    if n >= len(PRE):
        return [([(0, "D")], [])] * (n - len(PRE)) + PRE
    return PRE[:max(0, n - 1)] + PRE[-1:]


# flight (E major): the motif on the flute, a step higher, climbing to E6 on the vanish; bars picked by count
FL = {
    "F1": ([(0, "E")], [(0, 2, 76), (2, 1, 78), (3, 3, 83)]),
    "F2": ([(0, "F#m7")], [(0, 2, 81), (2, 1, 78), (3, 3, 76)]),
    "F2b": ([(0, "C#m7")], [(0, 2, 80), (2, 1, 78), (3, 3, 76)]),
    "F2c": ([(0, "G#m7")], [(0, 2, 83), (2, 1, 80), (3, 3, 78)]),
    "F3": ([(0, "Amaj7")], [(0, 2, 85), (2, 1, 83), (3, 2, 81), (5, 1, 80)]),
    "F4": ([(0, "Bsus4"), (3, "B")], [(0, 2, 83), (2, 1, 81), (3, 1, 83), (4, 1, 85), (5, 1, 87)]),
}
FLIGHT_SETS = {2: ["F1", "F4"], 3: ["F1", "F3", "F4"], 4: ["F1", "F2", "F3", "F4"], 5: ["F1", "F2", "F2b", "F3", "F4"],
               6: ["F1", "F2", "F2b", "F2c", "F3", "F4"]}

# bars: (global bar index, section, [(eighth, chord)], melody)
BARS = []
for i, (ch, mel) in enumerate(pre_plan(N_INTRO + NFB)):
    BARS.append((i - N_INTRO, "intro" if i < N_INTRO else "folding", ch, mel))
for k in range(nA):
    BARS.append((NFB + k, "awakening", [(0, "C")] if k < nA - 1 else ([(0, "C"), (4, "Dw")] if nA == 1 else
                                                                         [(0, "C"), (3, "Dw")]), []))
for k, name in enumerate(FLIGHT_SETS[nF]):
    BARS.append((gT // 6 + k, "flight", *FL[name]))
for k in range(nC):
    BARS.append((gV // 6 + k, "coda", [(0, "E")], []))
BARS.append((gE // 6, "card", [(0, "E")], []))
SEGS = []                                  # chord segments (g0, g1, chord, section) = the pedal changes
for b, sec, ch, _ in BARS:
    for j, (e, c) in enumerate(ch):
        e1 = ch[j + 1][0] if j + 1 < len(ch) else 6
        SEGS.append((6 * b + e, 6 * b + e1, c, sec))
PEDAL = [s[0] for s in SEGS] + [SEGS[-1][1]]
seg_at = lambda g: next((s for s in SEGS if s[0] <= g < s[1]), SEGS[-1])
pedal_after = lambda g: next((p for p in PEDAL if p >= g - 1e-6), PEDAL[-1])
PRE_I = {b: i for i, (b, sec, _, _) in enumerate(BARS) if sec in ("intro", "folding")}   # bar → index in the opening

# ═════════════ 2. INSTRUMENTS ═════════════
PIANO = sa.load_piano(SR)
STR_SOFT, STR_LOUD = sa.load_strings(SR), sa.load_strings(SR, loud=True)
FLUTE, HORNS = sa.load_flute(SR), sa.load_horns(SR)
print(f"MIX samples: piano {len(PIANO.zones)} zones (soft layer, measured {', '.join(f'{c:+.0f}' for c in PIANO.checked)} "
      f"cents on A3/C4/A4 → tune {PIANO.tune:+.1f}), strings {len(STR_SOFT.zones)}+{len(STR_LOUD.zones)}, flute "
      f"{len(FLUTE.zones)}, horns {len(HORNS.zones)}")


class Bus:
    def __init__(self):
        self.x = np.zeros((N, 2))

    def put(self, sig, at, gain=1.0, pan=0.0):
        i = ns(at)
        if i >= N or i + len(sig) <= 0:
            return
        s = sig * gain
        if i < 0:
            s, i = s[-i:], 0
        s = s[:N - i]
        if s.ndim == 1:
            s = np.stack([s * math.sqrt((1 - pan) / 2) * 1.414, s * math.sqrt((1 + pan) / 2) * 1.414], 1)
        else:                                          # stereo sample: balance
            s = s * np.array([min(1.0, 1 - pan), min(1.0, 1 + pan)])
        self.x[i:i + len(s)] += s


piano, strings, flute, horns = Bus(), Bus(), Bus(), Bus()


def pn(t, m, vel, t_off, rel=0.45, pan=0.0, gain=1.0):
    """One piano note (soft-layer sample): loudness ∝ vel^1.6, softer = darker."""
    t = max(t, 0.02)
    lp = None if vel > 0.85 else 2200 + 9000 * vel ** 2
    piano.put(PIANO.note(m, max(0.05, t_off - t), rel, lp=lp), t, gain * vel ** 1.6, pan)


# piano: melody, arpeggios, bass
for b, sec, ch, mel in BARS:
    g0 = 6 * b
    pi = PRE_I.get(b)
    grow = 0 if pi is None else pi / max(1, len(PRE_I) - 1)     # 0 → 1 over the opening + folding
    notes = (PICKUP if pi == 0 and MUS.get("pickup", True) else []) + mel
    if sec in ("intro", "folding"):
        for e, l, m in notes:
            t_on = T(g0 + e)
            if t_on < -0.01:
                continue
            vel = (0.62 + 0.12 * grow) * (1.0 if e in (0, 3) else 0.88)
            pn(t_on, m, vel, T(pedal_after(g0 + e + l)) + 0.12, pan=0.1)
    for j, (e, c) in enumerate(ch):
        e1 = ch[j + 1][0] if j + 1 < len(ch) else 6
        arp = ARP[c]
        pat = arp if e1 - e == 6 else [arp[0], arp[1], arp[3], arp[4], arp[5], arp[2]][:e1 - e]
        t_off = T(g0 + e1) + 0.15
        if sec == "intro":                              # opening: just an open fifth under the motif
            for m in (arp[0] - 12, arp[0], arp[1]):
                pn(T(g0 + e), m, 0.42, t_off, pan=-0.15)
            continue
        if sec in ("folding", "flight"):
            amp = (0.4 + 0.1 * grow) if sec == "folding" else 0.5
            for k, m in enumerate(pat):
                acc = 1.12 if k == 0 else 1.04 if k == 3 else 0.92
                pn(T(g0 + e + k), m, amp * acc, t_off, pan=-0.25 + 0.1 * (k % 3))
            if sec == "flight" or grow > 0.2:
                pn(T(g0 + e), arp[0] - 12, 0.4 if sec == "folding" else 0.48, t_off, pan=-0.2)

# per fold: a very soft high piano note (a chord tone of the yo scale, climbing over the 14 folds)
for k, g in enumerate(FOLD_G[:-1]):
    c = seg_at(g)[2]
    pcs = {m % 12 for m in ARP[c] + STR[c]} & YO
    target = 86 + 12 * k / max(1, len(FOLD_G) - 2)
    cand = [m for m in range(84, 101) if m % 12 in pcs]
    m = min(cand, key=lambda x: abs(x - target)) if cand else 86
    pn(T(g), m, 0.26, T(g) + 1.2, rel=1.0, pan=0.45 if k % 2 else -0.4)

# awakening: deep C + E6 bloom, a soft "celesta" sweep up C lydian, then D and a second sweep into the take-off
ga_bars = [x for x in BARS if x[1] == "awakening"]
for b, sec, ch, _ in ga_bars:
    for j, (e, c) in enumerate(ch):
        g = 6 * b + e
        e1 = ch[j + 1][0] if j + 1 < len(ch) else 6
        t_off = T(6 * b + e1) + 0.2
        low = [36, 48, 55, 64] if c == "C" else [38, 50, 57, 66]
        for k, m in enumerate(low):
            pn(T(g) + 0.03 * k, m, 0.5, t_off, pan=-0.2)
        if c == "C" and b == NFB:
            pn(T(g), 88, 0.72, t_off + 0.6, pan=0.15)
            pn(T(g), 76, 0.55, t_off + 0.6, pan=0.1)
        sweep = [79, 84, 86, 88, 91, 93, 95] if c == "C" else [81, 86, 90, 93]
        span = (e1 - e) * 0.85
        for k, m in enumerate(sweep):
            pn(T(g + 0.5 + span * k / len(sweep)), m, 0.34 + 0.02 * k, T(6 * b + e1) + 0.8, rel=1.2,
               pan=-0.5 + k / len(sweep))
# coda (vanish): a rolled low E chord, then the motif echoed high and soft ("music box"), over the held strings
for k, m in enumerate([28, 40, 47, 56, 59, 64, 68]):
    pn(VA + 0.035 * k, m, 0.58 - 0.02 * k, CARD_AT + 0.3, rel=1.2, pan=-0.3 + 0.1 * k)
for e, m in ((2, 88), (4, 90), (5, 95)):
    pn(T(gV + e), m, 0.42, CARD_AT + 0.6, rel=1.5, pan=0.3)
# end card: a rolled Eadd9 whose notes follow the title letters (promo.py fades letter k in at card + title_in + k·step)
title = BEATS.get("title", "Origami Crane")
letters = [i for i, ch_ in enumerate(title) if ch_ != " "]
ti, ts = float(BEATS.get("title_in", 0.1)), float(BEATS.get("title_step", 0.045))
ROLL = [40, 47, 52, 56, 59, 64, 66, 68, 71, 76, 78, 80, 83, 88, 90, 92, 95]
pn(CARD_AT, 28, 0.5, DUR, rel=0.5, pan=-0.2)
for k, _ in enumerate(letters):
    m = ROLL[min(k, len(ROLL) - 1)]
    pn(CARD_AT + ti + k * ts, m, 0.55 - 0.18 * k / max(1, len(letters) - 1), DUR, rel=0.5,
       pan=-0.45 + 0.9 * k / max(1, len(letters) - 1))


# strings: voices led from chord to chord (same pitch = tied), slow bowed attack, long release; layer by intensity
def str_curve(t):
    pts = [(0, 0.0), (0.35, 0.2), (BAR0, 0.26), ((BAR0 + AW) / 2, 0.36), (AW - 2 * P, 0.48), (AW, 0.6),
           (AW + 0.8 * (TK - AW), 0.85), (TK, 0.78), (VA - 0.6, 1.0), (VA + 0.3, 1.0), (CARD_AT, 0.62),
           (CARD_AT + CARD, 0.42), (DUR, 0.3)]
    return np.interp(t, [p[0] for p in pts], [p[1] for p in pts])


def voices_for(sec, b):
    pi = PRE_I.get(b, 99)
    if sec == "intro":
        return (0, 1)
    if sec == "folding":
        return (0, 1, 2) if pi < len(PRE_I) - 4 else (0, 1, 2, 3)
    if sec == "flight":
        return (0, 1, 2)
    if sec == "card":
        return (0, 1, 2)
    return (0, 1, 2, 3)


tracks = {v: [] for v in range(4)}
for g0, g1, c, sec in SEGS:
    for v in voices_for(sec, g0 // 6):
        m = STR[c][v]
        tr = tracks[v]
        if tr and tr[-1][2] == m and abs(tr[-1][1] - g0) < 1e-6:
            tr[-1][1] = g1
        else:
            tr.append([g0, g1, m])
lines = []                                   # (t_on, t_off, midi, attack, release, gain, pan)
PAN_V = [-0.35, -0.1, 0.15, 0.35]
for v, tr in tracks.items():
    for g0, g1, m in tr:
        t_on = max(0.03, T(g0) - 0.08)
        t_off = T(g1) + 0.12
        if g1 >= gE + 6:
            t_off = CARD_AT + CARD - 0.9
        lines.append((t_on, t_off, m, 1.4 if g0 <= -6 * N_INTRO else 0.55, 1.3, [0.85, 0.8, 0.7, 0.55][v], PAN_V[v]))
# high violins: the awakening (G5 → F#5) and the vanish (B5)
for b, sec, ch, _ in ga_bars:
    for j, (e, c) in enumerate(ch):
        e1 = ch[j + 1][0] if j + 1 < len(ch) else 6
        lines.append((T(6 * b + e), T(6 * b + e1) + 0.1, 79 if c == "C" else 78, 0.5, 0.8, 0.4, 0.3))
lines.append((VA - 0.05, CARD_AT + 0.6, 83, 0.35, 1.6, 0.38, 0.3))
# violins double the flute melody an octave lower in the flight
FLUTE_NOTES = []                             # (g, length, MIDI, slurred)
fl_bars = [x for x in BARS if x[1] == "flight"]
FLUTE_NOTES += [(gT - 2, 1, 71, False), (gT - 1, 1, 73, True)]
for b, sec, ch, mel in fl_bars:
    for e, l, m in mel:
        FLUTE_NOTES.append((6 * b + e, l, m, True))
FLUTE_NOTES.append((gV, 3, 88, True))
for g, l, m, _ in FLUTE_NOTES[2:-1]:
    lines.append((T(g), T(g + l) + 0.06, m - 12, 0.12, 0.35, 0.42, 0.2))
for t_on, t_off, m, att, rel, gain, pan in lines:
    lvl = float(str_curve(t_on))
    w = float(np.clip((lvl - 0.62) / 0.38, 0, 1)) * 0.7
    y = STR_SOFT.note(m, t_off - t_on, rel, att=att) * (1 - w)
    if w > 0:
        y += STR_LOUD.note(m, t_off - t_on, rel, att=att) * w
    strings.put(y, t_on, gain, pan)
strings.x *= str_curve(tm)[:, None]

# flute: legato phrase (slurred notes start past the sample's attack), a swell on the long notes, the climax E6
for k, (g, l, m, slur) in enumerate(FLUTE_NOTES):
    t_on, t_end = T(g), T(g + l)
    last = k == len(FLUTE_NOTES) - 1
    rel = 1.1 if last else 0.12
    y = FLUTE.note(m, t_end - t_on + (0.0 if last else 0.07), rel, att=0.04 if slur and k else 0.09,
                   offset=0.12 if slur and k else 0.0)
    if l >= 2:
        y *= (1 + 0.18 * np.sin(np.pi * np.arange(len(y)) / len(y)))[:, None]
    frac = (g - (gT - 2)) / max(1, gV - (gT - 2))
    flute.put(y, t_on, 0.62 + 0.38 * frac, 0.12)

# horns: soft warm chord pad (tenor + alto of the string voicing) from the second flight bar through the vanish
for g0, g1, c, sec in SEGS:
    if (sec == "flight" and g0 >= gT + 6) or sec == "coda":
        for v, gain in ((1, 0.7), (2, 0.55)):
            m = STR[c][v]
            m += 12 if m < 50 else 0
            t_on, t_off = T(g0), (T(g1) + 0.15 if sec == "flight" else CARD_AT + 0.4)
            horns.put(HORNS.note(m, t_off - t_on, 1.0, att=0.45), t_on, gain, -0.3)

# ═════════════ 3. MUSIC BUS: balance, room, EQ ═════════════
G_PIANO, G_STR, G_FL, G_HN = 0.5, 0.48, 0.45, 0.22
dry = piano.x * G_PIANO + strings.x * G_STR + flute.x * G_FL + horns.x * G_HN
send = piano.x * G_PIANO * 0.32 + strings.x * G_STR * 0.42 + flute.x * G_FL * 0.36 + horns.x * G_HN * 0.45
wet = sa.convolve(send, sa.hall_ir(SR, 4.2, 2.9, 0.9, 0.024, seed=3))
G_WET = min(1.0, db(-7.5) * np.sqrt((dry ** 2).mean() / ((wet ** 2).mean() + 1e-20)))   # tail ≈ 7.5 dB under the dry mix
wet *= G_WET
music = dry + wet


def tone(x):
    """Gentle mastering EQ per channel: high-pass 38 Hz, −1.5 dB at 300 Hz (less mud), +1.5 dB around 3 kHz (piano and
    flute stay clear on phone speakers), a soft high shelf easing off above 6 kHz (−4 dB from 10 kHz) and a 15 kHz
    low-pass (no air hiss, nothing harsh)."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    m = 1 / (1 + (38 / np.maximum(f, 1)) ** 4)
    m *= 1 + (db(-1.5) - 1) / (1 + ((f - 300) / 150) ** 2)
    m *= 1 + (db(1.5) - 1) / (1 + ((f - 3000) / 1500) ** 2)
    m *= db(-4) + (1 - db(-4)) / (1 + (f / 7500) ** 2)
    m /= 1 + (f / 15000) ** 6
    return np.fft.irfft(X * m, len(x))


music = np.stack([tone(music[:, c]) for c in range(2)], 1)
mid_, side_ = (music[:, 0] + music[:, 1]) / 2, (music[:, 0] - music[:, 1]) / 2 * 0.75   # a little narrower: holds up in mono
music = np.stack([mid_ + side_, mid_ - side_], 1)

# ═════════════ 4. SOUND EFFECTS ═════════════
fx = Bus()
for k, t_ in enumerate(F):
    p = 1.0 + 0.07 * math.sin(k * 1.9)
    pan = 0.22 * math.sin(k * 1.7)
    fx.put(sa.paper_slide(SR, 300 + k, 0.42), t_ - 0.44, 0.32, pan)
    fx.put(sa.paper_crease(SR, 400 + k, p), t_ - 0.01, 0.5, pan)
fx.put(sa.air_whoosh(SR, 23, 1.4, 180, 1500, 0.42), TK - 0.45, 0.42, -0.2)
if CLIMB is not None:
    fx.put(sa.air_whoosh(SR, 24, 1.8, 150, 1200, 0.5), float(CLIMB) - 0.7, 0.26, 0.25)
fx.put(sa.light_shimmer(SR, 29, [hz(88), hz(92), hz(95), hz(100)], 3.4), VA - 0.15, 0.2, 0.0)
fx.x = fx.x + sa.convolve(fx.x, sa.hall_ir(SR, 1.6, 0.9, 0.4, 0.012, seed=9)) * 0.22

amb = Bus()
br = band(rng.standard_normal(N), 120, 900)
br2 = band(rng.standard_normal(N), 120, 900)
sway = 0.006 * (1 + 0.4 * np.sin(2 * np.pi * 0.09 * tm) + 0.2 * np.sin(2 * np.pi * 0.23 * tm + 1))
amb.x[:, 0] += br / (br.std() + 1e-9) * sway
amb.x[:, 1] += br2 / (br2.std() + 1e-9) * sway
for k, (t_, pan) in enumerate(((1.3, -0.7), (8.6, 0.6), (17.9, -0.5), (30.5, 0.7))):
    if t_ < CARD_AT:
        amb.put(band(sa.bird(SR, 90 + k), 1800, 5000), t_, 0.016, pan)
amb.x[ns(CARD_AT):] *= np.linspace(1, 0.3, N - ns(CARD_AT))[:, None]

# ═════════════ 5. MIX + MASTER ═════════════
G_FX, G_AMB = db(-6), db(-4)
mix = music + fx.x * G_FX + amb.x * G_AMB
rms_db = lambda x: 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-12)
_st = lambda x: f"peak {20 * np.log10(np.abs(x).max() + 1e-9):6.1f} rms {rms_db(x):6.1f}"
print(f"MIX stems (dB, before master): music {_st(music)} | fx {_st(fx.x * G_FX)} | amb {_st(amb.x * G_AMB)}")
for nm, b_ in (("piano", piano.x * G_PIANO), ("strings", strings.x * G_STR), ("flute", flute.x * G_FL),
               ("horns", horns.x * G_HN), ("reverb", wet)):
    print(f"MIX   {nm:7s} {_st(b_)}  | per section rms: " + " ".join(
        f"{k} {rms_db(b_[ns(a_):ns(e_)]):5.1f}" for k, (a_, e_) in SECTIONS.items()))
# SFX under the music: crease windows vs the music around them
win = [(ns(t_ - 0.45), ns(t_ + 0.25)) for t_ in F]
r_fx = np.mean([rms_db(fx.x[a:b] * G_FX) for a, b in win])
r_mu = np.mean([rms_db(music[a:b]) for a, b in win])
print(f"MIX   folds: SFX {r_fx:.1f} dB vs music {r_mu:.1f} dB in the same windows ({r_fx - r_mu:+.1f} dB)")
mix[:, 0] = band(mix[:, 0], 35, None)
mix[:, 1] = band(mix[:, 1], 35, None)
mix[-ns(0.3):] *= np.linspace(1, 0, ns(0.3))[:, None]
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
LUFS, TP = -14.3, -1.0   # linear loudnorm lands ~0.3 LU above target → −14.3 so ebur128 reads −14.0


def write_wav24(path, x):
    a = np.round(np.clip(x, -1, 1) * 8388607).astype("<i4")
    with wave.open(path, "wb") as w_:
        w_.setnchannels(2)
        w_.setsampwidth(3)
        w_.setframerate(SR)
        w_.writeframes(a.view(np.uint8).reshape(-1, 4)[:, :3].tobytes())


def os_peaks(x, k=4):
    p = np.zeros(len(x))
    for c in range(2):
        y = np.fft.irfft(np.fft.rfft(x[:, c]), k * len(x)) * k
        p = np.maximum(p, np.abs(y).reshape(-1, k).max(1))
    return p


def limiter(x, ceil_db, look=0.002, rel=0.08):
    """Look-ahead true-peak-ish limiter (4x oversampled peaks), block release."""
    g = np.minimum(1, db(ceil_db) / np.maximum(os_peaks(x), 1e-9))
    w = ns(look)
    gm = np.lib.stride_tricks.sliding_window_view(np.concatenate([np.ones(w), g, np.ones(w)]), 2 * w + 1).min(1)
    h = w // 2
    box = np.convolve(np.concatenate([np.ones(h), gm, np.ones(h)]), np.ones(2 * h + 1) / (2 * h + 1), "valid")
    B = 48
    nb_ = len(gm) // B
    blk = gm[:nb_ * B].reshape(nb_, B).min(1)
    kr = 1 - math.exp(-B / SR / rel)
    y, out = 1.0, np.empty(nb_)
    for i, v in enumerate(blk):
        y = min(v, y + (1 - y) * kr)
        out[i] = y
    rc = np.interp(np.arange(len(gm)), np.arange(nb_) * B, out)
    gg = np.minimum(box, rc)
    return x * gg[:, None], 20 * np.log10(gg.min())


def loudnorm_measure(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-af",
                        f"loudnorm=I={LUFS}:TP={TP}:LRA=20:print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    return json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])


def harshness(x, sr, t0=0.0, t1=None):
    """Power spectrum (Welch, 8192-point Hann) of the mono sum between t0 and t1: spectral centroid (Hz), share of the
    energy above 6 kHz (dB re total) and the worst 0.5 s window for that share."""
    m = x.mean(1)[int(t0 * sr):int((t1 or len(x) / sr) * sr)]
    nfft, hop = 8192, 4096
    fr = np.lib.stride_tricks.sliding_window_view(m, nfft)[::hop] * np.hanning(nfft)
    S = np.abs(np.fft.rfft(fr, axis=1)) ** 2
    f = np.fft.rfftfreq(nfft, 1 / sr)
    Pm = S.mean(0)
    hi = f > 6000
    e_fr = S.sum(1)
    loud = e_fr > e_fr.max() * 1e-3                    # ignore near-silent frames for the worst-window figure
    share = S[:, hi].sum(1) / np.maximum(e_fr, 1e-20)
    k = max(1, int(0.5 * sr / hop))
    worst = max((share[i:i + k].mean() for i in range(0, len(share) - k + 1) if loud[i:i + k].all()), default=0.0)
    return dict(centroid_hz=round(float((f * Pm).sum() / Pm.sum())), above_6k_db=round(10 * math.log10(Pm[hi].sum() / Pm.sum()), 1),
                worst_05s_above_6k_db=round(10 * math.log10(max(worst, 1e-12)), 1))


os.makedirs(os.path.dirname(OUT), exist_ok=True)
PRE_W = OUT[:-4] + "_premaster.wav"
base = mix * 0.5 / max(1e-6, np.abs(mix).max())
write_wav24(PRE_W, base)
m1 = loudnorm_measure(PRE_W)
x = base * db(LUFS - float(m1["input_i"]))
x, gr = limiter(x, TP - 0.6)
write_wav24(PRE_W, x)
m2 = loudnorm_measure(PRE_W)
subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", PRE_W, "-af",
                f"loudnorm=I={LUFS}:TP={TP}:LRA=20:measured_I={m2['input_i']}:measured_TP={m2['input_tp']}:"
                f"measured_LRA={m2['input_lra']}:measured_thresh={m2['input_thresh']}:offset={m2['target_offset']}:linear=true:"
                f"print_format=summary", "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s24le", OUT], check=True)
os.remove(PRE_W)


def ebur128(path):
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    summ = r[r.rindex("Summary:"):]
    return [float(re.search(pat, summ).group(1)) for pat in
            (r"I:\s*(-?[\d.]+) LUFS", r"LRA:\s*(-?[\d.]+) LU", r"Peak:\s*(-?[\d.]+) dBFS")]


I_, LRA_, TP_ = ebur128(OUT)
y, _, _, _ = sa.read_wav(OUT)
trim_db = min(-14.0 - I_, -1.05 - TP_)              # loudnorm lands within ~0.3 LU: trim to −14.0 if the peak allows
if abs(trim_db) >= 0.05:
    y = y * db(trim_db)
    write_wav24(OUT, y)
    I_, LRA_, TP_ = ebur128(OUT)
clip_n = int((np.abs(y) >= 0.999).sum())
harsh = {"all": harshness(y, SR)}
for nm, (a_, b_) in SECTIONS.items():
    if b_ - a_ > 0.6:
        harsh[nm] = harshness(y, SR, a_, b_)
crest = round(20 * math.log10(np.abs(y).max() / (np.sqrt((y ** 2).mean()) + 1e-12)), 1)
json.dump({"tempo": {"fold_pulse_s": round(P, 4), "eighth_s": round(P / 3, 4), "quarter_bpm_folding": round(60 / (2 * P / 3), 1),
                     "quarter_bpm_flight": round(q_bpm(TK, VA, 6 * nF), 1), "intro_bars": N_INTRO, "folding_bars": NFB,
                     "awakening_bars": nA, "flight_bars": nF, "coda_bars": nC,
                     "anchors": [[int(g), round(float(t), 3)] for g, t in zip(GK, GT)]},
           "sections": {k: [round(a_, 3), round(b_, 3)] for k, (a_, b_) in SECTIONS.items()},
           "card_at": CARD_AT, "dur": round(DUR, 3), "limiter_gr_db": round(-gr, 2), "lufs": I_, "lra": LRA_,
           "true_peak": TP_, "clipped_samples": clip_n, "crest_db": crest, "harshness": harsh},
          open(OUT[:-4] + ".json", "w"), indent=1)
print(f"MIX harshness: centroid {harsh['all']['centroid_hz']} Hz, energy >6 kHz {harsh['all']['above_6k_db']} dB "
      f"(worst 0.5 s {harsh['all']['worst_05s_above_6k_db']} dB), clipped samples {clip_n}, crest {crest} dB")
print(f"MIX limiter GR {-gr:.1f} dB | AUDIO {os.path.relpath(OUT, ROOT)} {DUR:.1f}s | I {I_:.1f} LUFS, LRA {LRA_:.1f} LU, "
      f"true peak {TP_:.1f} dBTP")
