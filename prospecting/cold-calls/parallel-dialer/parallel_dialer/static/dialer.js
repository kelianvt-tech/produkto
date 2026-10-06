(() => {
  "use strict";

  const app = document.getElementById("dialer-app");
  if (!app) return;

  const byId = (id) => document.getElementById(id);
  // What this deployment says in its own voice (dialer.toml), rendered into the page by
  // the server: the brand, the talk track and the screening reply.
  const profile = (() => {
    try {
      return JSON.parse(byId("dialer-profile")?.textContent || "{}") || {};
    } catch (_e) {
      return {};
    }
  })();
  const rows = Array.from(document.querySelectorAll(".dialer-contact"));
  const maxConcurrency = Math.min(10, Number(app.dataset.maxConcurrency || 10));
  const liveReady = app.dataset.liveReady === "true";
  const operatorEmail = app.dataset.operatorEmail || "";
  const operatorName = app.dataset.operatorName || "";
  const smartViewId = app.dataset.smartViewId || "";
  const smartViewName = app.dataset.smartViewName || "Close Smart View";
  const activeSessionId = app.dataset.activeSessionId || "";
  const activeSmartViewId = app.dataset.activeSmartViewId || "";
  let progressAttempted = Number(app.dataset.progressAttempted || 0);
  let progressRemaining = Number(app.dataset.progressRemaining || 0);
  const contacts = rows.length
    ? rows.map((row, index) => ({
        key: row.dataset.contactId || `${row.dataset.leadId}-${index}`,
        contactId: row.dataset.contactId || "",
        leadId: row.dataset.leadId || "",
        name: row.dataset.name || "Close contact",
        company: row.dataset.company || "Close CRM",
        scriptFields: (() => { try { return JSON.parse(row.dataset.script || "{}"); } catch (_e) { return {}; } })(),
        phone: row.dataset.phone || "",
        email: row.dataset.email || "",
        liveAllowed: row.dataset.liveAllowed === "true",
        attempted: row.dataset.attempted === "true",
        row,
      }))
    : [];

  const state = {
    attempts: 0,
    batches: 0,
    connected: 0,
    abandoned: 0,
    completed: new Set(),
    outcomes: [],
    running: false,
    bridged: null,
    timers: [],
    currentLines: [],
    lineCards: new Map(),
    liveSessionId: "",
    pollTimer: 0,
    renderedLiveOutcomes: new Set(),
    modalDismissedByUser: false,
  };

  if (activeSessionId && activeSmartViewId && activeSmartViewId !== smartViewId) {
    const activeUrl = new URL(window.location.href);
    activeUrl.searchParams.set("smart_view_id", activeSmartViewId);
    window.location.replace(activeUrl.toString());
    return;
  }

  const formatPhone = (num) => {
    if (!num) return "";
    const clean = String(num).replace(/[^\d+]/g, "");
    if (clean.startsWith("+1") && clean.length === 12) {
      return `+1 (${clean.slice(2, 5)}) ${clean.slice(5, 8)}-${clean.slice(8)}`;
    }
    if (clean.length === 10) {
      return `(${clean.slice(0, 3)}) ${clean.slice(3, 6)}-${clean.slice(6)}`;
    }
    return num;
  };

  const outcomeCopy = {
    queued: ["Queued", "Waiting for Twilio"],
    initiated: ["Calling", "Dial request accepted"],
    ringing: ["Ringing", "Waiting for an answer"],
    "in-progress": ["Answered", "Classifying the answer"],
    screening: ["Screening gate", "Playing your gatekeeper reply"],
    bridging: ["Human", "Joining the waiting operator"],
    bridged: ["Connected", "Live conversation active"],
    "human-detected": ["Human detected", "Joining the waiting operator"],
    "human-bridged": ["Connected", "Operator connected immediately"],
    "operator-connecting": ["Get ready", "Answer your phone to begin dialing"],
    "operator-unavailable": ["Operator unavailable", "The handoff did not connect"],
    "operator-no-answer": ["Operator unavailable", "The operator did not answer"],
    "operator-busy": ["Operator busy", "The operator line was busy"],
    "operator-failed": ["Handoff failed", "The operator call could not be routed"],
    "operator-canceled": ["Handoff canceled", "The operator call was canceled"],
    "operator-unknown": ["Handoff unknown", "The operator result was unavailable"],
    "voicemail-waiting": ["Voicemail", "Waiting for the greeting to finish"],
    "voicemail-playing": ["Voicemail", "Playing your recording"],
    voicemail: ["Voicemail", "Your recording was left"],
    hangup: ["Hung up", "Recipient ended the call"],
    busy: ["Busy", "Destination was busy"],
    "no-answer": ["No answer", "Ring timeout"],
    failed: ["Carrier error", "Call could not be completed by carrier"],
    invalid: ["Disconnected / Invalid", "Number out of service (Carrier 404)"],
    unclassified: ["Unclassified", "No confident live answer"],
    completed: ["Completed", "Call ended"],
    canceled: ["Canceled", "Stopped by the operator"],
    "canceled-after-human": ["Canceled", "Another line reached a human"],
    "dropped-line": ["Dropped line", "Answered but lost operator race; queued first"],
    abandoned: ["Abandoned", "Human answered but operator was unavailable"],
    "provider-error": ["Invalid format", "Twilio rejected destination format"],
    human: ["Human", "Live answer; operator handoff started"],
    ivr: ["Phone tree", "Automated menu / extension required"],
    "mailbox-full": ["Mailbox full", "Recipient mailbox is full"],
  };
  const terminalStatuses = new Set([
    "abandoned",
    "busy",
    "canceled",
    "completed",
    "dropped-line",
    "failed",
    "invalid",
    "provider-error",
    "no-answer",
    "ivr",
    "mailbox-full",
    "voicemail",
    "voicemail-playing",
  ]);

  const playConnectChime = () => {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      if (ctx.state === "suspended") {
        ctx.resume().catch(() => {});
      }
      const now = ctx.currentTime;
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = "sine";
      osc1.frequency.setValueAtTime(587.33, now); // D5
      gain1.gain.setValueAtTime(0.18, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.22);

      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = "sine";
      osc2.frequency.setValueAtTime(880, now + 0.11); // A5
      gain2.gain.setValueAtTime(0.22, now + 0.11);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.start(now + 0.11);
      osc2.stop(now + 0.45);
    } catch (_e) {}
  };

  const addTimer = (callback, delay) => {
    const id = window.setTimeout(callback, delay);
    state.timers.push(id);
    return id;
  };
  const clearTimers = () => {
    state.timers.forEach((id) => window.clearTimeout(id));
    state.timers = [];
    if (state.pollTimer) window.clearTimeout(state.pollTimer);
    state.pollTimer = 0;
  };
  const percent = (count, total) => (total ? `${((count / total) * 100).toFixed(1)}%` : "0.0%");
  const initials = (name) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  const visibleContacts = () => contacts.filter((contact) => !contact.row || !contact.row.hidden);
  const availableLiveContacts = () => visibleContacts().filter((contact) => contact.liveAllowed && !contact.attempted);

  const updateMetrics = (sessionStats = null) => {
    const eligible = availableLiveContacts();
    byId("dialer-ready-count").textContent = String(eligible.length);
    byId("dialer-visible-count").textContent = String(visibleContacts().length);
    byId("dialer-active-count").textContent = String(state.currentLines.filter((line) => line.pending).length);

    let connected = state.connected;
    let attemptsCount = state.attempts;
    let humanMissed = state.abandoned || 0;
    let totalHuman = connected + humanMissed;

    if (sessionStats) {
      if (sessionStats.attempts !== undefined) attemptsCount = sessionStats.attempts;
      if (sessionStats.human_answered !== undefined) connected = Math.max(connected, sessionStats.human_answered);
      if (sessionStats.human_missed !== undefined) humanMissed = Math.max(humanMissed, sessionStats.human_missed);
      if (sessionStats.human_connects !== undefined) totalHuman = Math.max(totalHuman, sessionStats.human_connects);
    }

    const connectRate = attemptsCount ? Math.round((connected / attemptsCount) * 100) : 0;
    const connectRateEl = byId("dialer-connect-rate");
    if (connectRateEl) connectRateEl.textContent = `${connectRate}%`;
    const connectDetailEl = byId("dialer-connect-detail");
    if (connectDetailEl) {
      connectDetailEl.textContent = attemptsCount
        ? `${connected} connected from ${attemptsCount} attempt${attemptsCount === 1 ? "" : "s"}`
        : "No attempts yet";
    }

    const abandonRate = totalHuman ? Math.round((humanMissed / totalHuman) * 100) : 0;
    const abandonRateEl = byId("dialer-abandon-rate");
    if (abandonRateEl) abandonRateEl.textContent = `${abandonRate}%`;
    const abandonDetailEl = byId("dialer-abandon-detail");
    if (abandonDetailEl) {
      abandonDetailEl.textContent = totalHuman
        ? `${humanMissed} missed from ${totalHuman} connect${totalHuman === 1 ? "" : "s"}`
        : "0 missed from 0 connects";
    }
    const abandonTrendEl = byId("dialer-abandon-trend");
    if (abandonTrendEl) {
      if (humanMissed > 0) {
        abandonTrendEl.textContent = `${humanMissed} missed`;
        abandonTrendEl.className = "trend down";
      } else {
        abandonTrendEl.textContent = "This session";
        abandonTrendEl.className = "trend neutral";
      }
    }

    const invalid = state.outcomes.filter((item) => ["invalid", "failed", "provider-error"].includes(item.type)).length;
    const blocked = state.outcomes.filter((item) => item.type === "busy").length;
    const short = state.outcomes.filter((item) => ["hangup", "canceled", "canceled-after-human", "abandoned"].includes(item.type)).length;
    const signalBasisEl = byId("dialer-signal-basis");
    if (signalBasisEl) {
      signalBasisEl.textContent = attemptsCount
        ? `From ${attemptsCount} attempt${attemptsCount === 1 ? "" : "s"}`
        : "No attempts yet";
    }
    const blockRateEl = byId("dialer-block-rate");
    if (blockRateEl) blockRateEl.textContent = percent(blocked, attemptsCount);
    const shortRateEl = byId("dialer-short-rate");
    if (shortRateEl) shortRateEl.textContent = percent(short, attemptsCount);
    const invalidRateEl = byId("dialer-invalid-rate");
    if (invalidRateEl) invalidRateEl.textContent = percent(invalid, attemptsCount);
  };

  const buildLine = (contact, number, attemptId = "", attempt = {}) => {
    const initialType = attempt.outcome || attempt.status || "queued";
    const [initialLabel, initialDetail] = copyFor(initialType, attempt.status, attempt);
    const card = document.createElement("article");
    card.className = `dialer-line ${initialType}`;
    if (attemptId) card.dataset.attemptId = attemptId;

    // Header
    const header = document.createElement("div");
    header.className = "dialer-line-header";

    const badge = document.createElement("span");
    badge.className = "dialer-line-badge";
    badge.textContent = `Line ${number}`;

    const callerBadge = document.createElement("span");
    callerBadge.className = "dialer-line-caller-badge";
    const clLabel = attempt.caller_label || `Number ${number}`;
    const clNum = attempt.caller_number ? ` (${formatPhone(attempt.caller_number)})` : "";
    if (attempt.caller_health && attempt.caller_health.status) {
      const hDot = document.createElement("span");
      hDot.className = `health-badge ${attempt.caller_health.status}`;
      hDot.textContent = attempt.caller_health.badge || "●";
      callerBadge.append(hDot);
    }
    const callerTextNode = document.createTextNode(`${clLabel}${clNum}`);
    callerBadge.append(callerTextNode);
    callerBadge.title = `Outbound Caller ID: ${attempt.caller_number || "Dedicated number"}`;

    const statusPill = document.createElement("span");
    statusPill.className = `dialer-line-status-pill ${initialType}`;
    const statusDot = document.createElement("i");
    statusDot.className = "dialer-status-dot";
    const statusName = document.createElement("b");
    statusName.className = "dialer-status-label";
    statusName.textContent = initialLabel;
    statusPill.append(statusDot, statusName);

    const debugBtn = document.createElement("button");
    debugBtn.type = "button";
    debugBtn.className = "dialer-line-debug-btn";
    debugBtn.textContent = "{ } Debug";
    debugBtn.title = "Toggle call debug diagnostics";

    header.append(badge, callerBadge, statusPill, debugBtn);

    // Main Contact Info
    const main = document.createElement("div");
    main.className = "dialer-line-main";

    const avatar = document.createElement("div");
    avatar.className = "dialer-line-avatar";
    avatar.textContent = initials(contact.name || "CC");

    const identity = document.createElement("div");
    identity.className = "dialer-line-identity";

    const name = document.createElement("strong");
    name.className = "dialer-line-name";
    name.textContent = contact.name || "Close contact";

    const company = document.createElement("span");
    company.className = "dialer-line-company";
    company.textContent = [contact.title, contact.company || "Close CRM"].filter(Boolean).join(" · ");

    const phone = document.createElement("span");
    phone.className = "dialer-line-phone";
    phone.textContent = contact.phone_masked || contact.phone || "—";

    identity.append(name, company, phone);
    main.append(avatar, identity);

    // Detail footer
    const detailWrap = document.createElement("div");
    detailWrap.className = "dialer-line-detail";
    const statusDetail = document.createElement("span");
    statusDetail.className = "dialer-line-desc";
    statusDetail.textContent = initialDetail;
    detailWrap.append(statusDetail);

    // Collapsible debug drawer
    const debugDrawer = document.createElement("div");
    debugDrawer.className = "dialer-line-debug-drawer";
    debugDrawer.hidden = true;

    debugBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      debugDrawer.hidden = !debugDrawer.hidden;
      debugBtn.textContent = debugDrawer.hidden ? "{ } Debug" : "Hide Debug";
    });

    const updateDebugDrawer = (att) => {
      debugDrawer.replaceChildren();
      const grid = document.createElement("div");
      grid.className = "debug-grid";
      const fields = [
        ["Line Caller ID", `${att.caller_label || "Number"} (${formatPhone(att.caller_number) || "Pending"})`],
        ["Twilio SID", att.twilio_call_sid || "Pending..."],
        ["AMD Result", att.answered_by || "Listening..."],
        ["Twilio Status", att.twilio_status || att.status || "queued"],
        ["Dialer Outcome", att.outcome || "Pending"],
        ["Duration", att.duration != null ? `${att.duration}s` : "0s"],
        ["Voicemail AMD", att.voicemail_detected ? "Yes" : "No"],
      ];
      fields.forEach(([k, v]) => {
        const item = document.createElement("div");
        const lbl = document.createElement("span");
        lbl.textContent = k;
        const val = document.createElement("code");
        val.textContent = String(v);
        item.append(lbl, val);
        grid.append(item);
      });
      debugDrawer.append(grid);
    };
    updateDebugDrawer(attempt);

    card.append(header, main, detailWrap, debugDrawer);
    return {
      card,
      contact,
      statusName,
      statusDetail,
      statusPill,
      badge,
      callerBadge,
      debugDrawer,
      updateDebugDrawer,
      pending: true,
      attemptId,
      number,
    };
  };

  const buildExpandedHero = (attempt, session, siblingAttempts = []) => {
    const card = document.createElement("article");
    card.className = "dialer-line human-bridged expanded";
    if (attempt.id) card.dataset.attemptId = attempt.id;

    // 1. Hero Header
    const heroHeader = document.createElement("div");
    heroHeader.className = "dialer-expanded-hero-header";

    const liveBadge = document.createElement("div");
    liveBadge.className = "dialer-expanded-live-badge";
    const dot = document.createElement("i");
    const liveText = document.createElement("span");
    liveText.textContent = "Live Conversation Connected";
    liveBadge.append(dot, liveText);

    const timerBox = document.createElement("div");
    timerBox.className = "dialer-expanded-timer-box";
    const timerLabel = document.createElement("span");
    timerLabel.className = "dialer-expanded-timer-label";
    timerLabel.textContent = "Duration";
    const timer = document.createElement("time");
    timer.id = "dialer-expanded-timer";
    timer.className = "dialer-expanded-timer";
    const secs = bridgeStartedAt ? Math.floor((Date.now() - bridgeStartedAt) / 1000) : 0;
    const mins = Math.floor(secs / 60);
    const rem = secs % 60;
    timer.textContent = `${String(mins).padStart(2, "0")}:${String(rem).padStart(2, "0")}`;
    timerBox.append(timerLabel, timer);

    heroHeader.append(liveBadge, timerBox);

    // 2. Hero Content
    const content = document.createElement("div");
    content.className = "dialer-expanded-content";

    // Left Column: Profile
    const profile = document.createElement("div");
    profile.className = "dialer-expanded-profile";

    const avatar = document.createElement("div");
    avatar.className = "dialer-expanded-avatar";
    avatar.textContent = initials(attempt.name || "CC");

    const details = document.createElement("div");
    details.className = "dialer-expanded-details";

    const name = document.createElement("h3");
    name.className = "dialer-expanded-name";
    name.textContent = attempt.name || "Close contact";

    const role = document.createElement("p");
    role.className = "dialer-expanded-role";
    role.textContent = [attempt.title, attempt.company || "Close CRM"].filter(Boolean).join(" · ");

    const meta = document.createElement("div");
    meta.className = "dialer-expanded-meta";

    const phoneBadge = document.createElement("span");
    phoneBadge.className = "dialer-phone-badge";
    phoneBadge.textContent = attempt.phone_masked || attempt.phone || "—";

    const statusBadge = document.createElement("span");
    statusBadge.className = "dialer-status-badge";
    statusBadge.textContent = attempt.lead_status || "Active Lead";

    meta.append(phoneBadge, statusBadge);

    if (attempt.caller_number) {
      const lineCallerBadge = document.createElement("span");
      lineCallerBadge.className = "dialer-phone-badge";
      const clLabel = attempt.caller_label || "Number";
      lineCallerBadge.textContent = `Via: ${clLabel} (${formatPhone(attempt.caller_number)})`;
      lineCallerBadge.title = `Outbound line: ${attempt.caller_number}`;
      meta.append(lineCallerBadge);
    }

    details.append(name, role, meta);

    const linksRow = document.createElement("div");
    linksRow.className = "dialer-hero-links-row";

    if (attempt.close_url && /^https:\/\/app\.close\.com\//.test(attempt.close_url)) {
      const openBtn = document.createElement("a");
      openBtn.className = "dialer-btn-open-close";
      openBtn.href = attempt.close_url;
      openBtn.target = "_blank";
      openBtn.rel = "noopener";
      openBtn.textContent = "Open in Close CRM ↗";
      linksRow.append(openBtn);
    }

    const heroLinkedinUrl = attempt.linkedin_url || (attempt.name ? `https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent([attempt.name, attempt.company].filter(Boolean).join(" "))}` : "");
    if (heroLinkedinUrl) {
      const linkedinBtn = document.createElement("a");
      linkedinBtn.className = "dialer-btn-open-linkedin";
      linkedinBtn.href = heroLinkedinUrl;
      linkedinBtn.target = "_blank";
      linkedinBtn.rel = "noopener";
      linkedinBtn.textContent = "LinkedIn ↗";
      linksRow.append(linkedinBtn);
    }

    if (linksRow.hasChildNodes()) {
      details.append(linksRow);
    }

    profile.append(avatar, details);

    // Right Column: Call Console (Mic meter + Controls)
    const consoleBox = document.createElement("div");
    consoleBox.className = "dialer-expanded-console";

    const micWrap = document.createElement("div");
    micWrap.className = "dialer-card-mic-meter";

    const micHead = document.createElement("div");
    micHead.className = "dialer-card-mic-head";
    const micLabel = document.createElement("span");
    micLabel.textContent = "🎙️ Microphone Input";
    const micStatus = document.createElement("span");
    micStatus.id = "dialer-card-mic-status";
    micStatus.textContent = "Auto-gain on";
    micHead.append(micLabel, micStatus);

    const micTrack = document.createElement("div");
    micTrack.className = "dialer-card-mic-track";
    const micFill = document.createElement("div");
    micFill.id = "dialer-card-mic-fill";
    micFill.className = "dialer-card-mic-fill";
    micTrack.append(micFill);

    micWrap.append(micHead, micTrack);

    const actions = document.createElement("div");
    actions.className = "dialer-card-call-actions";

    const muteBtn = document.createElement("button");
    muteBtn.type = "button";
    muteBtn.id = "dialer-card-mute-btn";
    muteBtn.className = "dialer-card-btn-mute";
    const isMuted = activeCall ? activeCall.isMuted() : false;
    muteBtn.textContent = isMuted ? "Unmute" : "Mute";
    muteBtn.addEventListener("click", () => {
      const deskMute = byId("dialer-mute");
      if (deskMute) deskMute.click();
      const nowMuted = activeCall ? activeCall.isMuted() : false;
      muteBtn.textContent = nowMuted ? "Unmute" : "Mute";
    });

    const completeBtn = document.createElement("button");
    completeBtn.type = "button";
    completeBtn.className = "dialer-card-btn-complete dialer-card-btn-hangup";
    completeBtn.innerHTML = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:5px;vertical-align:-2px"><path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7 2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-6-6 19.8 19.8 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91"/></svg><span>Hang up &amp; next call</span>';
    completeBtn.addEventListener("click", () => {
      completeLiveCall();
    });

    const profileModalBtn = document.createElement("button");
    profileModalBtn.type = "button";
    profileModalBtn.className = "dialer-card-btn-popout";
    profileModalBtn.textContent = "Open contact pop-up ⤢";
    profileModalBtn.addEventListener("click", () => {
      state.modalDismissedByUser = false;
      showProfileModal(attempt);
    });

    actions.append(muteBtn, completeBtn, profileModalBtn);
    consoleBox.append(micWrap, actions);

    content.append(profile, consoleBox);

    // 3. Debug drawer toggle on the hero card
    const debugWrap = document.createElement("div");
    debugWrap.style.marginTop = "10px";
    const debugToggle = document.createElement("button");
    debugToggle.type = "button";
    debugToggle.className = "dialer-line-debug-btn";
    debugToggle.textContent = "{ } Call Diagnostics";

    const debugDrawer = document.createElement("div");
    debugDrawer.className = "dialer-line-debug-drawer";
    debugDrawer.hidden = true;

    debugToggle.addEventListener("click", () => {
      debugDrawer.hidden = !debugDrawer.hidden;
      debugToggle.textContent = debugDrawer.hidden ? "{ } Call Diagnostics" : "Hide Diagnostics";
    });

    const debugGrid = document.createElement("div");
    debugGrid.className = "debug-grid";
    [
      ["Twilio SID", attempt.twilio_call_sid || "—"],
      ["AMD Result", attempt.answered_by || "human"],
      ["Operator Status", attempt.operator_status || "connected"],
      ["Dialer Outcome", attempt.outcome || "human-bridged"],
      ["Duration", `${attempt.duration || 0}s`],
      ["Attempt ID", attempt.id || "—"],
    ].forEach(([k, v]) => {
      const item = document.createElement("div");
      const lbl = document.createElement("span");
      lbl.textContent = k;
      const val = document.createElement("code");
      val.textContent = String(v);
      item.append(lbl, val);
      debugGrid.append(item);
    });
    debugDrawer.append(debugGrid);
    debugWrap.append(debugToggle, debugDrawer);

    card.append(heroHeader, content, debugWrap);

    // 4. Sibling wave container underneath if any sibling lines exist
    let siblingSection = null;
    if (siblingAttempts && siblingAttempts.length > 0) {
      siblingSection = document.createElement("div");
      siblingSection.className = "dialer-sibling-wave";
      const sibTitle = document.createElement("span");
      sibTitle.className = "dialer-sibling-title";
      sibTitle.textContent = "Parallel lines dialed in this wave:";
      const sibList = document.createElement("div");
      sibList.className = "dialer-sibling-list";

      siblingAttempts.forEach((sib, idx) => {
        const sibCard = document.createElement("div");
        sibCard.className = "dialer-sibling-card";

        const top = document.createElement("div");
        top.className = "dialer-sibling-top";
        const sibBadge = document.createElement("span");
        sibBadge.className = "dialer-line-badge";
        sibBadge.textContent = `Line ${idx + 2}`;

        const sibName = document.createElement("strong");
        sibName.className = "dialer-sibling-name";
        sibName.textContent = sib.name || "Close contact";

        const sibDebugBtn = document.createElement("button");
        sibDebugBtn.type = "button";
        sibDebugBtn.className = "dialer-line-debug-btn";
        sibDebugBtn.textContent = "{ } Debug";

        top.append(sibBadge, sibName, sibDebugBtn);

        const sibStatus = document.createElement("span");
        sibStatus.className = "dialer-sibling-status";
        const [label, detail] = copyFor(sib.outcome || sib.status || "queued", sib.status, sib);
        sibStatus.textContent = `${label} · ${detail}`;

        const sibDebugDrawer = document.createElement("div");
        sibDebugDrawer.className = "dialer-line-debug-drawer";
        sibDebugDrawer.hidden = true;

        sibDebugBtn.addEventListener("click", () => {
          sibDebugDrawer.hidden = !sibDebugDrawer.hidden;
          sibDebugBtn.textContent = sibDebugDrawer.hidden ? "{ } Debug" : "Hide";
        });

        const sGrid = document.createElement("div");
        sGrid.className = "debug-grid";
        [
          ["Twilio SID", sib.twilio_call_sid || "—"],
          ["AMD", sib.answered_by || "—"],
          ["Outcome", sib.outcome || sib.status || "—"],
          ["Duration", `${sib.duration || 0}s`],
        ].forEach(([k, v]) => {
          const item = document.createElement("div");
          const l = document.createElement("span");
          l.textContent = k;
          const val = document.createElement("code");
          val.textContent = String(v);
          item.append(l, val);
          sGrid.append(item);
        });
        sibDebugDrawer.append(sGrid);

        sibCard.append(top, sibStatus, sibDebugDrawer);
        sibList.append(sibCard);
      });

      siblingSection.append(sibTitle, sibList);
    }

    return { card, siblingSection };
  };


  const addActivity = (contact, type, label, detail) => {
    const container = byId("dialer-activity");
    const empty = container.querySelector(".dialer-activity-empty");
    if (empty) empty.remove();
    const item = document.createElement("div");
    item.className = `dialer-activity-row ${type}`;
    const icon = document.createElement("i");
    const identity = document.createElement("span");
    const name = document.createElement("b");
    name.textContent = contact.name;
    const company = document.createElement("small");
    company.textContent = contact.company;
    identity.append(name, company);
    const result = document.createElement("span");
    const resultName = document.createElement("b");
    resultName.textContent = label;
    const resultDetail = document.createElement("small");
    resultDetail.textContent = detail;
    result.append(resultName, resultDetail);
    const time = document.createElement("time");
    time.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    item.append(icon, identity, result, time);
    container.prepend(item);
  };
  const copyFor = (type, status = "", attempt = null) => {
    if (type === "invalid" || status === "invalid") {
      if (attempt && (attempt.error_code === "13224" || attempt.sip_response_code === "404")) {
        return ["Disconnected", "Number out of service (Carrier 404)"];
      }
      if (attempt && attempt.error_code) {
        return ["Invalid number", `Invalid destination (Twilio ${attempt.error_code})`];
      }
      return ["Disconnected / Invalid", "Number out of service (Carrier 404)"];
    }
    if (type === "failed" || status === "failed") {
      if (attempt && attempt.error_code) {
        return ["Carrier error", `Carrier rejected call (${attempt.error_code})`];
      }
      return ["Carrier error", "Call could not be completed by carrier"];
    }
    return outcomeCopy[type] || outcomeCopy[status] || ["Updated", status || "Call state changed"];
  };

  let bridgeTimer = null;
  let bridgeStartedAt = 0;
  let lastBridgedContact = null;

  // --- Call Script Notepad Engine ---
  const SCRIPT_STORAGE_KEY = "parallel_dialer_script_notepad";
  const SCRIPT_COLLAPSED_KEY = "parallel_dialer_script_collapsed";
  const DEFAULT_COLD_CALL_SCRIPT = profile.script || "";

  let scriptAutoSaveTimer = 0;

  // The pop-up's copy of the script is for reading while you talk: rendered, large and
  // filled in for the person on the line. "Edit" swaps in the same notepad textarea.
  const renderModalScript = () => {
    const view = byId("dialer-modal-script-view");
    const pad = byId("dialer-modal-script-pad") || byId("dialer-script-pad");
    const script = window.DialerCallScript;
    if (!view || !pad) return;
    if (!script) {
      view.textContent = pad.value;
      return;
    }
    const contact = lastBridgedContact || {};
    const company = contact.company && contact.company !== "Close CRM" ? contact.company : "";
    const match = contacts.find(
      (item) =>
        (contact.contact_id && item.contactId === contact.contact_id) ||
        (contact.contactId && item.contactId === contact.contactId) ||
        (contact.lead_id && item.leadId === contact.lead_id) ||
        (contact.phone && item.phone === contact.phone)
    );
    view.innerHTML = script.render(pad.value, {
      name: script.firstName(contact.name),
      me: script.firstName(operatorName),
      company,
      ...((match && match.scriptFields) || contact.script_fields || {}),
    });
  };

  const updateScriptMeta = (text) => {
    const metaEl = byId("dialer-script-meta");
    if (!metaEl) return;
    const trimmed = (text || "").trim();
    const chars = (text || "").length;
    const words = trimmed ? trimmed.split(/\\s+/).length : 0;
    metaEl.textContent = `${words} words • ${chars} characters`;
  };

  const setScriptStatus = (statusText, isSaving = false) => {
    const badges = [byId("dialer-script-status"), byId("dialer-modal-script-status")];
    badges.forEach((b) => {
      if (!b) return;
      b.textContent = statusText;
      if (isSaving) {
        b.classList.add("saving");
      } else {
        b.classList.remove("saving");
      }
    });
  };

  const saveScriptToServer = async (text) => {
    try {
      await apiRequest("/dialer/api/talk-track", {
        method: "PUT",
        body: JSON.stringify({ script: text }),
      });
      setScriptStatus("Saved ✓", false);
    } catch (_err) {
      setScriptStatus("Saved (offline)", false);
    }
  };

  // If the server holds a talk track for this operator and this browser has none of its own
  // yet, take the server's.
  const fetchTalkTrack = async () => {
    try {
      const res = await apiRequest("/dialer/api/talk-track");
      if (!res || !res.script) return;
      if (localStorage.getItem(SCRIPT_STORAGE_KEY)) return;
      try { localStorage.setItem(SCRIPT_STORAGE_KEY, res.script); } catch (_e) {}
      const padMain = byId("dialer-script-pad");
      const padModal = byId("dialer-modal-script-pad");
      if (padMain) padMain.value = res.script;
      if (padModal) padModal.value = res.script;
      updateScriptMeta(res.script);
      renderModalScript();
    } catch (_e) {}
  };

  const handleScriptInput = (sourceEl) => {
    const newText = sourceEl.value;
    const padMain = byId("dialer-script-pad");
    const padModal = byId("dialer-modal-script-pad");

    if (sourceEl === padMain && padModal && padModal.value !== newText) {
      padModal.value = newText;
    } else if (sourceEl === padModal && padMain && padMain.value !== newText) {
      padMain.value = newText;
    }

    updateScriptMeta(newText);
    renderModalScript();
    setScriptStatus("Saving...", true);

    try {
      localStorage.setItem(SCRIPT_STORAGE_KEY, newText);
    } catch (_e) {}

    clearTimeout(scriptAutoSaveTimer);
    scriptAutoSaveTimer = setTimeout(() => {
      saveScriptToServer(newText);
    }, 450);
  };

  const initScriptNotepad = () => {
    const padMain = byId("dialer-script-pad");
    const padModal = byId("dialer-modal-script-pad");
    if (!padMain && !padModal) return;

    let initialScript = "";
    try {
      initialScript = localStorage.getItem(SCRIPT_STORAGE_KEY) || "";
    } catch (_e) {}

    if (!initialScript) {
      initialScript = DEFAULT_COLD_CALL_SCRIPT;
      try {
        localStorage.setItem(SCRIPT_STORAGE_KEY, initialScript);
      } catch (_e) {}
    }

    if (padMain) padMain.value = initialScript;
    if (padModal) padModal.value = initialScript;
    updateScriptMeta(initialScript);
    renderModalScript();
    setScriptStatus("Saved", false);

    const onInputHandler = (e) => handleScriptInput(e.target);
    if (padMain) padMain.addEventListener("input", onInputHandler);
    if (padModal) padModal.addEventListener("input", onInputHandler);

    const handleCopy = async (btn) => {
      const current = (padMain ? padMain.value : "") || (padModal ? padModal.value : "");
      try {
        await navigator.clipboard.writeText(current);
        const orig = btn.textContent;
        btn.textContent = "Copied!";
        setTimeout(() => {
          btn.textContent = orig;
        }, 1500);
      } catch (_err) {
        const orig = btn.textContent;
        btn.textContent = "Copied!";
        setTimeout(() => {
          btn.textContent = orig;
        }, 1500);
      }
    };

    const copyBtn = byId("dialer-script-copy-btn");
    if (copyBtn) copyBtn.addEventListener("click", () => handleCopy(copyBtn));

    const modalCopyBtn = byId("dialer-modal-script-copy-btn");
    if (modalCopyBtn) modalCopyBtn.addEventListener("click", () => handleCopy(modalCopyBtn));

    const resetBtn = byId("dialer-script-reset-btn");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        if (window.confirm("Reset the call script to the default talk track?")) {
          if (padMain) padMain.value = DEFAULT_COLD_CALL_SCRIPT;
          if (padModal) padModal.value = DEFAULT_COLD_CALL_SCRIPT;
          handleScriptInput(padMain || padModal);
        }
      });
    }

    // Open unless this operator closed it: reading it is the point of having it here.
    const drawer = byId("dialer-modal-script-drawer");
    const toggleBtn = byId("dialer-modal-script-toggle");
    const setCollapsed = (collapsed) => {
      if (drawer) drawer.classList.toggle("collapsed", collapsed);
      if (toggleBtn) toggleBtn.setAttribute("aria-expanded", String(!collapsed));
    };
    let collapsed = false;
    try {
      collapsed = localStorage.getItem(SCRIPT_COLLAPSED_KEY) === "1";
    } catch (_e) {}
    setCollapsed(collapsed);
    if (toggleBtn && drawer) {
      toggleBtn.addEventListener("click", () => {
        const next = !drawer.classList.contains("collapsed");
        setCollapsed(next);
        try {
          localStorage.setItem(SCRIPT_COLLAPSED_KEY, next ? "1" : "0");
        } catch (_e) {}
      });
    }

    const drawerBody = byId("dialer-modal-script-body");
    const view = byId("dialer-modal-script-view");
    const editBtn = byId("dialer-modal-script-edit-btn");
    if (editBtn && drawerBody && view) {
      editBtn.addEventListener("click", () => {
        const editing = drawerBody.hidden;
        if (editing) setCollapsed(false);
        drawerBody.hidden = !editing;
        view.hidden = editing;
        editBtn.textContent = editing ? "Done" : "Edit";
        if (editing && padModal) padModal.focus();
        else renderModalScript();
      });
    }
  };

  const notesCache = new Map();

  const renderPreviousCallNotes = (data) => {
    const notesBox = byId("dialer-modal-notes-box");
    const notesList = byId("dialer-notes-list");
    const countBadge = byId("dialer-notes-count-badge");
    if (!notesBox || !notesList) return;

    if (!data || !data.has_called_before || !Array.isArray(data.call_notes) || data.call_notes.length === 0) {
      notesBox.hidden = true;
      notesList.replaceChildren();
      return;
    }

    const total = data.total_calls || data.call_notes.length;
    if (countBadge) {
      countBadge.textContent = total === 1 ? "1 previous call" : `${total} previous calls`;
    }

    const entries = data.call_notes.map((call) => {
      const entry = document.createElement("div");
      entry.className = "dialer-note-entry";

      const meta = document.createElement("div");
      meta.className = "dialer-note-meta";

      const dateEl = document.createElement("span");
      dateEl.className = "dialer-note-date";
      dateEl.textContent = call.date_formatted || call.relative_date || call.date || "Past call";

      meta.appendChild(dateEl);

      const repDetails = [call.duration_formatted, call.user_name].filter(Boolean).join(" · ");
      if (repDetails) {
        const durEl = document.createElement("span");
        durEl.className = "dialer-note-duration";
        durEl.textContent = repDetails;
        meta.appendChild(durEl);
      }

      const textEl = document.createElement("div");
      textEl.className = "dialer-note-text";
      textEl.textContent = call.note || "Call completed (no notes recorded)";

      entry.appendChild(meta);
      entry.appendChild(textEl);
      return entry;
    });

    notesList.replaceChildren(...entries);
    notesBox.hidden = false;
  };

  const loadPreviousCallNotes = async (contact) => {
    const notesBox = byId("dialer-modal-notes-box");
    const notesList = byId("dialer-notes-list");
    if (!notesBox || !notesList) return;

    const contactId = contact.contact_id || contact.contactId || contact.id || "";
    const leadId = contact.lead_id || contact.leadId || "";
    const phone = contact.phone || "";

    if (!contactId && !leadId && !phone) {
      notesBox.hidden = true;
      notesList.replaceChildren();
      return;
    }

    const cacheKey = `${contactId}:${leadId}:${phone}`;
    if (notesCache.has(cacheKey)) {
      renderPreviousCallNotes(notesCache.get(cacheKey));
      return;
    }

    // Default to hidden while fetching
    notesBox.hidden = true;

    try {
      const q = new URLSearchParams();
      if (leadId) q.set("lead_id", leadId);
      if (phone) q.set("phone", phone);
      const url = `/dialer/api/contacts/${encodeURIComponent(contactId || "unknown")}/call-notes?${q.toString()}`;
      const res = await fetch(url, { headers: { Accept: "application/json" } });
      if (!res.ok) return;
      const data = await res.json();
      notesCache.set(cacheKey, data);
      if (
        lastBridgedContact &&
        ((lastBridgedContact.contact_id && lastBridgedContact.contact_id === contactId) ||
          (lastBridgedContact.id && lastBridgedContact.id === contact.id) ||
          (lastBridgedContact.phone && lastBridgedContact.phone === phone))
      ) {
        renderPreviousCallNotes(data);
      }
    } catch (_err) {
      // Quiet fail to preserve call flow
    }
  };

  const showProfileModal = (contact) => {
    if (!contact) return;
    lastBridgedContact = contact;
    const dialog = byId("dialer-profile-dialog");
    if (!dialog) return;

    loadPreviousCallNotes(contact);
    renderModalScript();

    const avatar = byId("dialer-modal-avatar");
    if (avatar) avatar.textContent = initials(contact.name || "CC");

    const nameEl = byId("dialer-modal-name");
    if (nameEl) nameEl.textContent = contact.name || "Close contact";

    const titleEl = byId("dialer-modal-title");
    if (titleEl) titleEl.textContent = contact.title || "Contact";

    const companyEl = byId("dialer-modal-company");
    if (companyEl) companyEl.textContent = contact.company || "Close CRM";

    const phoneEl = byId("dialer-modal-phone");
    if (phoneEl) phoneEl.textContent = contact.phone_masked || contact.phone || "—";

    const statusEl = byId("dialer-modal-status-pill");
    if (statusEl) statusEl.textContent = contact.lead_status || "Active";

    const linkedinUrl = contact.linkedin_url || (contact.name ? `https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent([contact.name, contact.company].filter(Boolean).join(" "))}` : "");
    const closeUrl = contact.close_url || (contact.lead_id ? `https://app.close.com/lead/${contact.lead_id}/` : "");

    const linkedinIconBtn = byId("dialer-modal-linkedin-btn");
    if (linkedinIconBtn) {
      if (linkedinUrl) {
        linkedinIconBtn.href = linkedinUrl;
        linkedinIconBtn.style.display = "inline-flex";
      } else {
        linkedinIconBtn.removeAttribute("href");
        linkedinIconBtn.style.display = "none";
      }
    }

    const closeIconBtn = byId("dialer-modal-close-btn-link");
    if (closeIconBtn) {
      if (closeUrl) {
        closeIconBtn.href = closeUrl;
        closeIconBtn.style.display = "inline-flex";
      } else {
        closeIconBtn.removeAttribute("href");
        closeIconBtn.style.display = "none";
      }
    }

    const openClose = byId("dialer-modal-open-close");
    if (openClose) {
      if (closeUrl && /^https:\/\/app\.close\.com\//.test(closeUrl)) {
        openClose.href = closeUrl;
        openClose.style.display = "inline-flex";
      } else {
        openClose.removeAttribute("href");
        openClose.style.display = "none";
      }
    }

    const openLinkedin = byId("dialer-modal-open-linkedin");
    if (openLinkedin) {
      if (linkedinUrl) {
        openLinkedin.href = linkedinUrl;
        openLinkedin.style.display = "inline-flex";
      } else {
        openLinkedin.removeAttribute("href");
        openLinkedin.style.display = "none";
      }
    }

    if (!bridgeStartedAt) bridgeStartedAt = Date.now();
    if (!bridgeTimer) {
      const timerEl = byId("dialer-modal-timer");
      bridgeTimer = window.setInterval(() => {
        const secs = Math.floor((Date.now() - bridgeStartedAt) / 1000);
        const mins = Math.floor(secs / 60);
        const rem = secs % 60;
        const formatted = `${String(mins).padStart(2, "0")}:${String(rem).padStart(2, "0")}`;
        if (timerEl) {
          timerEl.textContent = formatted;
        }
        const heroTimerEl = byId("dialer-expanded-timer");
        if (heroTimerEl) {
          heroTimerEl.textContent = formatted;
        }
      }, 1000);
    }

    try {
      if (typeof dialog.showModal === "function" && !dialog.open) {
        dialog.showModal();
      } else if (!dialog.open) {
        dialog.setAttribute("open", "");
      }
    } catch (_err) {
      try {
        if (!dialog.open) dialog.setAttribute("open", "");
      } catch (_e2) {}
    }

    const autoOpenToggle = byId("dialer-auto-open-toggle");
    if (autoOpenToggle && autoOpenToggle.checked && contact.close_url) {
      if (state.lastAutoOpened !== (contact.id || contact.key)) {
        state.lastAutoOpened = contact.id || contact.key;
        window.setTimeout(() => {
          try {
            window.open(contact.close_url, "_blank");
          } catch (_e) {}
        }, 150);
      }
    }
  };

  const hideProfileModal = () => {
    state.modalDismissedByUser = true;
    const dialog = byId("dialer-profile-dialog");
    if (dialog && dialog.open) {
      try {
        dialog.close();
      } catch (_e) {
        dialog.removeAttribute("open");
      }
    }
  };

  const resetBridgeModal = () => {
    if (bridgeTimer) {
      window.clearInterval(bridgeTimer);
      bridgeTimer = null;
    }
    bridgeStartedAt = 0;
    const timerEl = byId("dialer-modal-timer");
    if (timerEl) timerEl.textContent = "00:00";
    const heroTimerEl = byId("dialer-expanded-timer");
    if (heroTimerEl) heroTimerEl.textContent = "00:00";
    const notesBox = byId("dialer-modal-notes-box");
    const notesList = byId("dialer-notes-list");
    if (notesBox) notesBox.hidden = true;
    if (notesList) notesList.replaceChildren();
    state.lastAutoOpened = null;
    hideProfileModal();
  };

  const showBridgeContact = (contact) => {
    if (!contact) return;
    state.modalDismissedByUser = false;
    state.bridged = contact.id || contact.key || true;
    byId("dialer-bridge-name").textContent = contact.name || "Close contact";
    byId("dialer-bridge-company").textContent = contact.company || "Close CRM";
    byId("dialer-bridge-details").textContent = [contact.title, contact.lead_status, contact.phone_masked || contact.phone]
      .filter(Boolean)
      .join(" · ");
    const open = byId("dialer-bridge-open");
    if (contact.close_url && /^https:\/\/app\.close\.com\/lead\//.test(contact.close_url)) {
      open.href = contact.close_url;
      open.hidden = false;
    } else {
      open.removeAttribute("href");
      open.hidden = true;
    }
    byId("dialer-bridge").hidden = false;
    showProfileModal(contact);
  };

  const updateButtons = () => {
    byId("dialer-start").hidden = state.running || Boolean(state.bridged);
    byId("dialer-stop").hidden = !state.running && !state.bridged;
    byId("dialer-smart-view").disabled = state.running || Boolean(state.bridged);
    byId("dialer-reset-progress").hidden = progressAttempted === 0 || state.running || Boolean(state.bridged);
    // Locked is a real state with nothing behind it to fall back on, so the
    // button says so rather than quietly doing nothing when it is pressed.
    byId("dialer-start").disabled = !liveReady;
    byId("dialer-start").title = liveReady ? "" : "Locked until the server allowlist and operator number are set.";
    document.querySelectorAll(".dialer-slot button").forEach((button) => {
      button.disabled = state.running || Boolean(state.bridged);
    });
    if (!byId("dialer-callback-enable").textContent.includes("enabled")) {
      byId("dialer-callback-enable").disabled = state.running || Boolean(state.bridged) || byId("dialer-callback-enable").hasAttribute("data-unavailable");
    }
  };
  const apiRequest = async (path, options = {}) => {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (operatorEmail) {
      headers["X-Operator-Email"] = operatorEmail;
    }
    const response = await window.fetch(path, {
      credentials: "same-origin",
      headers,
      ...options,
    });
    let payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }
    if (!response.ok) {
      const error = new Error(payload.error || "The dialer request failed.");
      error.status = response.status;
      throw error;
    }
    return payload;
  };
  const fileToBase64 = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || "").split(",", 2)[1] || "");
    reader.onerror = () => reject(new Error("The recording could not be read."));
    reader.readAsDataURL(file);
  });
  const showError = (message, title = "Live test did not start") => {
    byId("dialer-session-state").textContent = "Blocked";
    byId("dialer-live-title").textContent = title;
    const copy = byId("dialer-safety-copy");
    if (copy) copy.textContent = message;
  };

  const syncLiveSession = (session) => {
    const attempts = Array.isArray(session.attempts) ? session.attempts : [];

    // 1. Mark queued contacts in Close CRM contact list as attempted
    attempts.forEach((attempt) => {
      const queuedContact = contacts.find((contact) => contact.contactId === attempt.contact_id);
      if (queuedContact) {
        queuedContact.attempted = true;
        if (queuedContact.row) {
          queuedContact.row.dataset.attempted = "true";
          queuedContact.row.classList.add("dialer-attempted");
        }
      }
    });

    // 2. Track terminal outcomes in activity log and metrics
    let sessionHumanAnswered = 0;
    let sessionHumanMissed = 0;

    attempts.forEach((attempt) => {
      const isAnswered = attempt.outcome === "human-bridged" || attempt.status === "bridged" || attempt.outcome === "human";
      const isMissed = (attempt.abandoned || attempt.human_detected || ["abandoned", "operator-unavailable", "operator-no-answer", "operator-busy", "operator-failed"].includes(attempt.outcome)) && !isAnswered;
      if (isAnswered) sessionHumanAnswered += 1;
      if (isMissed) sessionHumanMissed += 1;

      const type = attempt.outcome || attempt.status || "queued";
      const [label, detail] = copyFor(type, attempt.status, attempt);
      const isTerminal = terminalStatuses.has(attempt.status) || Boolean(attempt.outcome && [
        "hangup", "busy", "no-answer", "failed", "invalid", "unclassified", "completed",
        "canceled", "canceled-after-human", "abandoned", "provider-error",
      ].includes(attempt.outcome)) || String(attempt.outcome || "").startsWith("operator-");
      if (isTerminal && !state.renderedLiveOutcomes.has(attempt.id)) {
        state.renderedLiveOutcomes.add(attempt.id);
        state.attempts += 1;
        state.outcomes.push({ type, contact: attempt });
        addActivity(attempt, type, label, detail);
      }
    });

    state.abandoned = session.stats && session.stats.human_missed !== undefined ? session.stats.human_missed : sessionHumanMissed;
    if (sessionHumanAnswered > state.connected) {
      state.connected = sessionHumanAnswered;
    }

    // 3. Render Live Lines: Active Parallel Dials or Auto-Expanded Connected Call
    const linesContainer = byId("dialer-lines");
    const isHumanConnected = session.status === "human-connected";
    const isNonTerminal = (a) => a && a.status !== "completed" && !terminalStatuses.has(a.status);
    const activeContact = session.active_contact || null;
    const connectedWinner = isHumanConnected
      ? (activeContact || attempts.find((a) => a.status === "bridged" || a.outcome === "human-bridged" || isNonTerminal(a)) || lastBridgedContact)
      : (activeContact && (activeContact.status === "bridged" || isNonTerminal(activeContact)) ? activeContact : null);

    if (connectedWinner) {
      const activeKey = connectedWinner.id || connectedWinner.key || true;
      const isNewBridge = state.bridged !== activeKey;

      if (linesContainer) {
        linesContainer.classList.add("has-expanded");
        const winnerCreatedAt = connectedWinner.created_at ? new Date(connectedWinner.created_at).getTime() : 0;
        const siblingAttempts = attempts.filter((a) => {
          if (a.id === (connectedWinner.id || connectedWinner.key)) return false;
          const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
          return !winnerCreatedAt || !aTime || Math.abs(aTime - winnerCreatedAt) < 90000;
        });

        const hero = buildExpandedHero(connectedWinner, session, siblingAttempts);
        linesContainer.replaceChildren(hero.card, ...(hero.siblingSection ? [hero.siblingSection] : []));
      }

      if (isNewBridge) {
        state.connected += 1;
        playConnectChime();
        showBridgeContact(connectedWinner);
        byId("dialer-complete").textContent = "Hang up & next call";
      } else {
        const dialog = byId("dialer-profile-dialog");
        if (dialog && !dialog.open && !state.modalDismissedByUser) {
          showProfileModal(connectedWinner);
        }
      }
    } else {
      if (linesContainer) linesContainer.classList.remove("has-expanded");

      if (attempts.length === 0 || ["completed", "failed", "stopped"].includes(session.status)) {
        state.lineCards.clear();
        if (linesContainer) {
          let emptyMessage = "Start a session to classify each answer as human, voicemail, hang-up or screening.";
          if (session.status === "stopped") {
            emptyMessage = "Live session stopped. Start a session to resume dialing.";
          } else if (session.status === "completed") {
            emptyMessage = "Live batch complete. Start a session to resume dialing.";
          } else if (session.status === "failed") {
            emptyMessage = "Live session ended. Start a session to resume dialing.";
          }
          linesContainer.innerHTML = `<div class="dialer-lines-empty"><span>&phone;</span><p>${emptyMessage}</p></div>`;
        }
      } else {
        const pendingAttempts = attempts.filter((a) => !terminalStatuses.has(a.status) && a.status !== "completed");
        const activeWaveAttempts = pendingAttempts.length > 0
          ? pendingAttempts
          : attempts.slice(-Math.max(1, session.concurrency || 1));

        const waveCards = activeWaveAttempts.map((attempt, index) => {
          const type = attempt.outcome || attempt.status || "queued";
          const [label, detail] = copyFor(type, attempt.status, attempt);

          let lineItem = state.lineCards.get(attempt.id);
          if (!lineItem) {
            lineItem = buildLine(
              {
                key: attempt.id,
                name: attempt.name || "Close contact",
                company: attempt.company || "Close CRM",
                title: attempt.title || "",
                phone: attempt.phone_masked || attempt.phone || "",
              },
              index + 1,
              attempt.id,
              attempt
            );
            state.lineCards.set(attempt.id, lineItem);
          }
          lineItem.card.className = `dialer-line ${type}`;
          lineItem.statusName.textContent = label;
          lineItem.statusDetail.textContent = detail;
          lineItem.statusPill.className = `dialer-line-status-pill ${type}`;
          if (lineItem.callerBadge) {
            const clLabel = attempt.caller_label || `Number ${attempt.queue_position || index + 1}`;
            const clNum = attempt.caller_number ? ` (${formatPhone(attempt.caller_number)})` : "";
            lineItem.callerBadge.replaceChildren();
            if (attempt.caller_health && attempt.caller_health.status) {
              const hDot = document.createElement("span");
              hDot.className = `health-badge ${attempt.caller_health.status}`;
              hDot.textContent = attempt.caller_health.badge || "●";
              lineItem.callerBadge.append(hDot);
            }
            const clTextNode = document.createTextNode(`${clLabel}${clNum}`);
            lineItem.callerBadge.append(clTextNode);
            lineItem.callerBadge.title = `Outbound Caller ID: ${attempt.caller_number || "Dedicated number"}`;
          }
          if (typeof lineItem.updateDebugDrawer === "function") {
            lineItem.updateDebugDrawer(attempt);
          }
          // The line it is on now, not its place in the queue: "Line 12" on a
          // three-line session read as a twelfth phone line.
          lineItem.badge.textContent = `Line ${index + 1}`;
          if (attempt.queue_position) lineItem.badge.title = `Contact ${attempt.queue_position} in the queue`;
          lineItem.pending = !terminalStatuses.has(attempt.status) && attempt.status !== "completed";
          return lineItem.card;
        });

        if (linesContainer) {
          linesContainer.replaceChildren(...waveCards);
        }
      }
    }

    const queueTotal = Number(session.queue_total || attempts.length);
    const queueStarted = Number(session.queue_started || attempts.length);
    const queueRemaining = Number(session.queue_remaining || 0);
    progressAttempted = queueStarted;
    progressRemaining = queueRemaining;
    byId("dialer-progress-attempted").textContent = String(progressAttempted);
    byId("dialer-progress-remaining").textContent = String(progressRemaining);
    byId("dialer-batch-label").textContent = `${session.mode === "power" ? "Power" : "Parallel"} queue; ${queueStarted}/${queueTotal} started, ${queueRemaining} waiting`;
    if (connectedWinner) {
      const activeKey = (connectedWinner.id || connectedWinner.key) || true;
      if (state.bridged !== activeKey) {
        showBridgeContact(connectedWinner);
      }
      byId("dialer-live-title").textContent = "Live conversation connected";
      byId("dialer-session-state").textContent = "Connected";
    } else {
      if (["completed", "failed", "stopped"].includes(session.status)) {
        state.running = false;
        state.bridged = null;
        state.modalDismissedByUser = false;
        byId("dialer-bridge").hidden = true;
        byId("dialer-live-title").textContent = session.status === "stopped" ? "Live session stopped" : "Live batch complete";
        byId("dialer-session-state").textContent = session.status === "failed" ? "Failed" : "Complete";
        resetCallMicMeter();
        resetBridgeModal();
      } else {
        // When no human winner is connected and session is live/dialing:
        // Clear bridged state and reset modal so dialing wave and next contacts display immediately
        state.bridged = null;
        state.modalDismissedByUser = false;
        byId("dialer-bridge").hidden = true;
        resetCallMicMeter();
        resetBridgeModal();

        if (session.status === "operator-connecting") {
          byId("dialer-live-title").textContent = "Answer your phone to begin";
          byId("dialer-session-state").textContent = "Waiting for operator";
        } else {
          byId("dialer-live-title").textContent = `${session.mode === "power" ? "Power dialer" : "Parallel dialer"} in progress`;
          byId("dialer-session-state").textContent = session.operator && session.operator.ready ? "Operator ready" : "Live dialing";
        }
      }
    }
    updateButtons();
    updateMetrics(session.stats);
  };

  const pollLiveSession = async () => {
    if (!state.liveSessionId) return;
    try {
      const payload = await apiRequest(`/dialer/api/session/${state.liveSessionId}`);
      state.pollFailures = 0;
      syncLiveSession(payload.session);
      if (state.running || ["human-connected", "operator-connecting"].includes(payload.session.status)) {
        // Cleared first: a session taken over during Start can be polled from two places.
        if (state.pollTimer) window.clearTimeout(state.pollTimer);
        state.pollTimer = window.setTimeout(pollLiveSession, 500);
      }
    } catch (error) {
      // One failed read is not a stopped session. A proxy blip (a 502 on 2026-09-21)
      // froze this page on "did not start" while the session kept dialing and put a
      // contact through to the operator. Keep asking, backing off, and give up only
      // when the server says the session is gone or you are signed out.
      const gone = [400, 401, 403, 404].includes(error.status);
      state.pollFailures = (state.pollFailures || 0) + 1;
      if (!gone && state.pollFailures <= 30) {
        byId("dialer-session-state").textContent = "Reconnecting";
        if (state.pollTimer) window.clearTimeout(state.pollTimer);
        state.pollTimer = window.setTimeout(
          pollLiveSession,
          Math.min(5000, 500 * 2 ** Math.min(state.pollFailures, 4))
        );
        return;
      }
      state.running = false;
      showError(
        gone ? error.message : "The dialer stopped answering. Reload the page to see your session.",
        "Lost track of your session"
      );
      updateButtons();
    }
  };

  // A session this page never heard back about: the answer to its Start was lost (a
  // reload or a dropped connection), or an earlier Start got there first. The server
  // keeps one session per operator, so the one it reports as active is ours.
  const findActiveSessionId = async () => {
    try {
      const status = await apiRequest("/dialer/api/status");
      return (status.active_session && status.active_session.id) || "";
    } catch (_error) {
      return "";
    }
  };

  const adoptSession = (sessionId) => {
    if (!sessionId || state.liveSessionId === sessionId) return;
    state.liveSessionId = sessionId;
    state.running = true;
    byId("dialer-smart-view").disabled = true;
    byId("dialer-reset-progress").hidden = true;
    byId("dialer-session-state").textContent = "Live dialing";
    byId("dialer-live-title").textContent = "Your session is running";
    updateButtons();
    pollLiveSession();
  };


  // --- Softphone ------------------------------------------------------------
  // The operator leg never needed to be a phone: it only has to answer and join
  // the conference. Twilio addresses this page as client:<identity>, so the call
  // lands here over WebRTC and the contact is bridged to the browser instead of
  // to a handset. Registering has to finish before the server dials the client,
  // or Twilio rings an endpoint that is not listening yet.
  const softphone = byId("dialer-softphone");
  const browserCalling = softphone ? softphone.dataset.browserCalling === "true" : false;
  let operatorTarget = browserCalling ? "browser" : "phone";
  let device = null;
  let activeCall = null;

  // Clean WebRTC microphone constraints: enforce Echo Cancellation and AGC for voice normalization,
  // disable browser noiseSuppression and legacy Chromium filters to prevent double-suppression
  // and robotic/underwater frequency gating with modern headsets/OS voice processing.
  const MIC_CONSTRAINTS = {
    audio: {
      echoCancellation: true,
      autoGainControl: true,
      noiseSuppression: false,
      channelCount: 1,
    },
  };

  const setPhoneState = (label, ready = false) => {
    const chip = byId("dialer-phone-state");
    if (!chip) return;
    chip.textContent = label;
    chip.classList.toggle("ready", ready);
  };
  const showCallControls = (visible) => {
    const controls = byId("dialer-phone-controls");
    if (controls) controls.hidden = !visible;
    if (!visible) byId("dialer-mute").textContent = "Mute";
  };

  const updateCallMicMeter = (inputVolume) => {
    const pct = Math.min(100, Math.round((inputVolume || 0) * 160));
    const fillDesk = byId("dialer-mic-meter-fill");
    const statusDesk = byId("dialer-mic-status");
    const fillModal = byId("dialer-modal-mic-fill");
    const statusModal = byId("dialer-modal-mic-level-label");
    const fillCard = byId("dialer-card-mic-fill");
    const statusCard = byId("dialer-card-mic-status");

    if (activeCall && activeCall.isMuted()) {
      if (fillDesk) fillDesk.style.width = "0%";
      if (statusDesk) statusDesk.textContent = "Muted";
      if (fillModal) fillModal.style.width = "0%";
      if (statusModal) statusModal.textContent = "Muted";
      if (fillCard) fillCard.style.width = "0%";
      if (statusCard) statusCard.textContent = "Muted";
      return;
    }

    if (fillDesk) {
      fillDesk.style.width = `${pct}%`;
      fillDesk.style.backgroundColor = pct > 80 ? "#e67e22" : pct > 20 ? "#2ecc71" : "#27ae60";
    }
    if (statusDesk) {
      statusDesk.textContent = pct > 20 ? "Speaking (Loud & clear)" : pct > 5 ? "Speaking (Good)" : "Auto-gain on";
    }

    if (fillModal) {
      fillModal.style.width = `${pct}%`;
      fillModal.style.backgroundColor = pct > 80 ? "#e67e22" : pct > 20 ? "#3ee0a1" : "#2ebb85";
    }
    if (statusModal) {
      statusModal.textContent = pct > 20 ? "Loud & clear" : pct > 5 ? "Good level" : "Connected";
    }

    if (fillCard) {
      fillCard.style.width = `${pct}%`;
      fillCard.style.backgroundColor = pct > 80 ? "#e67e22" : pct > 20 ? "#10b981" : "#059669";
    }
    if (statusCard) {
      statusCard.textContent = pct > 20 ? "Speaking (Loud & clear)" : pct > 5 ? "Speaking (Good)" : "Auto-gain on";
    }
  };

  const resetCallMicMeter = () => {
    const fillDesk = byId("dialer-mic-meter-fill");
    const statusDesk = byId("dialer-mic-status");
    const fillModal = byId("dialer-modal-mic-fill");
    const statusModal = byId("dialer-modal-mic-level-label");
    const fillCard = byId("dialer-card-mic-fill");
    const statusCard = byId("dialer-card-mic-status");
    if (fillDesk) fillDesk.style.width = "0%";
    if (statusDesk) statusDesk.textContent = "Auto-gain on";
    if (fillModal) fillModal.style.width = "0%";
    if (statusModal) statusModal.textContent = "Auto-gain active";
    if (fillCard) fillCard.style.width = "0%";
    if (statusCard) statusCard.textContent = "Auto-gain on";
  };

  let micTestStream = null;
  let micTestAudioCtx = null;
  let micTestAnimId = 0;

  const stopMicTest = () => {
    if (micTestAnimId) {
      window.cancelAnimationFrame(micTestAnimId);
      micTestAnimId = 0;
    }
    if (micTestStream) {
      micTestStream.getTracks().forEach((track) => track.stop());
      micTestStream = null;
    }
    if (micTestAudioCtx) {
      micTestAudioCtx.close().catch(() => {});
      micTestAudioCtx = null;
    }
    const testBtn = byId("dialer-mic-test-btn");
    if (testBtn) testBtn.textContent = "Test mic";
    const status = byId("dialer-mic-status");
    if (status && !activeCall) status.textContent = "Auto-gain on";
    const fill = byId("dialer-mic-meter-fill");
    if (fill && !activeCall) fill.style.width = "0%";
  };

  const startMicTest = async () => {
    if (micTestStream) {
      stopMicTest();
      return;
    }
    const testBtn = byId("dialer-mic-test-btn");
    const status = byId("dialer-mic-status");
    const fill = byId("dialer-mic-meter-fill");
    if (testBtn) testBtn.textContent = "Stop test";
    if (status) status.textContent = "Speak now...";

    try {
      micTestStream = await navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS);
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) {
        if (status) status.textContent = "Mic active (AGC on)";
        return;
      }
      micTestAudioCtx = new AudioContextClass();
      const source = micTestAudioCtx.createMediaStreamSource(micTestStream);
      const analyser = micTestAudioCtx.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.25;
      source.connect(analyser);

      const buffer = new Uint8Array(analyser.frequencyBinCount);
      let peakVolume = 0;
      const startTime = Date.now();

      const sample = () => {
        if (!micTestStream) return;
        analyser.getByteFrequencyData(buffer);
        let sum = 0;
        for (let i = 0; i < buffer.length; i++) sum += buffer[i];
        const avg = sum / buffer.length;
        const norm = Math.min(1, avg / 110);
        peakVolume = Math.max(peakVolume, norm);
        const pct = Math.min(100, Math.round(norm * 140));

        if (fill) {
          fill.style.width = `${pct}%`;
          fill.style.backgroundColor = pct > 80 ? "#e67e22" : pct > 20 ? "#2ecc71" : "#27ae60";
        }

        if (status) {
          if (pct > 25) {
            status.textContent = "Loud & clear!";
          } else if (pct > 5) {
            status.textContent = "Speaking (Good)";
          } else if (Date.now() - startTime > 2500 && peakVolume < 0.1) {
            status.textContent = "Quiet - boost mic in Settings";
          } else {
            status.textContent = "Listening... speak now";
          }
        }

        if (Date.now() - startTime > 15000) {
          stopMicTest();
          return;
        }
        micTestAnimId = window.requestAnimationFrame(sample);
      };
      micTestAnimId = window.requestAnimationFrame(sample);
    } catch (err) {
      if (status) status.textContent = "Mic unavailable";
      if (testBtn) testBtn.textContent = "Test mic";
      showError("Could not access microphone: " + (err.message || err));
      stopMicTest();
    }
  };

  const attachCall = (call) => {
    activeCall = call;
    stopMicTest();
    showCallControls(true);
    setPhoneState("On the line", true);
    call.on("volume", (inputVolume, _outputVolume) => {
      updateCallMicMeter(inputVolume);
    });
    call.on("disconnect", () => {
      activeCall = null;
      showCallControls(false);
      resetCallMicMeter();
      setPhoneState(device ? "Ready" : "Not connected", Boolean(device));
    });
    call.on("cancel", () => {
      activeCall = null;
      showCallControls(false);
      resetCallMicMeter();
    });
  };

  const ensureDevice = async () => {
    if (device) return device;
    if (!window.Twilio || !window.Twilio.Device) {
      throw new Error("The softphone did not load. Reload the page, or take the call on your phone.");
    }
    setPhoneState("Connecting");
    const issued = await apiRequest("/dialer/api/voice-token");
    device = new window.Twilio.Device(issued.token, {
      edge: ["ashburn", "umatilla", "roaming"],
      codecPreferences: ["opus", "pcmu"],
      maxAverageBitrate: 32000,
      logLevel: "error",
      sounds: {
        incoming: false,
        outgoing: false,
        disconnect: false,
      },
      disableAudioContextSounds: true,
    });
    if (device.audio) {
      if (typeof device.audio.incoming === "function") device.audio.incoming(false);
      if (typeof device.audio.outgoing === "function") device.audio.outgoing(false);
      if (typeof device.audio.disconnect === "function") device.audio.disconnect(false);
      if (typeof device.audio.setAudioConstraints === "function") {
        device.audio.setAudioConstraints(MIC_CONSTRAINTS.audio);
      }
    }
    // The server places the operator leg, so a call that rings while this page is
    // starting or running a session is ours. One that rings an idle page belongs to the
    // operator's other screen (the phone app) or to a Start this page gave up on. Left
    // to ring, it reaches that screen or times out and ends its session. Taking it put
    // people through to a page that showed nothing.
    device.on("incoming", (call) => {
      if (!state.running) {
        call.ignore();
        return;
      }
      stopMicTest();
      call.accept({
        rtcConstraints: MIC_CONSTRAINTS,
      });
      attachCall(call);
      // The leg rings before Start answers, and the answer can be lost: show the
      // session these calls belong to either way.
      if (!state.liveSessionId) findActiveSessionId().then(adoptSession);
    });
    device.on("tokenWillExpire", async () => {
      try {
        const next = await apiRequest("/dialer/api/voice-token");
        device.updateToken(next.token);
      } catch (_error) {
        setPhoneState("Reconnect needed");
      }
    });
    device.on("unregistered", () => setPhoneState("Not connected"));
    device.on("error", (error) => {
      // 31401 is a refused microphone, which reads as a dead button otherwise.
      const message = error && error.code === 31401
        ? "The microphone was refused, so the call cannot be taken here."
        : `Softphone error: ${(error && error.message) || "unknown"}`;
      setPhoneState("Error");
      showError(message);
    });
    await device.register();
    setPhoneState("Ready", true);
    return device;
  };

  if (softphone) {
    document.querySelectorAll("[data-operator-target]").forEach((button) => {
      button.addEventListener("click", async () => {
        if (state.running || state.bridged || button.disabled) return;
        operatorTarget = button.dataset.operatorTarget;
        document.querySelectorAll("[data-operator-target]").forEach((other) => {
          other.classList.toggle("active", other === button);
        });
        if (operatorTarget === "browser") {
          try {
            await ensureDevice();
          } catch (error) {
            showError(error.message);
          }
        } else {
          setPhoneState("Your phone will ring", true);
          showCallControls(false);
        }
      });
    });
    const micTestBtn = byId("dialer-mic-test-btn");
    if (micTestBtn) micTestBtn.addEventListener("click", startMicTest);

    byId("dialer-mute").addEventListener("click", (event) => {
      if (!activeCall) return;
      const muted = !activeCall.isMuted();
      activeCall.mute(muted);
      event.currentTarget.textContent = muted ? "Unmute" : "Mute";
      const modalMute = byId("dialer-modal-mute");
      if (modalMute) {
        modalMute.textContent = muted ? "Unmute mic" : "Mute mic";
        modalMute.classList.toggle("muted", muted);
      }
      updateCallMicMeter(0);
    });
    byId("dialer-hangup").addEventListener("click", () => {
      if (state.bridged || (state.liveSessionId && state.running)) {
        completeLiveCall();
      } else {
        if (device) device.disconnectAll();
      }
    });
    // Register on load rather than on the first click: a softphone that says
    // "Not connected" until you prod it reads as broken, and registering costs
    // nothing -- the microphone is only requested when a call is accepted.
    if (browserCalling) {
      ensureDevice().catch((error) => {
        setPhoneState("Not connected");
        showError(error.message);
      });
    } else {
      setPhoneState("Not connected");
    }
  }

  const startLive = async () => {
    if (!liveReady || state.running || state.bridged) return;
    if (operatorTarget === "browser") {
      try {
        // Registering first is not an optimisation: Twilio would otherwise ring a
        // client that has not subscribed yet, and the session would stall.
        await ensureDevice();
      } catch (error) {
        showError(error.message);
        return;
      }
    }
    const capacity = Math.min(maxConcurrency, Number(byId("dialer-concurrency").value));
    const eligible = availableLiveContacts();
    if (!smartViewId) {
      showError("Choose a Close Smart View before starting.");
      return;
    }
    if (!eligible.length) {
      showError("This Smart View has no contacts on the consenting test allowlist.");
      return;
    }
    const approved = window.confirm(
      `${progressAttempted ? `Resume after ${progressAttempted} attempted contact${progressAttempted === 1 ? "" : "s"}` : "Start from the beginning"} of “${smartViewName}” in ${capacity === 1 ? "power-dialer" : `${capacity}-line parallel`} mode? Only the ${eligible.length} remaining server-allowlisted contact${eligible.length === 1 ? "" : "s"} can be called.`
    );
    if (!approved) return;
    clearTimers();
    state.running = true;
    state.bridged = null;
    state.currentLines = [];
    state.lineCards.clear();
    state.renderedLiveOutcomes.clear();
    byId("dialer-bridge").hidden = true;
    byId("dialer-session-state").textContent = "Starting";
    byId("dialer-live-title").textContent = "Starting live test";
    updateButtons();
    try {
      const payload = await apiRequest("/dialer/api/start", {
        method: "POST",
        body: JSON.stringify({
          smart_view_id: smartViewId,
          max_contacts: Math.max(1, contacts.length),
          concurrency: capacity,
          screening_reply:
            profile.screening_reply ||
            `Hi, this is ${operatorName || "an operator"} calling. Could you point me to the right person to speak with?`,
          operator_target: operatorTarget,
          timezone_wave: byId("dialer-wave-sort-toggle")?.checked ?? true,
          safe_hours_only: byId("dialer-safe-hours-toggle")?.checked ?? false,
        }),
      });
      const adopted = state.liveSessionId === payload.session.id;
      state.liveSessionId = payload.session.id;
      syncLiveSession(payload.session);
      if (!adopted) pollLiveSession();
    } catch (error) {
      // The server can have started a session this request never heard back about. Its
      // calls ring this page, so show it rather than "did not start".
      const running = state.liveSessionId || (await findActiveSessionId());
      if (running) {
        adoptSession(running);
        return;
      }
      state.running = false;
      state.liveSessionId = "";
      showError(error.message);
      updateButtons();
    }
  };

  const stopSession = async () => {
    clearTimers();
    if (state.liveSessionId) {
      try {
        const payload = await apiRequest(`/dialer/api/session/${state.liveSessionId}/stop`, { method: "POST", body: "{}" });
        syncLiveSession(payload.session);
      } catch (error) {
        showError(error.message);
      }
      state.liveSessionId = "";
    }
    if (device) device.disconnectAll();
    state.running = false;
    state.bridged = null;
    byId("dialer-bridge").hidden = true;
    resetBridgeModal();
    updateButtons();
    updateMetrics();
  };

  const completeLiveCall = async () => {
    if (!state.liveSessionId) return;
    const button = byId("dialer-complete");
    if (button) button.disabled = true;
    const modalBtn = byId("dialer-modal-complete");
    if (modalBtn) modalBtn.disabled = true;

    // Immediately unblock UI: clear bridged state, close modal, and show dialing state
    state.bridged = null;
    state.modalDismissedByUser = false;
    byId("dialer-bridge").hidden = true;
    resetCallMicMeter();
    resetBridgeModal();
    byId("dialer-live-title").textContent = "Dialing next contact...";
    byId("dialer-session-state").textContent = "Live dialing";

    try {
      const payload = await apiRequest(`/dialer/api/session/${state.liveSessionId}/complete-active`, {
        method: "POST",
        body: "{}",
      });
      if (payload && payload.session) {
        syncLiveSession(payload.session);
      }
    } catch (error) {
      console.warn("Complete active call notice:", error);
    } finally {
      if (button) button.disabled = false;
      if (modalBtn) modalBtn.disabled = false;
    }
  };

  const dropActiveVoicemail = async () => {
    if (!state.liveSessionId) return;
    const bridgeVmBtn = byId("dialer-bridge-drop-vm");
    const modalVmBtn = byId("dialer-modal-drop-voicemail");
    if (bridgeVmBtn) {
      bridgeVmBtn.disabled = true;
      bridgeVmBtn.textContent = "Dropping...";
    }
    if (modalVmBtn) {
      modalVmBtn.disabled = true;
      modalVmBtn.textContent = "Flagging...";
    }

    // Immediately unblock UI: clear bridged state, close modal, and resume dialing state
    const contactName = lastBridgedContact ? (lastBridgedContact.name || "Contact") : "Contact";
    state.bridged = null;
    state.modalDismissedByUser = false;
    byId("dialer-bridge").hidden = true;
    resetCallMicMeter();
    resetBridgeModal();
    byId("dialer-live-title").textContent = `⚡ Flagged voicemail for ${contactName}; dialing next...`;
    byId("dialer-session-state").textContent = "Live dialing";

    try {
      const payload = await apiRequest(`/dialer/api/session/${state.liveSessionId}/drop-voicemail`, {
        method: "POST",
        body: "{}",
      });
      if (payload && payload.session) {
        syncLiveSession(payload.session);
      }
    } catch (error) {
      console.warn("Voicemail drop notice:", error);
    } finally {
      if (bridgeVmBtn) {
        bridgeVmBtn.disabled = false;
        bridgeVmBtn.textContent = "⚡ Drop Voicemail";
      }
      if (modalVmBtn) {
        modalVmBtn.disabled = false;
        modalVmBtn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;vertical-align:-2px"><circle cx="5.5" cy="12" r="3.5"/><circle cx="18.5" cy="12" r="3.5"/><path d="M5.5 15.5h13"/></svg>This is a voicemail';
      }
    }
  };

  const disqualifyActiveCall = async (disposition = "Not Interested") => {
    if (!state.liveSessionId) return;
    const bridgeDncBtn = byId("dialer-bridge-dnc");
    const modalDncBtn = byId("dialer-modal-dnc");
    if (bridgeDncBtn) {
      bridgeDncBtn.disabled = true;
      bridgeDncBtn.textContent = "Updating Close...";
    }
    if (modalDncBtn) {
      modalDncBtn.disabled = true;
      modalDncBtn.textContent = "Updating Close...";
    }

    // Immediately unblock UI: clear bridged state, close modal, and resume dialing state
    const contactName = lastBridgedContact ? (lastBridgedContact.name || "Contact") : "Contact";
    state.bridged = null;
    state.modalDismissedByUser = false;
    byId("dialer-bridge").hidden = true;
    resetCallMicMeter();
    resetBridgeModal();
    byId("dialer-live-title").textContent = `⛔ Marked ${contactName} as Not Interested in Close; dialing next...`;
    byId("dialer-session-state").textContent = "Live dialing";

    try {
      const payload = await apiRequest(`/dialer/api/session/${state.liveSessionId}/disqualify-active`, {
        method: "POST",
        body: JSON.stringify({ disposition }),
      });
      if (payload && payload.session) {
        syncLiveSession(payload.session);
      }
    } catch (error) {
      console.warn("Disqualify call notice:", error);
    } finally {
      if (bridgeDncBtn) {
        bridgeDncBtn.disabled = false;
        bridgeDncBtn.textContent = "⛔ Not Interested";
      }
      if (modalDncBtn) {
        modalDncBtn.disabled = false;
        modalDncBtn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;vertical-align:-2px"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>Not Interested';
      }
    }
  };

  const updateStartCopy = () => {
    const concurrency = Number(byId("dialer-concurrency").value);
    byId("dialer-start").querySelector("b").textContent = concurrency === 1
      ? "Start power session"
      : "Start parallel session";
    byId("dialer-start-detail").textContent = concurrency === 1
      ? progressAttempted
        ? `Resume after ${progressAttempted}; call one contact at a time`
        : "Call the selected Smart View one contact at a time"
      : `Keep up to ${concurrency} Smart View contacts dialing`;
  };

  byId("dialer-concurrency").max = String(maxConcurrency);
  byId("dialer-concurrency").value = "1";
  byId("dialer-concurrency").addEventListener("input", (event) => {
    const value = event.target.value;
    byId("dialer-concurrency-output").textContent = value;
    byId("dialer-line-capacity").textContent = value;
    updateStartCopy();
    updateMetrics();
  });
  const updateWaveSummary = () => {
    const summaryEl = byId("dialer-wave-prime-count");
    if (!summaryEl) return;
    const callableContacts = rows.filter((r) => !r.hidden && r.dataset.canCall !== "false");
    const primeCount = callableContacts.filter((r) => r.dataset.waveStatus === "prime").length;
    const totalCount = callableContacts.length;

    if (primeCount > 0) {
      summaryEl.className = "wave-pill prime";
      summaryEl.textContent = `${primeCount} Prime Wave`;
    } else if (totalCount > 0) {
      summaryEl.className = "wave-pill";
      summaryEl.textContent = `${totalCount} Callable`;
    } else {
      summaryEl.className = "wave-pill off-hours";
      summaryEl.textContent = "Off-Hours";
    }
  };

  const applyContactFilters = () => {
    const searchEl = byId("dialer-search");
    const query = (searchEl ? searchEl.value : "").trim().toLowerCase();
    const safeHoursToggle = byId("dialer-safe-hours-toggle");
    const safeHoursOnly = safeHoursToggle ? safeHoursToggle.checked : false;

    rows.forEach((row) => {
      const text = `${row.dataset.name} ${row.dataset.company} ${row.dataset.status} ${row.dataset.phone}`.toLowerCase();
      const matchesQuery = !query || text.includes(query);
      const isOffHours = row.dataset.canCall === "false";
      const blockedBySafeHours = safeHoursOnly && isOffHours;

      row.classList.toggle("off-hours-filtered", blockedBySafeHours);
      row.hidden = !matchesQuery || blockedBySafeHours;
    });
    updateWaveSummary();
    updateMetrics();
  };

  const sortContactsByWave = () => {
    const listEl = byId("dialer-contact-list");
    if (!listEl) return;
    const waveToggle = byId("dialer-wave-sort-toggle");
    const waveSortOn = waveToggle ? waveToggle.checked : true;

    const tzPriority = {
      ET: 1,
      CT: 2,
      MT: 3,
      AZ: 4,
      PT: 5,
      AK: 6,
      HI: 7,
    };

    const sortedRows = [...rows].sort((a, b) => {
      // 1. Callable (not blocked) comes before blocked
      const allowedA = a.dataset.liveAllowed !== "false" ? 1 : 0;
      const allowedB = b.dataset.liveAllowed !== "false" ? 1 : 0;
      if (allowedA !== allowedB) return allowedB - allowedA;

      // 2. Unattempted comes before attempted
      const attemptedA = a.dataset.attempted === "true" ? 1 : 0;
      const attemptedB = b.dataset.attempted === "true" ? 1 : 0;
      if (attemptedA !== attemptedB) return attemptedA - attemptedB;

      if (!waveSortOn) {
        return Number(a.dataset.initialIndex || 0) - Number(b.dataset.initialIndex || 0);
      }
      const canCallA = a.dataset.canCall !== "false" ? 1 : 0;
      const canCallB = b.dataset.canCall !== "false" ? 1 : 0;
      if (canCallA !== canCallB) return canCallB - canCallA;

      const waveRank = { prime: 0, acceptable: 1, off_hours: 2 };
      const rankA = waveRank[a.dataset.waveStatus] ?? 1;
      const rankB = waveRank[b.dataset.waveStatus] ?? 1;
      if (rankA !== rankB) return rankA - rankB;

      const tzA = tzPriority[a.dataset.tzCode] || 99;
      const tzB = tzPriority[b.dataset.tzCode] || 99;
      if (tzA !== tzB) return tzA - tzB;

      return Number(a.dataset.initialIndex || 0) - Number(b.dataset.initialIndex || 0);
    });

    sortedRows.forEach((row) => listEl.appendChild(row));
  };

  const initTimezoneWave = () => {
    rows.forEach((row, idx) => {
      row.dataset.initialIndex = String(idx);
    });

    const waveToggle = byId("dialer-wave-sort-toggle");
    const safeHoursToggle = byId("dialer-safe-hours-toggle");

    const onWaveConfigChange = () => {
      sortContactsByWave();
      applyContactFilters();
    };

    if (waveToggle) waveToggle.addEventListener("change", onWaveConfigChange);
    if (safeHoursToggle) safeHoursToggle.addEventListener("change", onWaveConfigChange);

    onWaveConfigChange();
  };

  byId("dialer-search").addEventListener("input", () => {
    applyContactFilters();
  });
  byId("dialer-smart-view").addEventListener("change", (event) => {
    if (state.running || state.bridged || !event.target.value) return;
    const url = new URL(window.location.href);
    url.searchParams.set("smart_view_id", event.target.value);
    window.location.assign(url.toString());
  });
  const organizeBtn = byId("dialer-organize-btn");
  if (organizeBtn) {
    organizeBtn.addEventListener("click", async () => {
      if (state.running || state.bridged) return;
      const currentViewId = byId("dialer-smart-view")?.value || smartViewId || "";
      const origHtml = organizeBtn.innerHTML;
      organizeBtn.disabled = true;
      organizeBtn.innerHTML = `
        <svg class="dialer-spin" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"></path></svg>
        <span>Organizing...</span>
      `;
      try {
        await apiRequest("/dialer/api/contacts/organize", {
          method: "POST",
          body: JSON.stringify({ smart_view_id: currentViewId }),
        });
        window.location.reload();
      } catch (error) {
        showError(error.message || "Could not organize contacts.");
        organizeBtn.disabled = false;
        organizeBtn.innerHTML = origHtml;
      }
    });
  }
  byId("dialer-reset-progress").addEventListener("click", async () => {
    if (state.running || state.bridged || !smartViewId) return;
    if (!window.confirm(`Clear saved dialer progress for “${smartViewName}” and start from its first contact next time?`)) return;
    try {
      await apiRequest("/dialer/api/progress/reset", {
        method: "POST",
        body: JSON.stringify({ smart_view_id: smartViewId }),
      });
      window.location.reload();
    } catch (error) {
      showError(error.message);
    }
  });
  // --- Recording studio ---------------------------------------------------
  // Three things get said on a live call, and each is a slot the operator fills
  // in their own voice. A browser records WebM/Opus or MP4 and Twilio plays
  // neither, so what the microphone captures is decoded and re-encoded here as
  // 8 kHz mono PCM WAV -- the format the phone network actually carries, and
  // small enough that the upload is instant.
  const studio = byId("dialer-studio");
  const maxGreeting = Number((studio && studio.dataset.maxGreeting) || 2.5);

  const encodeWav = (samples, rate) => {
    const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
    const text = (offset, value) => {
      for (let index = 0; index < value.length; index += 1) {
        view.setUint8(offset + index, value.charCodeAt(index));
      }
    };
    text(0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    text(8, "WAVE");
    text(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, rate, true);
    view.setUint32(28, rate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    text(36, "data");
    view.setUint32(40, samples.length * 2, true);
    for (let index = 0, offset = 44; index < samples.length; index += 1, offset += 2) {
      const value = Math.max(-1, Math.min(1, samples[index]));
      view.setInt16(offset, value < 0 ? value * 0x8000 : value * 0x7fff, true);
    }
    return new Blob([view], { type: "audio/wav" });
  };

  const toTelephoneWav = async (blob) => {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const context = new AudioContextClass();
    let decoded;
    try {
      decoded = await context.decodeAudioData(await blob.arrayBuffer());
    } finally {
      context.close();
    }
    const rate = 8000;
    const offline = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * rate)), rate);
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();
    const rendered = await offline.startRendering();
    return { blob: encodeWav(rendered.getChannelData(0), rate), seconds: decoded.duration };
  };

  const slotPanels = Array.from(document.querySelectorAll(".dialer-slot"));
  slotPanels.forEach((panel) => {
    const slot = panel.dataset.slot;
    const find = (attribute) => panel.querySelector(`[${attribute}]`);
    const state_ = find("data-slot-state");
    const review = panel.querySelector(".dialer-slot-review");
    const audio = find("data-slot-audio");
    const playback = panel.querySelector("[data-slot-saved-playback]");
    const playbackAudio = find("data-slot-playback-audio");
    const recordButton = find("data-slot-record");
    const fileInput = find("data-slot-file");
    let recorder = null;
    let chunks = [];
    let pending = null;
    let ticker = null;
    let previewUrl = "";

    const setState = (label, ready) => {
      state_.textContent = label;
      state_.classList.toggle("ready", Boolean(ready));
    };
    const clearPreview = () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = "";
      pending = null;
      review.hidden = true;
      audio.removeAttribute("src");
      if (playback && !panel.querySelector("[data-slot-remove]").hidden) {
        playback.hidden = false;
      }
    };
    const offerPreview = (blob, seconds) => {
      pending = { blob, seconds };
      previewUrl = URL.createObjectURL(blob);
      audio.src = previewUrl;
      review.hidden = false;
      if (playback) {
        if (playbackAudio) playbackAudio.pause();
        playback.hidden = true;
      }
      setState(`${seconds.toFixed(1)}s — not saved`, false);
    };

    const stopRecording = () => {
      if (recorder && recorder.state !== "inactive") recorder.stop();
    };

    recordButton.addEventListener("click", async () => {
      if (playbackAudio) playbackAudio.pause();
      if (recorder && recorder.state === "recording") {
        stopRecording();
        return;
      }
      clearPreview();
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
      } catch (_error) {
        showError("The microphone was refused. Allow it for this site, or use Upload instead.");
        return;
      }
      chunks = [];
      recorder = new MediaRecorder(stream);
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size) chunks.push(event.data);
      });
      recorder.addEventListener("stop", async () => {
        window.clearInterval(ticker);
        stream.getTracks().forEach((track) => track.stop());
        recordButton.classList.remove("recording");
        recordButton.lastChild.textContent = "Record";
        try {
          const converted = await toTelephoneWav(new Blob(chunks, { type: recorder.mimeType }));
          offerPreview(converted.blob, converted.seconds);
        } catch (_error) {
          setState("Not set", false);
          showError("That recording could not be converted. Try Upload instead.");
        }
      });
      const started = Date.now();
      recorder.start();
      recordButton.classList.add("recording");
      recordButton.lastChild.textContent = "Stop";
      ticker = window.setInterval(() => {
        const elapsed = (Date.now() - started) / 1000;
        setState(`${elapsed.toFixed(1)}s`, false);
        // The hello is capped rather than trimmed: anything inside <Gather> is
        // time the speech recogniser cannot hear the contact. Stopping a little
        // early keeps the encoded file under the limit the server enforces, so a
        // recording that looked fine here is never rejected on save.
        if (slot === "greeting" && elapsed >= maxGreeting - 0.25) stopRecording();
        if (slot === "dropped" && elapsed >= 5.75) stopRecording();
      }, 100);
    });

    find("data-slot-upload").addEventListener("click", () => {
      if (playbackAudio) playbackAudio.pause();
      fileInput.click();
    });
    fileInput.addEventListener("change", async (event) => {
      const file = event.target.files && event.target.files[0];
      event.target.value = "";
      if (!file) return;
      clearPreview();
      const isWav = /\.wav$/i.test(file.name) || file.type === "audio/wav";
      if (!isWav && !/\.mp3$/i.test(file.name) && file.type !== "audio/mpeg") {
        showError("Upload an MP3 or WAV file. Phone voice memos are usually .m4a and will not play.");
        return;
      }
      try {
        const probe = await toTelephoneWav(file);
        // The original file is what gets saved; the decode only measures it.
        offerPreview(file, probe.seconds);
        pending.filename = file.name;
        pending.contentType = isWav ? "audio/wav" : "audio/mpeg";
      } catch (_error) {
        showError("That file could not be read as audio.");
      }
    });

    find("data-slot-save").addEventListener("click", async (event) => {
      if (!pending) return;
      const button = event.currentTarget;
      button.disabled = true;
      setState("Saving", false);
      try {
        const payload = {
          filename: pending.filename || `${slot}.wav`,
          content_type: pending.contentType || "audio/wav",
          data_base64: await fileToBase64(pending.blob),
        };
        await apiRequest(`/dialer/api/recording/${slot}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        window.location.reload();
      } catch (error) {
        setState("Not set", false);
        showError(error.message);
      } finally {
        button.disabled = false;
      }
    });

    find("data-slot-discard").addEventListener("click", () => {
      clearPreview();
      setState(panel.querySelector("[data-slot-remove]").hidden ? "Not set" : "Ready",
               !panel.querySelector("[data-slot-remove]").hidden);
    });

    find("data-slot-remove").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        await apiRequest(`/dialer/api/recording/${slot}`, { method: "DELETE" });
        window.location.reload();
      } catch (error) {
        showError(error.message);
        button.disabled = false;
      }
    });

    if (!navigator.mediaDevices || !window.MediaRecorder) {
      recordButton.disabled = true;
      recordButton.title = "This browser cannot record; upload a file instead.";
    }
  });
  byId("dialer-callback-enable").addEventListener("click", async (event) => {
    if (state.running || event.currentTarget.disabled) return;
    event.currentTarget.disabled = true;
    try {
      await apiRequest("/dialer/api/callbacks/configure", { method: "POST", body: "{}" });
      event.currentTarget.textContent = "Callback forwarding enabled";
    } catch (error) {
      showError(error.message);
      event.currentTarget.disabled = false;
    }
  });
  byId("dialer-start").addEventListener("click", startLive);
  byId("dialer-stop").addEventListener("click", stopSession);
  byId("dialer-complete").addEventListener("click", completeLiveCall);
  byId("dialer-clear").addEventListener("click", () => {
    byId("dialer-activity").innerHTML = '<div class="dialer-activity-empty">Outcomes will appear as a session runs.</div>';
  });

  const modalCloseBtn = byId("dialer-modal-close");
  if (modalCloseBtn) modalCloseBtn.addEventListener("click", hideProfileModal);

  const profileDialogEl = byId("dialer-profile-dialog");
  if (profileDialogEl) {
    profileDialogEl.addEventListener("click", (event) => {
      if (event.target === profileDialogEl) {
        hideProfileModal();
      }
    });
  }

  const modalCompleteBtn = byId("dialer-modal-complete");
  if (modalCompleteBtn) modalCompleteBtn.addEventListener("click", completeLiveCall);

  const modalMuteBtn = byId("dialer-modal-mute");
  if (modalMuteBtn) {
    modalMuteBtn.addEventListener("click", () => {
      if (!activeCall) return;
      const muted = !activeCall.isMuted();
      activeCall.mute(muted);
      modalMuteBtn.textContent = muted ? "Unmute mic" : "Mute mic";
      modalMuteBtn.classList.toggle("muted", muted);
      const deskMute = byId("dialer-mute");
      if (deskMute) deskMute.textContent = muted ? "Unmute" : "Mute";
      updateCallMicMeter(0);
    });
  }

  const autoOpenToggle = byId("dialer-auto-open-toggle");
  if (autoOpenToggle) {
    autoOpenToggle.checked = window.localStorage.getItem("dialer_auto_open_close") === "true";
    autoOpenToggle.addEventListener("change", () => {
      window.localStorage.setItem("dialer_auto_open_close", autoOpenToggle.checked ? "true" : "false");
    });
  }

  byId("dialer-bridge").addEventListener("click", (event) => {
    if (
      event.target &&
      (event.target.id === "dialer-complete" ||
        event.target.id === "dialer-bridge-open" ||
        event.target.id === "dialer-bridge-drop-vm" ||
        (event.target.closest && event.target.closest("#dialer-bridge-drop-vm")))
    ) {
      return;
    }
    if (lastBridgedContact) showProfileModal(lastBridgedContact);
  });

  const bridgeDropVmBtn = byId("dialer-bridge-drop-vm");
  if (bridgeDropVmBtn) bridgeDropVmBtn.addEventListener("click", dropActiveVoicemail);

  const modalDropVmBtn = byId("dialer-modal-drop-voicemail");
  if (modalDropVmBtn) modalDropVmBtn.addEventListener("click", dropActiveVoicemail);

  const bridgeDncBtn = byId("dialer-bridge-dnc");
  if (bridgeDncBtn) bridgeDncBtn.addEventListener("click", () => disqualifyActiveCall());

  const modalDncBtn = byId("dialer-modal-dnc");
  if (modalDncBtn) modalDncBtn.addEventListener("click", () => disqualifyActiveCall());

  window.addEventListener("keydown", (event) => {
    const settingsDlg = byId("dialer-settings-dialog");
    if (settingsDlg && settingsDlg.open && event.key === "Escape") {
      settingsDlg.close();
      return;
    }
    const dialog = byId("dialer-profile-dialog");
    if (dialog && dialog.open) {
      if (event.key === "Enter") {
        const openClose = byId("dialer-modal-open-close");
        if (openClose && openClose.href && openClose.style.display !== "none") {
          window.open(openClose.href, "_blank");
        }
      } else if (event.key === "Escape") {
        hideProfileModal();
      }
    }

    const activeTag = document.activeElement ? document.activeElement.tagName : "";
    const isEditing =
      ["INPUT", "TEXTAREA"].includes(activeTag) ||
      (document.activeElement && document.activeElement.isContentEditable);
    if (!isEditing && (event.key === "d" || event.key === "D" || event.key === "v" || event.key === "V")) {
      const isCallActive =
        state.bridged ||
        (state.liveSessionId && !byId("dialer-bridge")?.hidden) ||
        (dialog && dialog.open);
      if (isCallActive) {
        event.preventDefault();
        dropActiveVoicemail();
      }
    }
    if (!isEditing && (event.key === "x" || event.key === "X" || event.key === "n" || event.key === "N")) {
      const isCallActive =
        state.bridged ||
        (state.liveSessionId && !byId("dialer-bridge")?.hidden) ||
        (dialog && dialog.open);
      if (isCallActive) {
        event.preventDefault();
        disqualifyActiveCall();
      }
    }
  });

  // Close CRM & Twilio Settings Dialog
  const settingsBtn = byId("dialer-settings-btn");
  const settingsDialog = byId("dialer-settings-dialog");
  const settingsClose = byId("dialer-settings-close");
  const settingsStatusText = byId("dialer-key-status-text");
  const settingsStatusWrap = byId("dialer-key-status");
  const settingsKeyInput = byId("dialer-api-key-input");
  const settingsFeedback = byId("dialer-settings-feedback");
  const settingsSaveBtn = byId("dialer-save-key-btn");
  const settingsRemoveBtn = byId("dialer-remove-key-btn");

  const twilioStatusWrap = byId("dialer-twilio-status");
  const twilioStatusText = byId("dialer-twilio-status-text");
  const twilioAccountInput = byId("dialer-twilio-account-input");
  const twilioApiKeyInput = byId("dialer-twilio-api-key-input");
  const twilioSecretInput = byId("dialer-twilio-secret-input");
  const twilioFeedback = byId("dialer-twilio-feedback");
  const twilioSaveBtn = byId("dialer-save-twilio-btn");
  const twilioRemoveBtn = byId("dialer-remove-twilio-btn");

  const showSettingsFeedback = (msg, type = "error") => {
    if (!settingsFeedback) return;
    settingsFeedback.textContent = msg;
    settingsFeedback.className = `dialer-settings-feedback ${type}`;
    settingsFeedback.hidden = false;
  };

  const hideSettingsFeedback = () => {
    if (!settingsFeedback) return;
    settingsFeedback.textContent = "";
    settingsFeedback.hidden = true;
  };

  const showTwilioFeedback = (msg, type = "error") => {
    if (!twilioFeedback) return;
    twilioFeedback.textContent = msg;
    twilioFeedback.className = `dialer-settings-feedback ${type}`;
    twilioFeedback.hidden = false;
  };

  const hideTwilioFeedback = () => {
    if (!twilioFeedback) return;
    twilioFeedback.textContent = "";
    twilioFeedback.hidden = true;
  };

  const fetchSettingsStatus = async () => {
    if (settingsStatusText) settingsStatusText.textContent = "Checking Close connection...";
    if (settingsStatusWrap) settingsStatusWrap.classList.remove("connected");
    hideSettingsFeedback();
    try {
      const res = await fetch("/dialer/api/settings");
      const data = await res.json();
      if (data.configured) {
        if (settingsStatusWrap) settingsStatusWrap.classList.add("connected");
        if (data.is_custom) {
          settingsStatusText.textContent = `Connected as ${data.user_name || operatorEmail} (${data.key_masked})`;
          if (settingsRemoveBtn) settingsRemoveBtn.hidden = false;
        } else {
          settingsStatusText.textContent = `Using default organization key (${data.key_masked})`;
          if (settingsRemoveBtn) settingsRemoveBtn.hidden = true;
        }
      } else {
        if (settingsStatusWrap) settingsStatusWrap.classList.remove("connected");
        settingsStatusText.textContent = "No personal Close key connected. Please add your key below.";
        if (settingsRemoveBtn) settingsRemoveBtn.hidden = true;
      }
    } catch (_err) {
      if (settingsStatusText) settingsStatusText.textContent = "Could not check Close key status.";
    }
  };

  const fetchTwilioSettingsStatus = async () => {
    if (twilioStatusText) twilioStatusText.textContent = "Checking Twilio connection...";
    if (twilioStatusWrap) twilioStatusWrap.classList.remove("connected");
    hideTwilioFeedback();
    try {
      const res = await fetch("/dialer/api/twilio-settings");
      const data = await res.json();
      if (data.configured) {
        if (twilioStatusWrap) twilioStatusWrap.classList.add("connected");
        const displaySid = data.account_sid || data.account_sid_masked || "";
        if (data.is_custom) {
          twilioStatusText.textContent = `Connected with Twilio Account (${displaySid})`;
          if (twilioRemoveBtn) twilioRemoveBtn.hidden = false;
        } else {
          twilioStatusText.textContent = `Using default organization Twilio account (${displaySid})`;
          if (twilioRemoveBtn) twilioRemoveBtn.hidden = true;
        }
        if (twilioAccountInput) {
          twilioAccountInput.value = data.account_sid || "";
        }
        if (twilioApiKeyInput) {
          twilioApiKeyInput.value = data.api_key_sid || "";
        }
        if (twilioSecretInput && data.api_key_secret) {
          twilioSecretInput.value = data.api_key_secret;
        }
      } else {
        if (twilioStatusWrap) twilioStatusWrap.classList.remove("connected");
        twilioStatusText.textContent = "Twilio credentials not configured.";
        if (twilioRemoveBtn) twilioRemoveBtn.hidden = true;
      }
    } catch (_err) {
      if (twilioStatusText) twilioStatusText.textContent = "Could not check Twilio status.";
    }
  };

  if (settingsBtn && settingsDialog) {
    settingsBtn.addEventListener("click", () => {
      if (typeof settingsDialog.showModal === "function") {
        settingsDialog.showModal();
        fetchSettingsStatus();
        fetchTwilioSettingsStatus();
      }
    });
  }

  if (settingsClose && settingsDialog) {
    settingsClose.addEventListener("click", () => {
      settingsDialog.close();
    });
  }

  if (settingsSaveBtn && settingsKeyInput) {
    settingsSaveBtn.addEventListener("click", async () => {
      const key = settingsKeyInput.value.trim();
      if (!key) {
        showSettingsFeedback("Please enter a Close API key.");
        return;
      }
      if (!key.startsWith("api_") || key.length < 15) {
        showSettingsFeedback("Close API keys must start with 'api_' and be at least 15 characters long.");
        return;
      }
      hideSettingsFeedback();
      settingsSaveBtn.disabled = true;
      settingsSaveBtn.textContent = "Validating...";
      try {
        const res = await fetch("/dialer/api/settings", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ api_key: key }),
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          showSettingsFeedback(data.error || "Failed to validate Close API key.");
          settingsSaveBtn.disabled = false;
          settingsSaveBtn.textContent = "Save & Connect";
          return;
        }
        showSettingsFeedback(`Connected to Close CRM as ${data.user_name || "user"}! Reloading your lists...`, "success");
        settingsKeyInput.value = "";
        settingsSaveBtn.textContent = "Connected!";
        setTimeout(() => {
          window.location.reload();
        }, 1000);
      } catch (_err) {
        showSettingsFeedback("Network error connecting to Close CRM.");
        settingsSaveBtn.disabled = false;
        settingsSaveBtn.textContent = "Save & Connect";
      }
    });
  }

  if (settingsRemoveBtn) {
    settingsRemoveBtn.addEventListener("click", async () => {
      if (!confirm("Are you sure you want to disconnect your personal Close API key?")) return;
      settingsRemoveBtn.disabled = true;
      settingsRemoveBtn.textContent = "Disconnecting...";
      try {
        await fetch("/dialer/api/settings", { method: "DELETE" });
        showSettingsFeedback("Disconnected key. Reloading...", "success");
        setTimeout(() => {
          window.location.reload();
        }, 800);
      } catch (_err) {
        settingsRemoveBtn.disabled = false;
        settingsRemoveBtn.textContent = "Disconnect Key";
      }
    });
  }

  if (twilioSaveBtn) {
    twilioSaveBtn.addEventListener("click", async () => {
      const accountSid = twilioAccountInput ? twilioAccountInput.value.trim() : "";
      const apiKeySid = twilioApiKeyInput ? twilioApiKeyInput.value.trim() : "";
      const apiSecret = twilioSecretInput ? twilioSecretInput.value.trim() : "";

      if (!accountSid.startsWith("AC") || accountSid.length < 30) {
        showTwilioFeedback("Account SID must start with 'AC' and be 34 characters long.");
        return;
      }
      if (!apiKeySid.startsWith("SK") || apiKeySid.length < 30) {
        showTwilioFeedback("API Key SID must start with 'SK' and be 34 characters long.");
        return;
      }
      if (!apiSecret) {
        showTwilioFeedback("Please enter your API Key Secret.");
        return;
      }

      hideTwilioFeedback();
      twilioSaveBtn.disabled = true;
      twilioSaveBtn.textContent = "Validating...";
      try {
        const res = await fetch("/dialer/api/twilio-settings", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            account_sid: accountSid,
            api_key_sid: apiKeySid,
            api_key_secret: apiSecret,
          }),
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          showTwilioFeedback(data.error || "Failed to update Twilio credentials.");
          twilioSaveBtn.disabled = false;
          twilioSaveBtn.textContent = "Update Twilio Credentials";
          return;
        }
        showTwilioFeedback("Successfully connected Twilio credentials!", "success");
        if (twilioSecretInput) twilioSecretInput.value = "";
        twilioSaveBtn.disabled = false;
        twilioSaveBtn.textContent = "Update Twilio Credentials";
        fetchTwilioSettingsStatus();
        fetchDialerNumbers();
      } catch (_err) {
        showTwilioFeedback("Network error connecting to Twilio.");
        twilioSaveBtn.disabled = false;
        twilioSaveBtn.textContent = "Update Twilio Credentials";
      }
    });
  }

  if (twilioRemoveBtn) {
    twilioRemoveBtn.addEventListener("click", async () => {
      if (!confirm("Are you sure you want to revert to the organization default Twilio credentials?")) return;
      twilioRemoveBtn.disabled = true;
      twilioRemoveBtn.textContent = "Reverting...";
      try {
        await fetch("/dialer/api/twilio-settings", { method: "DELETE" });
        showTwilioFeedback("Reverted to organization default Twilio account.", "success");
        if (twilioAccountInput) twilioAccountInput.value = "";
        if (twilioApiKeyInput) twilioApiKeyInput.value = "";
        if (twilioSecretInput) twilioSecretInput.value = "";
        twilioRemoveBtn.disabled = false;
        twilioRemoveBtn.textContent = "Use Organization Default";
        fetchTwilioSettingsStatus();
        fetchDialerNumbers();
      } catch (_err) {
        twilioRemoveBtn.disabled = false;
        twilioRemoveBtn.textContent = "Use Organization Default";
      }
    });
  }

  // Outbound Phone Numbers Dialog
  const numbersBtn = byId("dialer-numbers-btn");
  const numbersDialog = byId("dialer-numbers-dialog");
  const numbersClose = byId("dialer-numbers-close");
  const numbersList = byId("dialer-numbers-list");
  const numbersPill = byId("dialer-numbers-pill");
  const buyNumberBtn = byId("dialer-buy-number-btn");
  const buyPanel = byId("dialer-buy-panel");
  const buyAreaCodeInput = byId("dialer-buy-area-code");
  const buyLabelInput = byId("dialer-buy-label");
  const confirmBuyBtn = byId("dialer-confirm-buy-btn");
  const cancelBuyBtn = byId("dialer-cancel-buy-btn");
  const buyFeedback = byId("dialer-buy-feedback");

  const showBuyFeedback = (msg, type = "error") => {
    if (!buyFeedback) return;
    buyFeedback.textContent = msg;
    buyFeedback.className = `dialer-buy-feedback ${type}`;
    buyFeedback.hidden = false;
  };

  const hideBuyFeedback = () => {
    if (!buyFeedback) return;
    buyFeedback.textContent = "";
    buyFeedback.hidden = true;
  };

  if (buyNumberBtn && buyPanel) {
    buyNumberBtn.addEventListener("click", () => {
      buyPanel.hidden = !buyPanel.hidden;
      hideBuyFeedback();
      if (!buyPanel.hidden && buyAreaCodeInput) {
        buyAreaCodeInput.focus();
      }
    });
  }

  if (cancelBuyBtn && buyPanel) {
    cancelBuyBtn.addEventListener("click", () => {
      buyPanel.hidden = true;
      hideBuyFeedback();
    });
  }

  if (confirmBuyBtn) {
    confirmBuyBtn.addEventListener("click", async () => {
      const areaCode = buyAreaCodeInput ? buyAreaCodeInput.value.trim() : "";
      const label = buyLabelInput ? buyLabelInput.value.trim() : "";

      if (areaCode && !/^\d{3}$/.test(areaCode)) {
        showBuyFeedback("Area code must be a 3-digit US code (e.g. 816, 860, 701).");
        return;
      }

      hideBuyFeedback();
      confirmBuyBtn.disabled = true;
      confirmBuyBtn.textContent = "Purchasing...";

      try {
        const res = await fetch("/dialer/api/numbers/buy", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            area_code: areaCode || undefined,
            label: label || undefined,
          }),
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          showBuyFeedback(data.error || "Failed to purchase phone number.");
          confirmBuyBtn.disabled = false;
          confirmBuyBtn.textContent = "Purchase Clean Number";
          return;
        }

        showBuyFeedback(`Purchased ${formatPhone(data.phone_number) || data.phone_number}! Voice callback webhook configured.`, "success");
        if (buyAreaCodeInput) buyAreaCodeInput.value = "";
        if (buyLabelInput) buyLabelInput.value = "";
        confirmBuyBtn.disabled = false;
        confirmBuyBtn.textContent = "Purchase Clean Number";

        setTimeout(() => {
          if (buyPanel) buyPanel.hidden = true;
          hideBuyFeedback();
        }, 1500);

        fetchDialerNumbers();
      } catch (_err) {
        showBuyFeedback("Network error purchasing phone number.");
        confirmBuyBtn.disabled = false;
        confirmBuyBtn.textContent = "Purchase Clean Number";
      }
    });
  }

  const renderNumbersList = (numbers = []) => {
    if (!numbersList) return;
    numbersList.replaceChildren();

    if (!numbers.length) {
      const empty = document.createElement("div");
      empty.className = "dialer-numbers-empty";
      empty.textContent = "No phone numbers currently assigned to your account.";
      numbersList.append(empty);
      return;
    }

    numbers.forEach((item) => {
      const card = document.createElement("div");
      card.className = "dialer-number-card";

      const icon = document.createElement("div");
      icon.className = "dialer-number-icon";
      icon.textContent = "📞";

      const info = document.createElement("div");
      info.className = "dialer-number-info";

      const labelRow = document.createElement("div");
      labelRow.className = "dialer-number-label-row";

      const labelEl = document.createElement("span");
      labelEl.className = "dialer-number-label";
      labelEl.textContent = item.label || "Number";

      const renameBtn = document.createElement("button");
      renameBtn.type = "button";
      renameBtn.className = "text-button dialer-number-rename-btn";
      renameBtn.textContent = "Rename";

      labelRow.append(labelEl, renameBtn);
      if (item.primary) {
        const mainTag = document.createElement("span");
        mainTag.className = "dialer-number-main-tag";
        mainTag.textContent = "Main line";
        mainTag.title = "The main line: callbacks ring here, and it is never released.";
        labelRow.append(mainTag);
      }

      const phoneEl = document.createElement("span");
      phoneEl.className = "dialer-number-phone";
      phoneEl.textContent = formatPhone(item.phone_number) || item.friendly_name || item.phone_number;

      const metaEl = document.createElement("span");
      metaEl.className = "dialer-number-meta";
      metaEl.textContent = `${item.sid ? `Twilio ${item.sid} · ` : ""}Inbound callbacks enabled`;

      info.append(labelRow, phoneEl, metaEl);

      // Actions container: Health Badge + Replace (if cooked) + Delete
      const actions = document.createElement("div");
      actions.className = "dialer-number-actions";

      const health = item.health || { status: "fresh", badge: "Fresh", message: "New number, no call history yet." };
      const healthBadge = document.createElement("span");
      healthBadge.className = `health-badge ${health.status || "fresh"}`;
      healthBadge.title = health.message || "";
      healthBadge.textContent = `● ${health.badge || "Fresh"}`;
      actions.append(healthBadge);

      if (health.status === "cooked") {
        const replaceBtn = document.createElement("button");
        replaceBtn.type = "button";
        replaceBtn.className = "dialer-number-replace-btn";
        replaceBtn.textContent = "Replace";
        replaceBtn.title = "Release this cooked number and buy a fresh replacement in the same area code";
        replaceBtn.addEventListener("click", async () => {
          if (!confirm(`Replace cooked number ${item.label || "Number"} (${formatPhone(item.phone_number)}) with a fresh number?${item.primary ? " The fresh number becomes the main line." : ""}`)) return;
          replaceBtn.disabled = true;
          replaceBtn.textContent = "Replacing...";
          try {
            if (item.primary) {
              // Buy first and hand the main line over, so it is never without one.
              const clean = (item.phone_number || "").replace(/[^\d]/g, "");
              const code = clean.length === 11 && clean.startsWith("1") ? clean.slice(1, 4) : clean.slice(0, 3);
              const bought = await apiRequest("/dialer/api/numbers/buy", {
                method: "POST",
                body: JSON.stringify({ area_code: code || undefined, label: item.label || undefined }),
              });
              await apiRequest(`/dialer/api/numbers/${encodeURIComponent(bought.number.sid)}/main`, { method: "POST", body: "{}" });
              await apiRequest(`/dialer/api/numbers/${encodeURIComponent(item.sid)}`, { method: "DELETE" });
              await fetchDialerNumbers();
              return;
            }
            const delRes = await fetch(`/dialer/api/numbers/${encodeURIComponent(item.sid)}`, { method: "DELETE" });
            if (!delRes.ok) {
              const errData = await delRes.json();
              alert(errData.error || "Failed to release cooked number.");
              replaceBtn.disabled = false;
              replaceBtn.textContent = "Replace";
              return;
            }
            let areaCode = "";
            const clean = (item.phone_number || "").replace(/[^\d]/g, "");
            if (clean.length === 11 && clean.startsWith("1")) {
              areaCode = clean.slice(1, 4);
            } else if (clean.length === 10) {
              areaCode = clean.slice(0, 3);
            }
            const buyRes = await fetch("/dialer/api/numbers/buy", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                area_code: areaCode || undefined,
                label: item.label || undefined,
              }),
            });
            const buyData = await buyRes.json();
            if (!buyRes.ok || buyData.error) {
              alert(`Released cooked number, but purchase of replacement failed: ${buyData.error || "unknown error"}`);
            }
            await fetchDialerNumbers();
          } catch (err) {
            alert(err && err.message ? err.message : "Error during number replacement.");
            replaceBtn.disabled = false;
            replaceBtn.textContent = "Replace";
          }
        });
        actions.append(replaceBtn);
      }

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "text-button dialer-number-delete-btn";
      deleteBtn.textContent = "Delete";
      deleteBtn.title = "Release phone number from Twilio account";
      deleteBtn.addEventListener("click", async () => {
        const question = item.primary
          ? `Delete the main line ${formatPhone(item.phone_number)}? It is released from Twilio for good, and callbacks to it stop. Your healthiest other number becomes the main line.`
          : `Are you sure you want to delete ${item.label || "this number"} (${formatPhone(item.phone_number)})? This will permanently release the number from your Twilio account.`;
        if (!confirm(question)) return;
        deleteBtn.disabled = true;
        deleteBtn.textContent = "Deleting...";
        try {
          const res = await fetch(`/dialer/api/numbers/${encodeURIComponent(item.sid)}`, { method: "DELETE" });
          const data = await res.json();
          if (!res.ok || data.error) {
            alert(data.error || "Failed to delete number.");
            deleteBtn.disabled = false;
            deleteBtn.textContent = "Delete";
            return;
          }
          await fetchDialerNumbers();
        } catch (_err) {
          alert("Network error deleting phone number.");
          deleteBtn.disabled = false;
          deleteBtn.textContent = "Delete";
        }
      });
      if (!item.primary && String(item.sid || "").startsWith("PN")) {
        const mainBtn = document.createElement("button");
        mainBtn.type = "button";
        mainBtn.className = "text-button dialer-number-main-btn";
        mainBtn.textContent = "Make main line";
        mainBtn.title = "Use this number as the main line: the default caller ID, the number your softphone leg comes from, and a callback line.";
        mainBtn.addEventListener("click", async () => {
          if (!confirm(`Make ${formatPhone(item.phone_number)} the main line? The current main line stays one of your numbers.`)) return;
          mainBtn.disabled = true;
          try {
            await apiRequest(`/dialer/api/numbers/${encodeURIComponent(item.sid)}/main`, { method: "POST", body: "{}" });
            await fetchDialerNumbers();
          } catch (err) {
            alert(err.message || "The main line could not be switched.");
            mainBtn.disabled = false;
          }
        });
        actions.append(mainBtn);
      }
      actions.append(deleteBtn);

      card.append(icon, info, actions);
      numbersList.append(card);

      renameBtn.addEventListener("click", () => {
        const editWrap = document.createElement("div");
        editWrap.className = "dialer-number-edit-wrap";

        const input = document.createElement("input");
        input.type = "text";
        input.className = "dialer-number-edit-input";
        input.value = item.label || "";
        input.placeholder = "e.g. Number 1";
        input.maxLength = 40;

        const saveBtn = document.createElement("button");
        saveBtn.type = "button";
        saveBtn.className = "btn-sm-primary";
        saveBtn.textContent = "Save";

        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.className = "text-button";
        cancelBtn.textContent = "Cancel";

        editWrap.append(input, saveBtn, cancelBtn);
        info.replaceChild(editWrap, labelRow);
        input.focus();

        const restoreLabelRow = () => {
          if (info.contains(editWrap)) {
            info.replaceChild(labelRow, editWrap);
          }
        };

        cancelBtn.addEventListener("click", restoreLabelRow);

        const handleSave = async () => {
          const newLabel = input.value.trim();
          if (!newLabel || newLabel === item.label) {
            restoreLabelRow();
            return;
          }
          saveBtn.disabled = true;
          saveBtn.textContent = "Saving...";
          try {
            const res = await fetch(`/dialer/api/numbers/${encodeURIComponent(item.sid)}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ label: newLabel }),
            });
            const data = await res.json();
            if (!res.ok || data.error) {
              alert(data.error || "Failed to update label.");
              saveBtn.disabled = false;
              saveBtn.textContent = "Save";
              return;
            }
            item.label = newLabel;
            labelEl.textContent = newLabel;
            restoreLabelRow();
          } catch (_err) {
            alert("Network error updating number label.");
            saveBtn.disabled = false;
            saveBtn.textContent = "Save";
          }
        };

        saveBtn.addEventListener("click", handleSave);
        input.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            handleSave();
          } else if (e.key === "Escape") {
            e.preventDefault();
            restoreLabelRow();
          }
        });
      });
    });
  };

  const fetchDialerNumbers = async () => {
    if (!numbersList) return;
    numbersList.innerHTML = '<div class="dialer-numbers-loading">Loading numbers...</div>';
    try {
      const res = await fetch("/dialer/api/numbers");
      const data = await res.json();
      if (!res.ok || data.error) {
        numbersList.innerHTML = `<div class="dialer-numbers-error">${data.error || "Could not load phone numbers."}</div>`;
        return;
      }
      if (data.count != null && numbersPill) {
        numbersPill.textContent = String(data.count);
      }
      renderNumbersList(data.numbers || []);
    } catch (_err) {
      numbersList.innerHTML = '<div class="dialer-numbers-error">Failed to connect to phone number service.</div>';
    }
  };

  if (numbersBtn && numbersDialog) {
    numbersBtn.addEventListener("click", () => {
      if (typeof numbersDialog.showModal === "function") {
        numbersDialog.showModal();
        fetchDialerNumbers();
      }
    });
  }

  if (numbersClose && numbersDialog) {
    numbersClose.addEventListener("click", () => {
      numbersDialog.close();
    });
  }

  byId("dialer-start").classList.add("live");
  if (activeSessionId) {
    state.running = true;
    state.liveSessionId = activeSessionId;
    byId("dialer-smart-view").disabled = true;
    byId("dialer-reset-progress").hidden = true;
    byId("dialer-session-state").textContent = "Reconnecting";
    byId("dialer-live-title").textContent = "Reconnecting to active session";
  } else {
    byId("dialer-session-state").textContent = "Standing by";
  }
  fetchTalkTrack();
  initScriptNotepad();
  initTimezoneWave();
  updateStartCopy();
  updateButtons();
  updateMetrics();
  if (activeSessionId) pollLiveSession();
})();
