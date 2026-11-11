#!/bin/bash
# burst.sh: relaunch the dev app on the main sim, wait for the demo clock to start ("EVT clock" in notes/metro.log),
# skip SKIP seconds, take N screenshots every DT seconds and tile them into one sheet.
#   N=24 DT=0.4 SKIP=0 COLS=12 W=160 [AT=climb] OUT=/path/sheet.jpg tools/burst.sh
set -uo pipefail
cd "$(dirname "$0")/.."
U=${UDID:-$(cat notes/udid.txt)}
N=${N:-24}; DT=${DT:-0.4}; SKIP=${SKIP:-0}; COLS=${COLS:-12}; W=${W:-160}
OUT=${OUT:?set OUT}
D=$(mktemp -d)
L=notes/metro.log
n0=$(wc -l < "$L" | tr -d ' ')
xcrun simctl terminate "$U" dev.hoanghoa.origamicrane 2>/dev/null
sleep 0.5
xcrun simctl openurl "$U" "exp+origami-crane://expo-development-client/?url=http%3A%2F%2Flocalhost%3A8093"
for i in $(seq 1 160); do tail -n +"$((n0 + 1))" "$L" | grep -aq "EVT clock" && break; sleep 0.25; done
# AT=<event>: wait for "EVT <event>" (e.g. climb, vanish) instead of counting wall-clock seconds from the start
if [[ -n "${AT:-}" ]]; then for i in $(seq 1 400); do tail -n +"$((n0 + 1))" "$L" | grep -aq "EVT $AT" && break; sleep 0.1; done; fi
sleep "$SKIP"
for i in $(seq -w 1 "$N"); do xcrun simctl io "$U" screenshot "$D/$i.png" >/dev/null 2>&1; sleep "$DT"; done
ROWS=$(( (N + COLS - 1) / COLS ))
ffmpeg -loglevel error -y -pattern_type glob -i "$D/*.png" -vf "scale=$W:-1,tile=${COLS}x${ROWS}" -frames:v 1 "$OUT"
echo "$D"
