#!/bin/bash
# 2026-10-06: two call scripts with a picker (default "Follow-up after email") + ringing sound removed.
# Run from the parallel-dialer folder on the Mac: bash deploy/2026-10-06-scripts/apply.sh
# Don't run it during a live call session: it restarts the dialer.
set -euo pipefail
cd "$(dirname "$0")"
KEY=~/.ssh/produkto_hetzner; HOST=root@2.28.131.206
scp -i $KEY -q scripts.patch dialer.toml $HOST:/root/
ssh -i $KEY $HOST 'set -e
cd /opt/parallel-dialer
mkdir -p /root/bak-2026-10-06-scripts && cp -a dialer.toml parallel_dialer /root/bak-2026-10-06-scripts/
patch -p4 < /root/scripts.patch
cp /root/dialer.toml dialer.toml && chown root:dialer dialer.toml && chmod 640 dialer.toml
sed -i "/const setRingback = (on) => {/a\    return; // ringing sound removed 2026-10-06 (Kelian did not like it)" parallel_dialer/static/dialer.js
sed -i "s/dialer.js?v=10/dialer.js?v=11/" parallel_dialer/templates/shell.html
.venv/bin/python -c "from parallel_dialer.profile import load_profile; print(load_profile(\"dialer.toml\").script_names())"
systemctl restart parallel-dialer && sleep 3 && systemctl is-active parallel-dialer'
echo "Done. Reload the dialer page."
