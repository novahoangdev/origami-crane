#!/bin/bash
# evcheck.sh: contact sheet of the recording at every beat-sheet event (to check the SFX times on a new take).
#   tools/evcheck.sh render/promo/v1/screen.mp4 blender/scripts/beats/v1.json [out.jpg]
# Film start from tools/filmstart.sh. Tiles (left to right, top to bottom): [rewind (v1–v3 storyboard),] fold1..fold14, takeoff, climb, through,
# vanish − 0.1, vanish, vanish + 0.15; each at the event time (a fold = the flap has just landed, the swipe dot leaving).
# Release builds do not log EVT lines; if a tile looks early/late, step with
#   ffmpeg -ss <film start + t> -i screen.mp4 -frames:v 1 x.png   and fix the time in the beat sheet.
set -euo pipefail
cd "$(dirname "$0")/.."
SCREEN=$1; BEATS=$2; OUTJ=${3:-$(dirname "$SCREEN")/evcheck.jpg}
F0=$(tools/filmstart.sh "$SCREEN" 2>/dev/null)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
TIMES=$(python3 -c "
import json,sys
E=json.load(open(sys.argv[1]))['events']
ts=([('rewind',E['rewind'])] if 'rewind' in E else [('start',0.0)])+[(f'fold{i+1}',t) for i,t in enumerate(E['folds'])]
ts+=[(k,E[k]) for k in ('takeoff','climb','through') if k in E]
ts+=[('vanish-0.1',E['vanish']-0.1),('vanish',E['vanish']),('vanish+0.15',E['vanish']+0.15)]
print(' '.join(f'{n}={t}' for n,t in ts))" "$BEATS")
i=0
for nt in $TIMES; do
  t=${nt#*=}
  ffmpeg -v error -y -ss "$(python3 -c "print($F0 + $t)")" -i "$SCREEN" -frames:v 1 -vf scale=220:-2 "$TMP/$(printf %02d $i).png"
  echo "tile $i: ${nt%%=*} @ $t"
  i=$((i + 1))
done
ffmpeg -v error -y -i "$TMP/%02d.png" -vf "tile=11x2:padding=3:color=0x202020" -q:v 3 "$OUTJ"
echo "film start $F0 → $OUTJ"
