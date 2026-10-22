#!/bin/bash
# Renders each named HTML sheet to a 2400x3000 PNG (LinkedIn 4:5) with headless Chrome.
cd "$(dirname "$0")"
C="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; P=$(mktemp -d)
for f in "$@"; do n="${f%.html}"; "$C" --headless=new --disable-gpu --hide-scrollbars --user-data-dir="$P" --force-device-scale-factor=2 --window-size=1200,1500 --virtual-time-budget=5000 --screenshot="$PWD/$n.png" "file://$PWD/$f" >/dev/null 2>&1; sips -Z 800 "$n.png" --out "/private/tmp/claude-501/-Users-kelianvantulder-Desktop-Kelian-OS-AEO-for-eccomerce-brands/9ac1719f-37e6-4aae-9062-10b09dbb9b0d/scratchpad/p-$n.png" >/dev/null; done
rm -rf "$P"
