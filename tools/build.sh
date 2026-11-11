#!/usr/bin/env bash
# Blender pipeline -> app/assets/scene: (Codex textures) -> build blender/room.blend -> render bg / table / backdrop + layout.json
#   tools/build.sh            final (100 %, 160 samples)
#   PREVIEW=1 tools/build.sh  quick preview (50 %, 24 samples)
#   TEX=1 tools/build.sh      reprocess the Codex images in blender/textures/raw first (also writes paper_*.jpg, icon)
#   extra args go to render_passes.py, e.g. tools/build.sh --only table
#   ANIME=1 tools/build.sh    anime look (default since v2): Codex paintings in blender/textures/anime_raw -> multiplane
#                             layers + table light passes + bg/backdrop composites (blender/scripts/anime_scene.py, no Cycles)
#   ANIME=0 tools/build.sh    the older Cycles tea room
# Scene knobs (env vars read by build_scene.py): OC_SUN OC_SKY OC_FILL OC_EXPOSURE
set -eo pipefail
cd "$(dirname "$0")/.."
BLENDER=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
if [[ "${ANIME:-1}" == 1 ]]; then
  BPY=$(ls /Applications/Blender.app/Contents/Resources/*/python/bin/python3.* | head -1)
  "$BPY" -I blender/scripts/anime_scene.py
  ls -lh app/assets/scene app/assets/scene/anime app/assets/fx
  exit 0
fi
if [[ "${PREVIEW:-0}" == 1 ]]; then RARGS=(--pct 50 --samples 24); else RARGS=(--pct 100 --samples 160); fi
if [[ "${TEX:-0}" == 1 ]]; then
  "$BLENDER" -b --factory-startup -P blender/scripts/prep_textures.py 2>&1 | grep -E "TEX|FIBRE|Error|Traceback" || true
fi
"$BLENDER" -b --factory-startup -P blender/scripts/build_scene.py 2>&1 | grep -E "SAVED|Error|Traceback|line [0-9]+" || true
"$BLENDER" -b blender/room.blend -P blender/scripts/render_passes.py -- "${RARGS[@]}" "$@" 2>&1 \
  | grep -E "── render|SAVE|TABLE|SUNMASK|AMBIENT|TIMES|Error|Traceback|line [0-9]+" || true
ls -lh app/assets/scene
