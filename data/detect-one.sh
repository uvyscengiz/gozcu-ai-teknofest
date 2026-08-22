#!/bin/bash
set -u
cd "$(dirname "$0")"
f="$1"; b=$(basename "$f" .mp4); csv="scenes/${b}-scenes.csv"
[ -s "$csv" ] && exit 0
scenedetect -i "$f" -o scenes -d 4 -q \
  detect-adaptive --min-scene-len 1.5s \
  list-scenes -f "${b}-scenes.csv" >/dev/null 2>&1
