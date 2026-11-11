#!/bin/bash
# Pack the tumbling leaf frames (render/leaf_frames, from blender/scripts/leaf_sprites.py) into app/assets/fx/leaves.png:
# 16 columns (tumble phase) × 3 rows (red maple, green maple, sakura petal), 128 px cells, straight alpha.
set -euo pipefail
cd "$(dirname "$0")/.."
D=render/leaf_frames
ffmpeg -v error -y \
  -framerate 1 -i "$D/leaf_maple_red_%02d.png" -framerate 1 -i "$D/leaf_maple_green_%02d.png" -framerate 1 -i "$D/petal_sakura_%02d.png" \
  -filter_complex "[0]scale=128:128,tile=16x1[a];[1]scale=128:128,tile=16x1[b];[2]scale=128:128,tile=16x1[c];[a][b][c]vstack=3,format=rgba" \
  -frames:v 1 app/assets/fx/leaves.png
echo "→ app/assets/fx/leaves.png"
