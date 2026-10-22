#!/bin/bash
# Usage: render.sh <out-dir> sheet.html [more.html ...]
# Renders each sheet (1200x1500 CSS px) at 2x to <out-dir>/<name>.png (2400x3000, LinkedIn 4:5)
# and a small preview to <out-dir>/_preview/<name>.png for checking fit.
# The HTML must sit next to d.css and logo.png (copy them from templates/).
set -e
OUT="$1"; shift
mkdir -p "$OUT/_preview"
C="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
P=$(mktemp -d)   # throwaway profile so it never touches Kelian's real Chrome
for f in "$@"; do
  n=$(basename "${f%.html}"); abs=$(cd "$(dirname "$f")" && pwd)/$(basename "$f")
  "$C" --headless=new --disable-gpu --hide-scrollbars --user-data-dir="$P" --force-device-scale-factor=2 \
       --window-size=1200,1500 --virtual-time-budget=5000 --screenshot="$OUT/$n.png" "file://$abs" >/dev/null 2>&1
  sips -Z 800 "$OUT/$n.png" --out "$OUT/_preview/$n.png" >/dev/null
  echo "$OUT/$n.png"
done
rm -rf "$P"
