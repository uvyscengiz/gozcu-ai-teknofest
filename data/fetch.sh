#!/bin/bash
# Downloads every non-playlist source in sources.tsv into data/raw/<kategori>/.
# Capped at 1080p, remuxed to mp4. Re-runnable: yt-dlp skips existing files.
set -u
cd "$(dirname "$0")"
mkdir -p raw
while IFS=$'\t' read -r slot cat url note; do
  [ -z "${url:-}" ] && continue
  case "$url" in *"playlist?list="*) continue ;; esac
  mkdir -p "raw/$cat"
  echo "=== $slot  $url"
  yt-dlp \
    -f "bv*[height<=1080]+ba/b[height<=1080]/b" \
    --merge-output-format mp4 \
    --no-playlist --no-overwrites --no-progress --no-warnings \
    --write-info-json \
    -o "raw/$cat/${slot}--%(id)s.%(ext)s" \
    "$url" || echo "!!! FAILED: $url"
done < sources.tsv
