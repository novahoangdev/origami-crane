#!/bin/bash
# embed.sh: copy the built Release app, replace main.jsbundle with the current JS bundle (no native build), install on the sim.
#   [DEMO=1] [TS=0.5] tools/embed.sh          (DEMO=0 USERSIM=1 TS=1: the scripted-user screen recording build)
# Use when only JS/TS/SkSL changed. Native changes need: xcodebuild … -configuration Release (see notes/build_release.log).
set -euo pipefail
cd "$(dirname "$0")/../app"
UDID=${UDID:-$(cat ../notes/udid.txt)}
SRC=${SRC:-$(cd .. && pwd)/render/dd-release/Build/Products/Release-iphonesimulator/OrigamiCrane.app}
WORK=${WORK:-$(cd .. && pwd)/render/embed}
node ../tools/pack_fold.mjs
rm -rf "$WORK"; mkdir -p "$WORK"; cp -R "$SRC" "$WORK/"
APPD="$WORK/OrigamiCrane.app"
EXPO_PUBLIC_DEMO=${DEMO:-1} EXPO_PUBLIC_USERSIM=${USERSIM:-0} EXPO_PUBLIC_TIMESCALE=${TS:-1} npx expo export:embed --platform ios --dev false --minify true \
  --entry-file index.ts --bundle-output "$APPD/main.jsbundle" --assets-dest "$APPD" >/dev/null
codesign -f -s - --deep "$APPD" >/dev/null 2>&1 || true
xcrun simctl install "$UDID" "$APPD"
echo "installed $APPD (DEMO=${DEMO:-1} TS=${TS:-1})"
