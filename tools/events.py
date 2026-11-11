#!/usr/bin/env python3
"""events.py: copy the scene event times of a deterministic demo run into a beat sheet (sound effects land on the frame).

The app (DEMO=1) logs `EVT <name> <t>` (demo seconds): start, rewind, fold1..fold14, awaken, takeoff, climb, vanish.
Sources: a Metro log of a dev run (EXPO_PUBLIC_DEMO=1 npx expo start …) or render/promo/vN/evt.log from tools/rec.sh
(simctl log stream; Release builds may not log, then keep the beat sheet times or read them off the recording).

  python3 tools/events.py render/promo/v1/evt.log blender/scripts/beats/v1.json

Writes events.rewind / folds (fold1..N in order) / awaken / takeoff / climb / vanish; prints what changed.
"""
import json
import re
import sys

log, beats = sys.argv[1], sys.argv[2]
seen = {}
for line in open(log, errors="ignore"):
    m = re.search(r"EVT ([a-z]+\d*) (-?[0-9.]+)", line)
    if m and m[1] not in seen:          # first occurrence (later runs of the demo loop are ignored)
        seen[m[1]] = round(float(m[2]), 3)
if not seen:
    sys.exit(f"no EVT lines in {log}")
b = json.load(open(beats))
E = b["events"]
old = json.dumps(E, sort_keys=True)
folds = [seen[k] for k in sorted((k for k in seen if re.fullmatch(r"fold\d+", k)), key=lambda k: int(k[4:]))]
if folds:
    E["folds"] = folds
for k in ("rewind", "awaken", "takeoff", "climb", "vanish"):
    if k in seen:
        E[k] = seen[k]
json.dump(b, open(beats, "w"), indent=1)
print(f"{len(seen)} events: rewind {E.get('rewind')} | {len(folds)} folds {folds[:1]}…{folds[-1:]} | awaken {E.get('awaken')} "
      f"takeoff {E.get('takeoff')} climb {E.get('climb')} vanish {E.get('vanish')}"
      + ("" if json.dumps(E, sort_keys=True) != old else " (unchanged)"))
