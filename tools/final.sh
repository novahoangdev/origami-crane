#!/bin/bash
# final.sh: the whole final take in one go (the v2 recipe in notes/promo.md, with the safety checks).
#   tools/final.sh v3            # → render/promo/origami-crane-demo-v3.mp4 + origami-crane-sheet-v3.jpg (~40 min)
# 1. waits while another session's recorder runs (their rec scripts SIGSTOP every other sim app, which freezes our take)
# 2. bundles the current app into the Release build on the Rec sim (DEMO=1, TS=0.5)
# 3. records; if rawcheck.txt reports frozen seconds, waits for the other recorder again and retakes (up to 3 takes)
# 4. event contact sheet, full-resolution render (WORKERS=2), clip contact sheet, the 9:19 screen video, a row in notes/versions.md
set -euo pipefail
cd "$(dirname "$0")/.."
V=${1:?version, e.g. v3}
ROOT=$(pwd -P)
BEATS=blender/scripts/beats/$V.json
OUT=render/promo/$V

# recorder processes whose working directory is not this project
others() {
  local p cwd
  for p in $(pgrep -f "rec3d.sh|tools/rec.sh" || true); do
    cwd=$(lsof -a -d cwd -p "$p" -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)
    [[ -n "$cwd" && "$cwd" != "$ROOT"* ]] && echo "$p"
  done
  true
}
wait_others() {
  local n=0
  while [[ -n "$(others)" ]]; do
    (( n++ % 10 == 0 )) && echo "$(date +%T) another session is recording ($(others | tr '\n' ' ')), waiting…"
    sleep 3
  done
}

[[ -f "$BEATS" ]] || sed "s#mix_v2.wav#mix_$V.wav#" blender/scripts/beats/v2.json > "$BEATS"
echo "$(date +%T) bundle"
UDID=$(cat notes/udid_rec.txt) DEMO=1 TS=0.5 tools/embed.sh

for take in 1 2 3; do
  wait_others
  echo "$(date +%T) take $take"
  rm -rf "$OUT"
  TS=0.5 OUT="$OUT" SECS=${SECS:-47} tools/rec.sh   # v4 storyboard: app_end 39.6 + card 3 + warm-up + margin
  if grep -q WARNING "$OUT/rawcheck.txt" || [[ -n "$(others)" ]]; then
    echo "$(date +%T) take $take froze or overlapped another recorder: retake"
    continue
  fi
  break
done
grep -q WARNING "$OUT/rawcheck.txt" && { echo "every take froze, giving up" >&2; exit 1; }

tools/evcheck.sh "$OUT/screen.mp4" "$BEATS" || true
echo "$(date +%T) render"
WORKERS=2 tools/promo.sh --beats "$BEATS" --screen "$OUT/screen.mp4" --out "render/promo/origami-crane-demo-$V.mp4"
tools/sheet.sh "render/promo/origami-crane-demo-$V.mp4" "render/promo/origami-crane-sheet-$V.jpg" "$BEATS"
FS=$(cat "$OUT/filmstart.txt" 2>/dev/null | tail -1)
# the second format: the bare screen recording, portrait, with the same soundtrack
AUD=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['audio'])" "$BEATS")
tools/screen_video.sh "$OUT/screen.mp4" "$FS" "$AUD" "render/promo/origami-crane-screen-9x19-$V.mp4" "$BEATS"
echo "| $V | final take $(date '+%d/%m %H:%M') (tools/final.sh): current app | rawcheck clean; film start $FS; clip render/promo/origami-crane-demo-$V.mp4 |" >> notes/versions.md
echo "$(date +%T) done → render/promo/origami-crane-demo-$V.mp4"
