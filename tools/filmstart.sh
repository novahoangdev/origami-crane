#!/bin/bash
# filmstart.sh: second in a recording (screen.mp4 from tools/rec.sh, demo time) that shows app t = 0.
# Demo builds draw a 9 × 9 pt #ff00ff marker in the top-left corner while the demo clock is < 0.5 s
# (CraneScene.tsx `syncMark`). The END of the marker is the reliable anchor (startup jank can delay its first frames; builds
# from 04/11 01:25 also hold t = 0 for a warm-up (24 frames, 90 since 02:35), so the marker shows up to ~120 frames; the clock runs true after it):
# film start = first frame without the marker after frames with it − 0.5 s.
#   tools/filmstart.sh render/promo/v1/screen.mp4        → prints e.g. 1.2333 (warnings on stderr)
# MARK=0.5 overrides the marker length (demo seconds).
set -euo pipefail
MARK=${MARK:-0.5}
ffmpeg -v error -i "$1" -t 12 -vf "crop=18:18:4:4,scale=1:1:flags=area,format=rgb24" -f rawvideo - | python3 -c "
import sys
d = sys.stdin.buffer.read()
fr = [d[i:i + 3] for i in range(0, len(d) - 2, 3)]
seen = first = 0
for k, (r, g, b) in enumerate(fr):
    mag = r > 180 and g < 90 and b > 180
    if mag:
        if not seen:
            first = k
        seen += 1
    elif seen:
        exp = round($MARK * 60)
        if seen > exp + 100:
            print(f'WARNING: marker visible for {seen} frames (expected ~{exp} + the 90-frame warm-up hold): startup jank held the clock, check an event frame', file=sys.stderr)
        elif seen < exp - 3:
            print(f'note: marker visible for {seen} frames (expected ~{exp}): the first frames reached the screen late (the end of the marker is still exact)', file=sys.stderr)
        print(f'marker frames {first}..{k - 1} ({seen})', file=sys.stderr)
        if first / 60.0 > k / 60.0 - $MARK + 1e-6:
            print(f'WARNING: the picture reached the screen {first / 60.0 - (k / 60.0 - $MARK):.3f} s after film start (frame 1 would be blank): set the beat sheet app_start >= that', file=sys.stderr)
        print(round(k / 60.0 - $MARK, 4)); sys.exit(0)
print('no sync marker found', file=sys.stderr); sys.exit(1)
"
