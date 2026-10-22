#!/bin/bash
# 2026-10-06: (1) script picker was white-on-white; (2) the call pop-up ran past the bottom of the
# screen (page zoom 1.15 makes 94vh taller than the window), hiding the outcome buttons.
# The buttons now stay pinned at the bottom and the middle scrolls. Restarts the dialer:
# not during a live session.
set -euo pipefail
ssh -i ~/.ssh/produkto_hetzner root@2.28.131.206 'set -e
cd /opt/parallel-dialer/parallel_dialer
cp static/dialer.css /root/dialer.css.bak-2026-10-06-fix
grep -q "keep the script picker readable" static/dialer.css || cat >> static/dialer.css <<CSS
/* The page is dark: keep the script picker readable on it. */
.dialer-script-choice { background: #1b2626; color: #e6efec; border-color: rgba(255, 255, 255, 0.2); }
.dialer-script-choice option { background: #1b2626; color: #e6efec; }
CSS
grep -q "outcome buttons always on screen" static/dialer.css || cat >> static/dialer.css <<CSS
/* Call pop-up: outcome buttons always on screen (body zoom 1.15 makes vh units 15% too tall). */
.dialer-profile-dialog { max-height: calc(94vh / 1.15); overflow: hidden; }
.dialer-modal-container { display: flex; flex-direction: column; max-height: calc(94vh / 1.15); }
.dialer-modal-container > .dialer-modal-body { flex: 1 1 auto; min-height: 0; overflow-y: auto; }
.dialer-modal-container > .dialer-modal-header, .dialer-modal-container > .dialer-modal-footer { flex: none; }
@media (min-width: 900px) {
  .dialer-modal-body > .dialer-modal-script-drawer { max-height: calc(94vh / 1.15 - 190px); }
}
CSS
sed -i -E "s/dialer.css\?v=[0-9]+/dialer.css?v=12/" templates/shell.html
systemctl restart parallel-dialer && sleep 3 && systemctl is-active parallel-dialer'
echo "Done. Reload the dialer page (Cmd+Shift+R)."
# Drop the "only for emailed leads" line from the default script (Kelian, 2026-10-06).
ssh -i ~/.ssh/produkto_hetzner root@2.28.131.206 "sed -i '/Only for people who really got email 1/d' /opt/parallel-dialer/dialer.toml && systemctl restart parallel-dialer"
