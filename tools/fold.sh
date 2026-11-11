#!/bin/sh
# Bake the origami crane fold sequence and render step previews.
# Usage: tools/fold.sh [--no-render] [--steps=N] [--only=1,2]
cd "$(dirname "$0")/.." || exit 1
exec /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup \
  -P blender/scripts/fold_crane.py -- "$@"
