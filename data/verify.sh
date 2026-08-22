#!/bin/bash
# Bozuk/yarim kalan kesitleri bulur (moov atom yok, sure okunamiyor).
cd "$(dirname "$0")"
for f in $(find clips -name "*.mp4" | sort); do
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null)
  case "$d" in ''|N/A) echo "$f" ;; esac
done
