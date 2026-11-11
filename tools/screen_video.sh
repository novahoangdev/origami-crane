#!/bin/bash
# screen_video.sh: the raw app recording as a full-screen portrait video with the clip soundtrack (720×1564, 60 fps), the
# second format next to the 4:3 promo (as in the soap-bubbles and neon-sign projects): from app t = 0 to app t = END
# (default app_end + card from the beat sheet, so the end-card chord rings out), audio = the version's mix from app t = 0.
# The demo's magenta sync marker (9 × 9 pt top-left while the clock is < 0.5 s; hidden by the mockup corner in the 4:3
# clip) is covered with the patch of picture right next to it.
#   tools/screen_video.sh render/promo/vN/screen.mp4 <film start> render/audio/mix_vN.wav OUT.mp4 [beats.json]
set -euo pipefail
cd "$(dirname "$0")/.."
SCREEN=$1; FS=$2; AUDIO=$3; OUT=$4; BEATS=${5:-}
if [[ -z "${END:-}" ]]; then
  END=$([[ -n "$BEATS" ]] && python3 -c "import json,sys; b=json.load(open(sys.argv[1])); print(b['app_end'] + b.get('card', 3))" "$BEATS" || echo 40)
fi
ffmpeg -v error -y -ss "$FS" -t "$END" -i "$SCREEN" -i "$AUDIO" -filter_complex \
  "[0:v]split[s0][s1];[s1]crop=44:44:44:0[pt];[s0][pt]overlay=0:0:enable='lt(t,1.0)',scale=720:1564:flags=lanczos,setsar=1,fps=60,format=yuv420p,fade=t=out:st=$(python3 -c "print($END-0.6)"):d=0.6[v];\
[1:a]atrim=0:$END,afade=t=out:st=$(python3 -c "print($END-1.0)"):d=1.0[a]" \
  -map "[v]" -map "[a]" -t "$END" -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p -r 60 -c:a aac -b:a 192k \
  -movflags +faststart "$OUT"
ls -lh "$OUT"
ffmpeg -hide_banner -nostats -i "$OUT" -af ebur128=peak=true -f null - 2>&1 | awk '/Summary:/{s=1} s && /I:|Peak:/{printf "%s ", $0} END{print ""}' | tr -s ' '
