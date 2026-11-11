# Promo clip + audio

How to turn a simulator recording into the X clip (4:3 1920×1440, 60 fps, H.264 + AAC, −14 LUFS; −16 LUFS from v6 on). Ported from
`../soap-bubbles` (same rules): the phone stays still in the centre for the whole demo, one straight cut to the end card,
frame 1 = the app's first frame (the finished crane hovering in the sunbeam), no status bar, nothing over the screen.

## Files

| File | What |
|---|---|
| `tools/rec.sh` | record the rec sim with the app slowed (TS=0.5), conform to 60 fps CFR demo time, film start |
| `tools/filmstart.sh` | app t = 0 in a recording (end of the 9 × 9 pt magenta marker − 0.5 s) |
| `tools/evcheck.sh` | contact sheet of the recording at every beat-sheet event (check the SFX times on a new take) |
| `tools/events.py` | copy `EVT <name> <t>` lines (Metro log of a dev run, or `vN/evt.log`) into a beat sheet |
| `tools/promo.sh` | one command: sync → audio (if stale) → Blender frames → ffmpeg export + loudness readout |
| `tools/sheet.sh` | 3×2 contact sheet of the exported clip (frames from the beat sheet `sheet`) |
| `blender/scripts/promo.py` | the Blender scene: titanium iPhone mockup playing the recording, anime-sunset background, end card |
| `blender/scripts/beats/vN.json` | beat sheet per recording: every timing, colours, end card layout, SFX events, music |
| `blender/scripts/mix_calm.py` | clip audio from v5 on (beat sheet `"mixer": "mix_calm.py"`): calm felt piano, strings pad, celesta, one steady tempo, −16 LUFS / ≤ −1 dBTP |
| `tools/screen_video.sh`, `tools/rec_user.sh`, `blender/scripts/user_edit.py` | the 9:19 screen video of a take; the real-use recording (scripted user) and its edit |
| `blender/scripts/mix_clip.py` | clip audio up to v4: music on sampled instruments + SFX on the beat-sheet events, mastered to −14 LUFS / ≤ −1 dBTP |
| `blender/scripts/synth_audio.py` | instruments + SFX generators (shared with the mix); run directly = one-shots in `render/sfx/` |
| `blender/textures/promo/sky_soft.jpg`, `sky_mid.jpg` | `app/assets/scene/anime/sky.jpg` cropped 4:3 and blurred (σ 36+18 / σ 9) |
| `render/audio/mix_vN.wav` (+ `.json`) | the clip audio (app t = 0 at its start), tempo and measured loudness |
| `render/promo/caption.txt` | X caption |

## Final take (v3, a repeat of v2)

`blender/scripts/beats/v2.json` matches the 01:45 build (first visible frame = app t = 0 → `app_start` 0; awaken 14.97 →
96.2 BPM, `app_end` 27.445; vanish 24.98 = the visible flash onset, 0.14 s after its EVT time; background sections follow
the events by name). `render/dd-release` was rebuilt with expo-audio at 01:08 (the screen recording has no audio anyway).
Check first that no other session records (`pgrep -fl "rec3d.sh|tools/rec.sh"`), then:

```sh
cd origami-crane
sed 's#mix_v2.wav#mix_v3.wav#' blender/scripts/beats/v2.json > blender/scripts/beats/v3.json
UDID=$(cat notes/udid_rec.txt) DEMO=1 TS=0.5 tools/embed.sh
TS=0.5 OUT=render/promo/v3 tools/rec.sh                                       # ~80 s; check.txt 60/s, no WARNING
tools/evcheck.sh render/promo/v3/screen.mp4 blender/scripts/beats/v3.json    # look at render/promo/v3/evcheck.jpg
PCT=50 tools/promo.sh --beats blender/scripts/beats/v3.json --screen render/promo/v3/screen.mp4 --stills 0,3.2,15.6,23.6,28.8
WORKERS=2 tools/promo.sh --beats blender/scripts/beats/v3.json --screen render/promo/v3/screen.mp4 \
    --out render/promo/origami-crane-demo-v3.mp4                              # ~34 min at full resolution (WORKERS=2)
tools/sheet.sh render/promo/origami-crane-demo-v3.mp4 render/promo/origami-crane-sheet-v3.jpg blender/scripts/beats/v3.json
```

If an event time moved: fix it in v3.json (if `awaken` moves, set `app_end` to what the mix prints: "set app_end …").
Never pass `LABEL` for the final (it draws a small version label in the corner).

## Make a clip (next version N)

```sh
cd origami-crane
# 1. bundle the current JS into the Release app on the recording sim (no native build)
UDID=$(cat notes/udid_rec.txt) DEMO=1 TS=0.5 tools/embed.sh
# 2. record (rec sim only; ~75 s real time for SECS=33 demo seconds; pauses other sim apps / ffmpeg / Blender, never node/Metro)
TS=0.5 OUT=render/promo/vN tools/rec.sh
#    → check.txt must read 60 per second; filmstart.txt = app t = 0 in screen.mp4
# 3. beat sheet: copy the last one, set "audio": "render/audio/mix_vN.wav", then check the event times on the take
cp blender/scripts/beats/v1.json blender/scripts/beats/vN.json
tools/evcheck.sh render/promo/vN/screen.mp4 blender/scripts/beats/vN.json     # → render/promo/vN/evcheck.jpg
# 4. quick look (clip seconds, half resolution) → render/promo/stills/
PCT=50 tools/promo.sh --beats blender/scripts/beats/vN.json --screen render/promo/vN/screen.mp4 --stills 0,3.2,9,15.6,23.6,28
# 5. full clip + sheet
WORKERS=2 tools/promo.sh --beats blender/scripts/beats/vN.json --screen render/promo/vN/screen.mp4 \
    --out render/promo/origami-crane-demo-vN.mp4
tools/sheet.sh render/promo/origami-crane-demo-vN.mp4 render/promo/origami-crane-sheet-vN.jpg blender/scripts/beats/vN.json
```

Options: `--film-start S` (override the marker), `PCT=50` (test render), `WORKERS=1|2` (parallel Blender processes,
default 2), `PROMO_FAST=1` (8 TAA samples), `LABEL=vN` (small corner label for comparisons).

### Recording and sync

- **Only the rec sim** "Origami Crane Rec 17 Pro Max" (`notes/udid_rec.txt`); rec.sh refuses another UDID unless `ANY_SIM=1`.
  `simctl io recordVideo` is host-exclusive: if another recording runs, rec.sh retries every 30 s (`RETRY=20`).
- Time conform: the .mov is VFR; its **container** timestamps are scaled with `-itsscale 0.5` and resampled to 60 fps
  CFR (no `setpts` on decoded frames). The app clock uses `dt × TIMESCALE`, so 1 s of screen.mp4 = 1 demo second.
- Sync: the app draws a 9 × 9 pt `#ff00ff` marker top-left while the demo clock is < 0.5 s. `filmstart.sh` takes the
  **end** of the marker − 0.5 s. The marker is usually ~23 frames instead of 30: the first ~7 frames of the clock are
  drawn before the screen shows anything (v0/v1 builds). So v0/v1 use `app_start` 0.12; promo.sh raises `app_start`
  automatically if a take's first drawn frame is later, so frame 1 is never black. From the 01:30 build on the clock
  waits for the images and then holds t = 0 for a 24-frame warm-up, so the first visible frame is the complete t = 0
  picture (`app_start` 0) and the marker shows ~54 frames; `EVT start` is logged at the start of the warm-up, so never
  sync on the log, always on the marker's end.
- Frozen takes: another session (soap-bubbles) runs a rec script that SIGSTOPs other sims' apps. rec.sh warns when a
  second of screen.mp4 has < 55 distinct frames; then check the take (and `ps -o stat` for `T`) and redo it.
- Release builds do not log the `EVT` lines through `log stream` (rec.sh captures `vN/evt.log` anyway, in case). The demo
  is deterministic, so the beat-sheet times carry over between takes of the same build; after app changes, measure
  with a dev run (`tools/events.py <metro.log> <beats>`) or read them off the take with `tools/evcheck.sh`.
- `SECS` (rec.sh default 37; final.sh passes 47 for the v4 storyboard) must cover `app_end + card` (+ margin): the end-card phone keeps playing the recording.
- **Do not edit rec.sh while a take runs** (bash reads the script as it goes; that broke the first v0 conform).

## Beat sheet (v1)

- `app_start` 0.12 / `app_end` 27.125 / `card` 3.0 → clip 30.0 s (1800 frames). `app_end` sits on the bar line after
  the music's last bar (mix prints "card on the bar line at …"; it warns if `app_end` is off).
- `bg`: `[timing, top, mid, bottom, sun glow colour, glow strength, cross-fade frames, (plate_mix), (brightness)]`.
  Timing = app second, `"start"`, `"card"`, `"card+0.5"`, or an event name with an optional offset (`"climb"`, `"rewind+2.3"`). Sections: warm house (start), pinker while folding (4.6), golden on the
  awakening (14.85), sky blue as the crane leaves (climb 20.57, 2.5 s fade), sunset gold-pink after the vanish (24.8),
  peach end card. `plate_mix` = how much of the gradient goes over the painted clouds (0 = only the blurred sky).
- `bg_plates`, `bg_drift`, `bg_mid_amt`: the two cloud layers, their drift over the clip, the sharper layer's amount.
- `bokeh_n` / `bokeh_alpha`, `petals_n` / `petal_size` / `petal_cols`: background sprites (petals stay behind the phone; the
  ones that would cross the end-card text are hidden on the card).
- `camera_d` 5.0 (phone ~89 % of the height), `card_d` 7.4, `card_phone` (pose on the card), `card_x` (text column
  centre), `title_z`, `title_maxw`, `title_in` / `title_step` (letters fade + rise in; the mix plays a soft note per
  letter, keep both in the beat sheet), `body_in`.
- `music` (v4+): only `pickup` (play the two-eighth pickup before the first bar when there is room). The tempo map comes
  from the events (see Audio); up to v3 it was `anchor` / `bars_before` / `bars_after` (BAR = (awaken − app_start) / 6).
- `events` (demo seconds): `folds` (14 landing times; fold14 = awaken), `awaken`, `takeoff`, `climb`, `through` (camera
  passes the opening), `vanish` (flash in the sun). Up to v3 also `rewind` (+ `rewind_len`) and `furin` ([t, Hz, pan]);
  the v4 mix uses neither (a missing `rewind` is fine).
- `sheet`: six app seconds for `tools/sheet.sh` (the last one on the end card).

## Audio

Rebuild by hand (≈9 s, prints the tempo map, stems per section, harshness and loudness):

```sh
/Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 blender/scripts/mix_clip.py --beats blender/scripts/beats/v4.json
```

- Music (v4): calm, cinematic, in the spirit of a Ghibli / Hisaishi score, on **real sampled instruments** read at mix
  time from this Mac's factory libraries (nothing copied into the repo): Steinway grand (Logic "Steinway Grand Piano 2",
  soft velocity layer, its full-length zones from `Steinway Piano_consolidated.caf`, EXS zone map parsed by
  `synth_audio.parse_exs`, layout and tuning checked by FFT at load: the piano is stretch-tuned ~+7 cents, the mix
  retunes it to A440), GarageBand String Ensemble (soft n/m and loud f layers, crossfaded by intensity), solo flute
  (sustain mf) and French horns (sustain mf). Pitch = Hermite resampling from the nearest sampled note, sustain loops
  from the WAV `smpl` chunks, per-note release envelopes, a stereo hall (frequency-dependent decay, RT ~2.9 s low /
  0.9 s high), gentle EQ (−1.5 dB at 300 Hz, +1.5 dB at 3 kHz, high shelf −4 dB from 10 kHz, 15 kHz low-pass).
  No drums, no beat.
- Form, D major with a yo-pentatonic melody (D E G A B), 6/8: opening = solo piano motif "D E A | G E D | E D B A | B"
  over a ppp string pad; folding = motif + piano broken chords (D – Em7 – Gmaj7 – Asus4 | D/F# – Bm7 – Gmaj7/Em7 –
  Asus4/A), the strings build voice by voice, a very soft high piano note on every fold; awakening = C – D (bVII of E)
  with a high piano "celesta" sweep, string swell and a flute pickup; flight = E major tutti (E – F#m7 – Amaj7 –
  Bsus4/B), the flute carries the motif a step higher, violins an octave below, horns, piano arpeggios, climbing to E6 on
  the vanish; vanish = resolution on E, the piano echoes the motif up high; end card = rolled Eadd9 whose notes follow
  the title letters (`title_in` / `title_step`), ringing out.
- Tempo map (all from the events, so re-measured times just work): pulse = fitted fold period (one fold = a dotted
  quarter, a 6/8 bar = two folds), every fold is an anchor (even folds on bar lines, fold14 = awaken on a downbeat);
  intro bars before the first fold, awaken → takeoff, takeoff → vanish (2–6 bars, phrases picked to fit), vanish →
  app_end and the card are each a whole number of bars with the eighths spread evenly. Measured v4 events: eighth
  0.515 s (♩ 58) while folding, ♩ ≈ 73–75 from the awakening on. Tested with every event moved by ±1 s.
- SFX (v4, quiet under the music, ~−12 dB in the fold windows): per fold a soft paper slide (0.44 s before the landing)
  + a natural crease (smooth-grain crinkle, muffled pat, finger slide; no clicks); a gentle airy whoosh on take-off and a
  fainter one on the climb; a soft shimmer of light on the vanish; a very low garden bed (breeze, four distant birds).
- Master: 48 kHz stereo 24-bit, two-pass ffmpeg loudnorm (linear) + 4× oversampled look-ahead limiter, then a small
  trim to −14.0 LUFS if the true peak allows. `render/audio/mix_vN.json`: tempo map, sections, LUFS / LRA / true peak,
  clipped samples, crest, harshness (spectral centroid, energy above 6 kHz, worst 0.5 s window) for the whole mix and
  per section. promo.sh prints the ebur128 summary of the exported clip.
- v4 figures: −14.0 LUFS, true peak −1.4 dBTP, LRA 8.7 LU, 0 clipped samples, limiter 0.5 dB; centroid 650 Hz, energy
  above 6 kHz −41.8 dB (worst 0.5 s −33.4 dB). The old synthesised v3 mix: centroid 755 Hz, above 6 kHz −20.9 dB.
- v0–v3 (old storyboard with a rewind): synthesised lo-fi / J-pop beat (koto hook, kick, shaker, claps, marimba, glock)
  in the old version of mix_clip.py; the old SFX generators stay in synth_audio.py for the one-shots.
- One-shots for a possible in-app use: `synth_audio.py` → `render/sfx/` (crease_1..4, rustle, rewind, furin, awaken,
  flutter, whoosh, bloom); `--app` writes them to `app/assets/sfx/` (only when the app owner asks).

## Freeze check (04/11, 02:30)
`check.txt` (mpdecimate on the encoded screen.mp4) can report 60/60 even when the app was frozen: x264 noise makes repeated
frames look "distinct". rec.sh now also writes `rawcheck.txt` from the raw .mov packet timestamps (simctl writes a frame only
when the screen changes) and warns when a real second after the launch has < 50 frames. Take t3 (02:24) froze at the awakening
because the soap-bubbles session started its own rec script mid-take (it SIGSTOPs other sims' apps); the retake at 02:27 was clean.
Before AND after the final take: `pgrep -fl "rec3d.sh|tools/rec.sh"`, and read rawcheck.txt.

## One command (04/11, 02:50)
`tools/final.sh v3` runs the whole recipe above with the safety checks:
- It waits while another project's recorder runs, found by the cwd of `rec3d.sh`/`tools/rec.sh` processes.
- It bundles the app and records.
- It retakes, up to 3 times, if `rawcheck.txt` shows frozen seconds or another recorder overlapped.
- It then runs `evcheck`, the full render (WORKERS=2) and the clip sheet, and appends a row to notes/versions.md.
