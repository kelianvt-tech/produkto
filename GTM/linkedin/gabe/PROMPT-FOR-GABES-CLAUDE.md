# Message for Gabe

Hey Gabe, here's the LinkedIn connection agent I'm running. It sends 40 connection requests a day (Mon–Fri, 9am–5pm) from your own LinkedIn to e-commerce founders, no notes, no messages. You've got your own 547 founders (coffee & tea + pet), different brands from mine, so nobody hears from both of us.

Setup takes ~10 minutes:
1. Download the zip I'm sending you (gabe-linkedin-agent.zip) into your Downloads folder.
2. Open Claude (desktop app, Code tab). Set the mode to **Manual** (bottom left), not Auto, or it'll refuse to write the scheduler.
3. Paste everything below the line into Claude and follow along. It'll ask you to approve each step.

---

I want to set up a LinkedIn connection agent on this Mac. My co-founder Kelian built it and sent me the files. I approve sending connection requests from my own LinkedIn account. Please set it up with me step by step, explain each step in plain language, and ask me before anything sends a real request.

**The files:** `~/Downloads/gabe-linkedin-agent.zip`. Unzip it to `~/Documents/gabe-linkedin-agent/`. It contains `linkedin_agent.py` (standard-library Python, drives my own Chrome through AppleScript), two lead CSVs, and `SETUP-GABE.md`. Read `SETUP-GABE.md` and `linkedin_agent.py` before running anything.

**Steps:**
1. Check `python3 --version` works (3.9+). If macOS asks to install developer tools, tell me to click Install and wait.
2. Ask me to open Google Chrome, make sure I'm logged into LinkedIn, and turn on **View → Developer → Allow JavaScript from Apple Events**. Wait until I confirm.
3. Import the leads:
   - `python3 linkedin_agent.py import gabe-leads-coffee-and-tea.csv --niche "coffee and tea"` (expect "Added 347")
   - `python3 linkedin_agent.py import gabe-leads-pet-products.csv --niche "pet products"` (expect "Added 200")
4. Run the dry test: `python3 linkedin_agent.py test`. It opens a founder's profile and the invite window in its own Chrome window, then closes it **without sending**. If macOS asks "Terminal (or python3) wants to control Google Chrome", tell me to click OK. Success = a line containing `DRY RUN: found 'Send without a note'`. If anything else appears, stop and show me the output so I can send it to Kelian.
5. **Ask me before this step.** Send one real request while I watch: `python3 linkedin_agent.py send-one`. Then I'll check that founder's profile shows "Pending".
6. Ask me what time zone I'm in. The schedule runs 9am–5pm in `Europe/Madrid` by default. If I'm somewhere else, change `"timezone"` in `~/Library/Application Support/ProduktoLinkedIn/settings.json` (it's created on the first run) to my zone, e.g. `America/New_York`.
7. Install the schedule: `python3 linkedin_agent.py install`. The first time it runs on its own, macOS may ask "python3 wants to control Google Chrome": tell me to click OK, or it will hang.
8. Show me `python3 linkedin_agent.py status` and explain it.

**Rules, don't change these unless Kelian says so:**
- Connection requests only. Keep `"send_messages": false`.
- Keep the limits: 40 a day, 200 a week, Monday to Friday. LinkedIn restricts accounts that go higher.
- Never type or ask for my LinkedIn password. The agent uses the Chrome I'm already logged into.
- Don't run commands against the agent while its own run is going (there's a `run.lock` file in `~/Library/Application Support/ProduktoLinkedIn/` while it works).
- If LinkedIn ever shows a security check or a limit warning, the agent pauses itself and shows a Mac notification. Don't resume it; tell me to message Kelian.

**Day to day, what I'll ask you for:**
- "How many has it sent?" → run `status`.
- "Pause it" → `python3 ~/Documents/gabe-linkedin-agent/linkedin_agent.py pause`
- "Start it again" → `... resume`
