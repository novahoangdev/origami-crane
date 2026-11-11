#!/usr/bin/env bash
# Build the 4:3 X clip (1920×1440, 60 fps, H.264 + AAC) from a recording made by tools/rec.sh.
# Ported from ../soap-bubbles/tools/promo.sh (the recording itself is tools/rec.sh's job).
#
#   tools/promo.sh --beats blender/scripts/beats/v1.json --screen render/promo/v1/screen.mp4 \
#       [--film-start S] [--out render/promo/origami-crane-demo-v1.mp4]
#   tools/promo.sh --beats … --screen … --stills 0,4,15,28      # only a few frames (clip seconds) → render/promo/stills/
#
#   --film-start S   second in screen.mp4 that shows app t = 0. Default: tools/filmstart.sh (end of the magenta sync
#                    marker − 0.5 s), else render/promo/vN/filmstart.txt, else the first frame after the dark launch screen
#                    minus the beat sheet "sync_offset".
# Frame 1: the first frames of the demo clock can be drawn before the screen shows them (the marker is then shorter
#   than 30 frames). If the beat sheet "app_start" is earlier than the first drawn frame, it is raised to it (printed),
#   so the clip never starts on a black frame.
# Beat sheet (one per recording) holds every timing: app_start / app_end / card, background sections, end card layout,
#   SFX events, music, audio file, sheet frames.
# Audio: the beat sheet "audio" WAV (render/audio/mix_vN.wav, app t = 0 at its start) is (re)built with
#   the beat sheet's "mixer" (default blender/scripts/mix_clip.py) when it is missing or older than the beat sheet / audio scripts.
# Environment: PCT=50 (half resolution test render), LABEL=v2 (small bottom-left label), WORKERS=2 (parallel Blender
#   processes, each renders a contiguous frame range; 1 keeps the machine free), PROMO_FAST=1 (8 TAA samples),
#   FRAMES=render/promo/frames, AUDIO=… (override the beat sheet audio), BLENDER=…
set -eo pipefail
cd "$(dirname "$0")/.."
OUT=render/promo
FRAMES=${FRAMES:-$OUT/frames}
BLENDER=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
BPY=${BPY:-$(ls /Applications/Blender.app/Contents/Resources/*/python/bin/python3.* 2>/dev/null | head -1)}
BEATS=blender/scripts/beats/v0.json
SCREEN="" FILM0="" STILLS="" FINAL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --beats) BEATS=$2; shift 2 ;;
    --screen) SCREEN=$2; shift 2 ;;
    --film-start) FILM0=$2; shift 2 ;;
    --stills) STILLS=$2; shift 2 ;;
    --out) FINAL=$2; shift 2 ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done
[[ -f "$BEATS" ]] || { echo "beat sheet not found: $BEATS" >&2; exit 1; }
[[ -n "$SCREEN" && -f "$SCREEN" ]] || { echo "need --screen <recording.mp4> (1320×2868, 60 fps CFR from tools/rec.sh)" >&2; exit 1; }
VER=$(basename "$BEATS" .json)
FINAL=${FINAL:-$OUT/origami-crane-demo-$VER.mp4}
beat() { python3 -c "import json,sys; v=json.load(open(sys.argv[1])).get(sys.argv[2]); print(sys.argv[3] if v is None else v)" "$BEATS" "$1" "$2"; }
APP_START=$(beat app_start 0)
SYNC_OFF=$(beat sync_offset 0)
AUDIO=${AUDIO:-$(beat audio render/audio/mix_$VER.wav)}
MIXER=blender/scripts/$(beat mixer mix_clip.py)   # v5 on: "mixer": "mix_calm.py" (the calm piano score)
mkdir -p "$OUT"

# 1. sync: the magenta marker (exact), else the first frame after the dark launch screen
FIRST_DRAWN=""
if [[ -z "$FILM0" ]]; then
  if FS=$(tools/filmstart.sh "$SCREEN" 2>"$OUT/.filmstart.err"); then
    FILM0=$FS
    MF=$(grep -o "marker frames [0-9]*" "$OUT/.filmstart.err" | awk '{print $3}' || true)
    [[ -n "$MF" ]] && FIRST_DRAWN=$(python3 -c "print(round($MF / 60 - $FILM0, 4))")
    echo "sync marker → app t=0 at ${FILM0}s in the recording (first drawn frame = app ${FIRST_DRAWN:-?}s)"
    cat "$OUT/.filmstart.err" | grep -v "^marker frames" || true
  elif [[ -f "$(dirname "$SCREEN")/filmstart.txt" ]]; then
    FILM0=$(tail -1 "$(dirname "$SCREEN")/filmstart.txt")
    echo "film start from $(dirname "$SCREEN")/filmstart.txt: $FILM0"
  else
    FIRST=$(ffmpeg -loglevel error -i "$SCREEN" -vf "scale=64:-2,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-" -f null - \
      | awk '/pts_time/{split($0,a,"pts_time:"); t=a[2]+0} /YAVG/{split($0,b,"="); print t, b[2]+0}' \
      | python3 -c "
import sys
rows = [tuple(map(float, l.split())) for l in sys.stdin if l.strip()]
t = [r[0] for r in rows]; y = [r[1] for r in rows]
med = lambda v: sorted(v)[len(v) // 2]
splash = med(y[:6]); scene = med(y[len(y) // 3:])
if scene - splash < 12:
    print('0.0 none'); sys.exit()
thr = splash + 0.5 * (scene - splash)
for i in range(len(y) - 6):
    if all(v > thr for v in y[i:i + 6]):
        print(f'{t[i]:.4f} {y[i]:.1f}/{splash:.1f}->{scene:.1f}'); break
else:
    print('0.0 none')")
    read -r T_FIRST INFO <<<"$FIRST"
    FILM0=$(python3 -c "print(round($T_FIRST - $SYNC_OFF, 4))")
    echo "no sync marker: scene appears at ${T_FIRST}s (YAVG $INFO) → app t=0 at ${FILM0}s (check still 0)"
  fi
  rm -f "$OUT/.filmstart.err"
fi
if [[ -n "$FIRST_DRAWN" ]] && python3 -c "import sys; sys.exit(0 if $APP_START < $FIRST_DRAWN - 1e-6 else 1)"; then
  echo "app_start $APP_START is before the first drawn frame → using app_start $FIRST_DRAWN"
  APP_START=$FIRST_DRAWN
fi
python3 -c "import sys; sys.exit(0 if $FILM0 + $APP_START >= -1e-6 else 1)" \
  || { echo "film-start + app_start is negative — pass --film-start manually" >&2; exit 1; }

# 2. audio (cheap, ~5 s): rebuild when missing or stale
if [[ ! -f "$AUDIO" || "$BEATS" -nt "$AUDIO" || "$MIXER" -nt "$AUDIO" || blender/scripts/synth_audio.py -nt "$AUDIO" ]]; then
  echo "building audio → $AUDIO ($MIXER)"
  "$BPY" "$MIXER" --beats "$BEATS" --out "$AUDIO" | grep -E "MIX|CALM"
fi

# 3. Blender: picture (all timings from the beat sheet)
PROMO_ARGS=(--beats "$BEATS" --screen "$SCREEN" --film-start "$FILM0" --app-start "$APP_START" --pct "${PCT:-100}" --label "${LABEL:-}")
if [[ -n "$STILLS" ]]; then
  rm -rf "$OUT/stills"
  "$BLENDER" -b --factory-startup -P blender/scripts/promo.py -- "${PROMO_ARGS[@]}" --out "$OUT/stills" --stills "$STILLS" \
    2>&1 | grep -E "PROMO|Error|Traceback" || true
  ls "$OUT/stills"
  exit 0
fi
rm -rf "$FRAMES"
mkdir -p "$FRAMES"
T0=$(date +%s)
TOTAL=$(python3 -c "import json; b=json.load(open('$BEATS')); print(round((b['app_end'] - $APP_START + b.get('card', 3.0)) * 60))")
W=${WORKERS:-2}
PIDS_R=()
for ((i = 0; i < W; i++)); do
  a=$(( TOTAL * i / W )); b=$(( TOTAL * (i + 1) / W - 1 ))
  "$BLENDER" -b --factory-startup -P blender/scripts/promo.py -- "${PROMO_ARGS[@]}" --out "$FRAMES" --range "$a,$b" \
    > "$FRAMES.part$i.log" 2>&1 &
  PIDS_R+=($!)
done
for p in "${PIDS_R[@]}"; do wait "$p" || true; done
grep -hE "^PROMO beats" "$FRAMES.part0.log" || true
grep -hE "Traceback|Error" "$FRAMES".part*.log | head -5 || true
rm -f "$FRAMES".part*.log
NF=$(ls "$FRAMES" | grep -c '\.png$' || true)
[[ "$NF" -eq "$TOTAL" ]] || echo "warning: rendered $NF of $TOTAL frames" >&2
[[ "$NF" -gt 0 ]] || { echo "Blender produced no frames" >&2; exit 1; }
DUR=$(python3 -c "print(round($NF / 60, 3))")
echo "rendered $NF frames (${DUR}s) in $(( $(date +%s) - T0 ))s"

# 4. export for X: audio starts at app t = 0 → skip the first app_start seconds; 0.4 s safety fade at the very end
VENC=(-c:v libx264 -profile:v high -preset slow -crf 17 -pix_fmt yuv420p -r 60 -movflags +faststart)
if [[ -f "$AUDIO" ]]; then
  AF=$(python3 -c "
s, d = $APP_START, $DUR
head = f'atrim=start={s},asetpts=PTS-STARTPTS' if s >= 0 else f'adelay={round(-s*1000)}:all=1'
print(f'{head},apad,atrim=end={d},afade=t=out:st={round(d - 0.4, 2)}:d=0.4')")
  ffmpeg -y -loglevel error -framerate 60 -i "$FRAMES/%04d.png" -i "$AUDIO" \
    -filter_complex "[1:a]$AF[a]" -map 0:v -map "[a]" -t "$DUR" \
    "${VENC[@]}" -c:a aac -b:a 192k -ar 48000 "$FINAL"
else
  echo "no $AUDIO → exporting a silent clip"
  ffmpeg -y -loglevel error -framerate 60 -i "$FRAMES/%04d.png" "${VENC[@]}" "$FINAL"
fi
ls -lh "$FINAL"
ffmpeg -hide_banner -nostats -i "$FINAL" -map 0:a? -af ebur128=peak=true -f null - 2>&1 \
  | awk '/Summary:/{s=1} s && /I:|Peak:/{printf "%s ", $0} END{print ""}' | tr -s ' '
