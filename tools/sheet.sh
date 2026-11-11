#!/usr/bin/env bash
# Quick-look image of 6 frames (3×2 grid, 1800 px wide) from the exported promo clip (ported from ../soap-bubbles).
#   tools/sheet.sh [clip.mp4] [out.jpg] [beats.json]
#     defaults: render/promo/origami-crane-demo-v1.mp4 → render/promo/origami-crane-sheet-v1.jpg, beat sheet v1
# Timings come from "sheet" (app seconds) and "app_start" in the beat sheet; override with APP_TIMES="…" APP_START=…
set -eo pipefail
cd "$(dirname "$0")/.."
IN=${1:-render/promo/origami-crane-demo-v1.mp4}
OUT=${2:-render/promo/origami-crane-sheet-v1.jpg}
BEATS=${3:-blender/scripts/beats/v1.json}
APP_START=${APP_START:-$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['app_start'])" "$BEATS")}
APP_TIMES=${APP_TIMES:-$(python3 -c "import json,sys; print(' '.join(map(str, json.load(open(sys.argv[1]))['sheet'])))" "$BEATS")}
[[ -f "$IN" ]] || { echo "not found: $IN" >&2; exit 1; }
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
i=0
for t in $APP_TIMES; do
  c=$(python3 -c "print(max(0.0, round($t - $APP_START, 3)))")
  ffmpeg -v error -y -ss "$c" -i "$IN" -frames:v 1 -vf "scale=600:450:flags=lanczos" "$TMP/$i.png"
  i=$((i + 1))
done
[[ $i -eq 6 ]] || { echo "need exactly 6 timings (got $i)" >&2; exit 1; }
# dark 4 px border between tiles for readability
ffmpeg -v error -y -framerate 1 -i "$TMP/%d.png" \
  -vf "tile=3x2:padding=4:margin=4:color=0x2a2438,scale=1800:-2:flags=lanczos" -frames:v 1 -q:v 3 "$OUT"
ls -lh "$OUT"
