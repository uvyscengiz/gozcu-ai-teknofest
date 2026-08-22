#!/bin/bash
# Downloads the first N items of each askeri playlist into data/raw/askeri-playlist/.
set -u
cd "$(dirname "$0")"
N="${1:-10}"
mkdir -p raw/askeri-playlist
i=0
for pl in "PLakEHcmK8B8WPrVTZO6Fdzfgqb6gI93SR" "PLCCgfjUwnRFYobTH6fQkbDcHcYFfNuRhk"; do
  i=$((i+1))
  echo "=== playlist $i ($pl) ilk $N"
  yt-dlp \
    -f "bv*[height<=1080]+ba/b[height<=1080]/b" \
    --merge-output-format mp4 \
    --playlist-items "1-$N" \
    --no-overwrites --no-progress --no-warnings --ignore-errors \
    --write-info-json \
    -o "raw/askeri-playlist/pl${i}-%(playlist_index)02d--%(id)s.%(ext)s" \
    "https://www.youtube.com/playlist?list=$pl" || echo "!!! playlist $i kismen basarisiz"
done
