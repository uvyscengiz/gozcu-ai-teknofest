#!/bin/bash
# labels.tsv'de 'ele' isaretli kesitleri clips/_elenen/ altina tasir (silmez).
# Geri almak icin: mv clips/_elenen/<dosya> eski yerine, ya da ./split.py yeniden uretir.
set -u
cd "$(dirname "$0")"
n=0
while IFS=$'\t' read -r yol verdict etiket not; do
  case "$yol" in \#*|"") continue ;; esac
  [ "$verdict" = "ele" ] || continue
  [ -f "$yol" ] || continue
  dest="clips/_elenen/$(basename "$(dirname "$yol")")"
  mkdir -p "$dest"
  mv "$yol" "$dest/"
  n=$((n+1))
done < labels.tsv
echo "$n kesit clips/_elenen/ altina tasindi"
