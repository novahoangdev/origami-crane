#!/bin/bash
# metro.sh: Metro for the dev build on port 8093 with watch mode, kept alive without a terminal and restarted if it exits
# (stdin is a never-ending pipe so the Expo CLI never sees EOF). Log: notes/metro.log
cd "$(dirname "$0")/../app"
trap '' HUP
while true; do
  echo "--- metro start $(date +%T)" >> ../notes/metro.log
  # run the CLI through node directly (not "npx expo start --port …"): another session's cleanup does
  # `pkill -f "expo start --port"`, which must not hit this server
  node node_modules/expo/bin/cli start --dev-client --port 8093 < <(sleep 2147483647) >> ../notes/metro.log 2>&1
  echo "--- metro exited $? $(date +%T)" >> ../notes/metro.log
  sleep 1
done
