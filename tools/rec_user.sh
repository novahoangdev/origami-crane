#!/bin/bash
# rec_user.sh: the "real use" screen recording, the third format next to the 4:3 promo and the 9:19 demo screen video:
# the home screen, a tap on the app icon, the app opening, and the interactive app (hints, step dots, captions) operated
# by the scripted user of EXPO_PUBLIC_USERSIM=1 (touches through the real pan / tap handlers, iOS-style touch dots), who
# folds all 14 steps, watches the crane fly off and taps for another sheet. Real time (no time scale), 60 fps.
#
#   tools/rec_user.sh v7                 # → render/promo/origami-crane-user-9x19-v7.mp4
#   NOBUILD=1 tools/rec_user.sh v7       # reuse the installed USERSIM build
#   RAWONLY=1 …                          # only record; POSTONLY=1 … only redo the edit from render/promo/user_v7/raw.mov
#
# Steps: embed the USERSIM Release bundle on the Rec sim (tools/embed.sh DEMO=0 USERSIM=1 TS=1); pause other sims' apps,
# ffmpeg and Blender like rec.sh; status bar 9:41; record; launch the app 2 s in; stop after SECS. Then the edit
# (blender/scripts/user_edit.py): CFR 60 fps, the app icon found on the home screen (template match against the app icon)
# and a touch dot drawn on it just before the launch animation starts, the music (mix_calm.py on the beat sheet
# beats/user_vN.json, app t = 0 = the end of the magenta sync marker − 0.5 s, painted out) laid under it, 1080 × 2346.
set -euo pipefail
cd "$(dirname "$0")/.."
V=${1:?version, e.g. v7}
OUT=render/promo/user_$V
SECS=${SECS:-74}
UDID=$(cat notes/udid_rec.txt)
APP=dev.hoanghoa.origamicrane
BPY=/Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13
mkdir -p "$OUT"

if [[ -z "${POSTONLY:-}" ]]; then
  [[ -n "${NOBUILD:-}" ]] || UDID=$UDID DEMO=0 USERSIM=1 TS=1 tools/embed.sh
  PIDS=$(ps ax -o pid=,command= | grep -E 'CoreSimulator/Devices/[^/]+/data/Containers/Bundle/Application/.*\.app/|(^|/| )ffmpeg |Blender' \
    | grep -v "$UDID" | grep -vE 'grep|node|expo|metro' | awk '{print $1}' | tr '\n' ' ' || true)
  resume() { [[ -n "$PIDS" ]] && kill -CONT $PIDS 2>/dev/null; true; }
  trap resume EXIT
  [[ -n "$PIDS" ]] && { echo "pausing $(echo $PIDS | wc -w) processes"; kill -STOP $PIDS 2>/dev/null || true; }
  xcrun simctl status_bar "$UDID" override --time "9:41" --dataNetwork wifi --wifiMode active --wifiBars 3 \
    --cellularMode active --cellularBars 4 --batteryState charged --batteryLevel 100 || true
  xcrun simctl terminate "$UDID" "$APP" 2>/dev/null || true
  sleep 2.5   # back on the home screen, the icons settled
  rm -f "$OUT/raw.mov"
  xcrun simctl io "$UDID" recordVideo --codec=h264 --force "$OUT/raw.mov" > "$OUT/rec.log" 2>&1 &
  RP=$!
  sleep 2.2
  xcrun simctl launch "$UDID" "$APP" > /dev/null
  echo "recording ${SECS} s…"
  sleep "$SECS"
  kill -INT $RP
  wait $RP || true
  resume
  ls -lh "$OUT/raw.mov"
fi
[[ -n "${RAWONLY:-}" ]] && exit 0
"$BPY" blender/scripts/user_edit.py --raw "$OUT/raw.mov" --beats "blender/scripts/beats/user_$V.json" \
  --out "render/promo/origami-crane-user-9x19-$V.mp4" --work "$OUT"
