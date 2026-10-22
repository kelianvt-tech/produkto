# The AI Shelf Playbook (lead magnet)

Comment-keyword lead magnet: post the cover (`.claude/skills/cheatsheet-design/templates/lead-magnet-cover.html`) with `Comment "PLAYBOOK"`, then DM the PDF.

- Text lives in `build.py` (CHAPTERS, CHECKS). Sheets are the PNGs in `img/`.
- Rebuild:
```
python3 build.py
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --user-data-dir="$(mktemp -d)" --virtual-time-budget=8000 --no-pdf-header-footer --print-to-pdf="$PWD/The-AI-Shelf-Playbook.pdf" "file://$PWD/playbook.html"
```
