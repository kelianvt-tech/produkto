(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = (id, cls = 'icon') => `<svg class="${cls}" aria-hidden="true"><use href="#i-${id}"/></svg>`;
  if (reduceMotion.matches) document.documentElement.classList.add('no-motion');

  /* ---------- Header ---------- */
  const header = $('[data-header]');
  /* Hides while scrolling down, comes back as soon as you scroll up. */
  let lastY = window.scrollY;
  const onScroll = () => {
    const y = window.scrollY;
    header.classList.toggle('is-scrolled', y > 8);
    if (Math.abs(y - lastY) < 6) return;
    const menuOpen = $('#nav-toggle')?.getAttribute('aria-expanded') === 'true';
    header.classList.toggle('is-hidden', y > lastY && y > header.offsetHeight && !menuOpen);
    lastY = y;
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  header.addEventListener('focusin', () => header.classList.remove('is-hidden'));
  onScroll();

  const toggle = $('#nav-toggle');
  const menu = $('#mobile-menu');
  const setMenu = (open) => {
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    menu.hidden = !open;
  };
  toggle.addEventListener('click', () => setMenu(toggle.getAttribute('aria-expanded') !== 'true'));
  $$('a', menu).forEach((a) => a.addEventListener('click', () => setMenu(false)));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !menu.hidden) { setMenu(false); toggle.focus(); } });
  window.addEventListener('resize', () => { if (window.innerWidth > 900 && !menu.hidden) setMenu(false); });

  /* ---------- Rotating assistant name in the hero (every 3 seconds) ---------- */
  const rotator = $('[data-rotator]');
  if (rotator) {
    const items = $$('.rot-item', rotator);
    let current = 0;
    let rotTimer = null;
    const tick = () => {
      const leaving = items[current];
      current = (current + 1) % items.length;
      leaving.classList.remove('is-active');
      leaving.classList.add('is-leaving');
      items[current].classList.remove('is-leaving');
      items[current].classList.add('is-active');
      setTimeout(() => leaving.classList.remove('is-leaving'), 700);
    };
    const start = () => { clearInterval(rotTimer); rotTimer = setInterval(tick, 3000); };
    document.addEventListener('visibilitychange', () => (document.hidden ? clearInterval(rotTimer) : start()));
    start();
  }

  /* ---------- Statement: words light up as you scroll through the section ---------- */
  const statementText = $('[data-scroll-reveal]');
  if (statementText) {
    $$('p', statementText).forEach((p) => {
      p.innerHTML = p.textContent.split(/(\s+)/).map((t) => (/^\s+$/.test(t) ? t : `<span class="w">${esc(t)}</span>`)).join('');
    });
    const words = $$('.w', statementText);
    const statementSection = statementText.closest('.statement');
    const updateStatement = () => {
      if (reduceMotion.matches) { words.forEach((w) => { w.style.opacity = '1'; w.style.filter = 'none'; }); return; }
      const r = statementSection.getBoundingClientRect();
      const lead = window.innerHeight * 0.35;
      const travel = r.height - window.innerHeight + lead;
      const progress = Math.min(1, Math.max(0, (lead - r.top) / travel));
      statementSection.style.setProperty('--sp', progress.toFixed(4));
      const lit = progress * (words.length + 2);
      /* Unlit words are faint and blurred so they can't be read yet; each sharpens as it lights up. */
      words.forEach((w, i) => {
        const k = Math.min(1, Math.max(0, lit - i));
        w.style.opacity = (0.3 + k * 0.7).toFixed(3);
        w.style.filter = k >= 1 ? 'none' : `blur(${((1 - k) * 8).toFixed(2)}px)`;
      });
    };
    window.addEventListener('scroll', updateStatement, { passive: true });
    window.addEventListener('resize', updateStatement);
    updateStatement();

  }

  // Share the same star density, brightness and drift across the approved navy sections.
  $$('#statement, #answer, #request, .footer').forEach((skySection) => {
    const sky = $('.starfield', skySection);
    const ctx = sky && sky.getContext('2d');
    if (ctx) {
      let stars = [];
      let w = 0;
      let h = 0;
      let running = false;
      const resize = () => {
        const dpr = Math.min(2, window.devicePixelRatio || 1);
        w = sky.clientWidth; h = sky.clientHeight;
        sky.width = w * dpr; sky.height = h * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        stars = Array.from({ length: Math.round((w * h) / 5200) }, () => ({
          x: Math.random() * w, y: Math.random() * h,
          r: Math.random() < 0.9 ? 0.35 + Math.random() * 0.6 : 1 + Math.random() * 0.5,
          depth: 0.2 + Math.random() * 0.8,
          a: 0.15 + Math.random() * 0.4,
          tw: Math.random() * Math.PI * 2
        }));
      };
      const draw = (now) => {
        const t = reduceMotion.matches ? 0 : now / 1000;
        // One scroll-distance scale for every sky, independent of section height.
        // Keep this separate from the statement's word-reveal progress.
        const r = skySection.getBoundingClientRect();
        const sp = reduceMotion.matches ? 0 : Math.max(0, (innerHeight - r.top) / innerHeight);
        skySection.style.setProperty('--sky-sp', sp.toFixed(4));
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = '#fff';
        for (const s of stars) {
          const y = (((s.y - t * 3 * s.depth - sp * 160 * s.depth) % h) + h) % h;
          const x = (s.x + t * 1.5 * s.depth) % w;
          ctx.globalAlpha = reduceMotion.matches ? s.a : s.a * (0.65 + 0.35 * Math.sin(t * 0.8 + s.tw));
          ctx.beginPath();
          ctx.arc(x, y, s.r, 0, Math.PI * 2);
          ctx.fill();
        }
        if (running && !reduceMotion.matches) requestAnimationFrame(draw);
      };
      resize();
      window.addEventListener('resize', resize);
      new IntersectionObserver(([e]) => {
        const was = running;
        running = e.isIntersecting;
        if (running && !was) requestAnimationFrame(draw);
      }).observe(skySection);
      draw(performance.now());
    }
  });

  /* ---------- Reveal + active nav ----------
     Reveal on a plain position check so content can never stay hidden if observer
     callbacks are delayed. Anything above the fold, or already scrolled past, shows at once. */
  let pending = $$('[data-reveal], [data-animate]');
  const checkReveal = () => {
    if (!pending.length) return;
    const limit = window.innerHeight * 0.94;
    pending = pending.filter((el) => {
      if (el.getBoundingClientRect().top < limit) { el.classList.add('is-in'); return false; }
      return true;
    });
    if (!pending.length) { window.removeEventListener('scroll', checkReveal); window.removeEventListener('resize', checkReveal); }
  };
  window.addEventListener('scroll', checkReveal, { passive: true });
  window.addEventListener('resize', checkReveal);
  checkReveal();

  /* ---------- Why-now figures count up from 0 the first time they come into view ---------- */
  let counters = reduceMotion.matches ? [] : $$('.stat-value').map((el) => {
    const m = el.textContent.trim().match(/^([^\d]*)([\d.,]+)(.*)$/);
    if (!m) return null;
    el.setAttribute('aria-label', el.textContent.trim());
    const counter = { el, pre: m[1], target: parseFloat(m[2].replace(/,/g, '')), post: m[3] };
    el.textContent = `${counter.pre}0${counter.post}`;
    return counter;
  }).filter(Boolean);
  const runCounter = ({ el, pre, target, post }) => {
    const t0 = performance.now();
    const frame = (now) => {
      const p = Math.min(1, (now - t0) / 1400);
      el.textContent = `${pre}${Math.round(target * (1 - Math.pow(1 - p, 3)))}${post}`;
      if (p < 1) requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  };
  const checkCounters = () => {
    const limit = window.innerHeight * 0.85;
    counters = counters.filter((c) => {
      if (c.el.getBoundingClientRect().top < limit) { runCounter(c); return false; }
      return true;
    });
    if (!counters.length) window.removeEventListener('scroll', checkCounters);
  };
  if (counters.length) {
    window.addEventListener('scroll', checkCounters, { passive: true });
    checkCounters();
  }

  if ('IntersectionObserver' in window) {
    /* Only in-page links: Netlify rewrites pricing.html to /pricing, which isn't a valid selector. */
    const navLinks = $$('.nav-links a').filter((a) => (a.getAttribute('href') || '').startsWith('#'));
    const sections = navLinks.map((a) => $(a.getAttribute('href'))).filter(Boolean);
    const navIO = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        navLinks.forEach((a) => a.setAttribute('aria-current', String(a.getAttribute('href') === '#' + e.target.id)));
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    sections.forEach((s) => navIO.observe(s));
  }

  /* ---------- AI answers: real ChatGPT responses captured 16 Sep 2026 (chatgpt.com, logged in, Instant).
     Opening sentence and the first three product cards, as shown. Record: ../chatgpt-captures-2026-09-16.md ---------- */
  const ANSWERS = [
    {
      q: 'What’s the best waterproof rain jacket under €250 for hiking?',
      text: 'For hiking under €250, my top pick is the Patagonia Torrentshell 3L.',
      picks: [
        { name: 'Patagonia Torrentshell 3L', brand: 'Patagonia', price: '€200.00', rating: 4.6, note: 'Durable, waterproof Patagonia jacket, ideal for outdoor adventures.', img: 'chatgpt-jacket-torrentshell.webp' },
        { name: 'Rab Downpour', brand: 'Rab', price: '€157.21', rating: 5.0, note: 'Highly rated Rab Downpour rain jacket, perfect for wet weather.', img: 'chatgpt-jacket-downpour.webp' },
        { name: 'Rab Firewall Light', brand: 'Rab', price: '€215.99', rating: 5.0, note: 'Lightweight Rab Firewall Light, great for active outdoor use.', img: 'chatgpt-jacket-firewall.webp' }
      ]
    },
    {
      q: 'Best rain trousers under €100 with full side zips?',
      text: 'For under €100 and genuinely full-length side zips, the standout is the Marmot PreCip Eco Full Zip.',
      picks: [
        { name: 'Marmot Men’s PreCip Eco Full Zip Rain Pant', brand: 'Marmot', price: '€69.95', rating: 4.5, note: 'outdoor-works.de', img: 'chatgpt-trousers-precip.webp' },
        { name: 'Rab Downpour Eco Full-Zip Pants', brand: 'Rab', price: '€86.79', rating: null, note: 'Water-resistant pants suitable for outdoor activities.', img: 'chatgpt-trousers-downpour.webp' },
        { name: 'Berghaus Deluge 2.0 Pant', brand: 'Berghaus', price: '€90.00', rating: 4.8, note: 'High-rated waterproof pants for active use.', img: 'chatgpt-trousers-deluge.webp' }
      ]
    },
    {
      q: 'Warm sleeping bag rated for −5 °C that packs small?',
      text: 'For a sleeping bag that will handle nights around −5 °C while packing genuinely small, I’d strongly favor high-fill-power down (800–900 FP) over synthetic.',
      picks: [
        { name: 'Therm-a-Rest Hyperion 20F/−6C', brand: 'Therm-a-Rest', price: '€462.90', rating: 4.6, note: 'EpicTV + others', img: 'chatgpt-sleepingbag-hyperion.webp' },
        { name: 'Sea to Summit Spark −9°C', brand: 'Sea to Summit', price: '€494.96', rating: null, note: 'Lightweight sleeping bag for cold weather camping.', img: 'chatgpt-sleepingbag-spark9.webp' },
        { name: 'Sea to Summit Spark Down Sleeping Bag', brand: 'Sea to Summit', price: '€434.90', rating: 4.7, note: 'High-quality down insulation for warmth and packability.', img: 'chatgpt-sleepingbag-sparkdown.webp' }
      ]
    }
  ];
  const chatEl = $('#chat-content');
  const switchEl = $('#q-switch');
  const stars = (r) => '★'.repeat(Math.round(r)) + '☆'.repeat(5 - Math.round(r));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  let playId = 0;
  let current = 0;

  /* Builds the finished answer. With `animate`, every part starts hidden but keeps its space,
     so the panel doesn't change height while the answer plays in. */
  const renderAnswer = (i, animate) => {
    const a = ANSWERS[i];
    current = i;
    playId += 1;
    $$('button', switchEl).forEach((b, n) => b.setAttribute('aria-pressed', String(n === i)));
    chatEl.innerHTML = `
      <div class="chat-anim${animate ? ' is-anim' : ''}">
        <div class="chat-body">
          <p class="bubble-user">${esc(a.q)}</p>
          <div class="bubble-ai">
            <span class="ai-avatar">${icon('openai')}</span>
            <div class="ai-col">
              <span class="ai-thinking" aria-hidden="true">Searching products<i></i><i></i><i></i></span>
              <p class="ai-text">${a.text.split(' ').map((w) => `<span class="w">${esc(w)}</span>`).join(' ')}</p>
              <div class="picks">
                ${a.picks.map((p, n) => `
                  <div class="p-card">
                    <span class="p-img is-photo"><img src="assets/${p.img}" alt="${esc(p.name)}, as shown in the AI answer" width="300" height="315" loading="lazy" decoding="async"></span>
                    <span class="p-rank">#${n + 1}</span>
                    <strong>${esc(p.name)}</strong>
                    <span class="p-meta"><span>${esc(p.brand)}</span><span>${esc(p.price)}</span></span>
                    ${p.rating ? `<span class="p-stars" role="img" aria-label="Rated ${p.rating.toFixed(1)} out of 5">${stars(p.rating)}<em>${p.rating.toFixed(1)}</em></span>` : '<span class="p-stars is-empty">No rating shown</span>'}
                    <span class="p-note">${esc(p.note)}</span>
                  </div>`).join('')}
              </div>
            </div>
          </div>
        </div>
        <p class="chat-flag is-hit">${icon('search')}<span><b>Is your product one of these?</b> Produkto runs questions like this for your product and shows who AI picks instead.</span></p>
        <div class="composer" aria-hidden="true">
          <span class="composer-field"><span class="composer-ph">Ask anything</span><span class="composer-text"></span><span class="composer-caret"></span></span>
          <span class="composer-send">${icon('arrow-right')}</span>
        </div>
      </div>`;
    return $('.chat-anim', chatEl);
  };

  /* Types the question, sends it, then plays the answer in: text word by word, then each pick. */
  const playAnswer = async (root, i) => {
    const run = playId;
    const live = () => run === playId;
    const step = async (ms) => { await wait(ms); return live(); };
    const composer = $('.composer', root);
    const typed = $('.composer-text', root);
    chatEl.setAttribute('aria-busy', 'true');

    composer.classList.add('is-typing');
    if (!await step(250)) return;
    for (const ch of ANSWERS[i].q) {
      typed.textContent += ch;
      typed.parentElement.scrollLeft = typed.parentElement.scrollWidth;
      composer.classList.add('has-text');
      if (!await step(ch === ' ' ? 30 : 14 + Math.random() * 14)) return;
    }
    if (!await step(250)) return;
    composer.classList.add('is-sending');
    if (!await step(150)) return;
    typed.textContent = '';
    composer.classList.remove('is-typing', 'has-text', 'is-sending');
    root.classList.add('is-sent');

    if (!await step(250)) return;
    root.classList.add('is-thinking');
    if (!await step(700)) return;
    root.classList.remove('is-thinking');
    root.classList.add('is-answering');
    for (const w of $$('.ai-text .w', root)) {
      w.classList.add('in');
      if (!await step(22)) return;
    }
    if (!await step(120)) return;
    for (const card of $$('.p-card', root)) {
      card.classList.add('in');
      if (!await step(110)) return;
    }
    if (!await step(250)) return;
    $('.chat-flag', root).classList.add('in');
    chatEl.setAttribute('aria-busy', 'false');
  };

  const showAnswer = (i) => {
    const animate = !reduceMotion.matches;
    const root = renderAnswer(i, animate);
    chatEl.setAttribute('aria-busy', 'false');
    if (animate) playAnswer(root, i);
  };

  /* Sets the answer to a point in its playback, 0 to 1. Used while the section is pinned,
     so scrolling plays it like the statement above; finishes at 0.85 to leave a beat to read. */
  const scrubAnswer = (root, i, p) => {
    const q = ANSWERS[i].q;
    const at = (a, b) => Math.min(1, Math.max(0, (p - a) / (b - a)));
    const composer = $('.composer', root);
    const typed = $('.composer-text', root);
    const sent = p >= 0.24;
    const chars = sent ? 0 : Math.round(at(0.02, 0.22) * q.length);
    if (typed.textContent.length !== chars) {
      typed.textContent = q.slice(0, chars);
      typed.parentElement.scrollLeft = typed.parentElement.scrollWidth;
    }
    composer.classList.toggle('is-typing', p > 0.01 && !sent);
    composer.classList.toggle('has-text', chars > 0);
    composer.classList.toggle('is-sending', p >= 0.22 && !sent);
    root.classList.toggle('is-sent', sent);
    root.classList.toggle('is-thinking', p >= 0.27 && p < 0.37);
    root.classList.toggle('is-answering', p >= 0.37);
    const words = $$('.ai-text .w', root);
    const lit = Math.round(at(0.37, 0.62) * words.length);
    words.forEach((w, n) => w.classList.toggle('in', n < lit));
    const cards = $$('.p-card', root);
    const shown = Math.floor(at(0.62, 0.78) * (cards.length + 0.999));
    cards.forEach((c, n) => c.classList.toggle('in', n < shown));
    $('.chat-flag', root).classList.toggle('in', p >= 0.85);
  };

  if (switchEl && chatEl) {
  switchEl.innerHTML = ANSWERS.map((a) => `<button type="button" aria-pressed="false"><span>“${esc(a.q)}”</span>${icon('arrow-right')}</button>`).join('');
  /* Keep in step with the #answer pin media query in styles.css. */
  const PIN_ANSWER = matchMedia('(min-width: 1101px) and (min-height: 760px) and (prefers-reduced-motion: no-preference)');
  const answerSection = $('#answer');
  let scrubbing = PIN_ANSWER.matches;
  $$('button', switchEl).forEach((b, i) => b.addEventListener('click', () => { scrubbing = false; showAnswer(i); }));

  if (scrubbing) {
    /* Pinned: scroll position plays the first answer until a visitor picks a question. */
    const scrubRoot = renderAnswer(0, true);
    let scrubFrame = 0;
    const updateScrub = () => {
      scrubFrame = 0;
      if (!scrubbing) return;
      const r = answerSection.getBoundingClientRect();
      const lead = window.innerHeight * 0.15;
      const travel = r.height - window.innerHeight + lead;
      scrubAnswer(scrubRoot, 0, Math.min(1, Math.max(0, (lead - r.top) / travel)));
    };
    const queueScrub = () => { if (!scrubFrame) scrubFrame = requestAnimationFrame(updateScrub); };
    window.addEventListener('scroll', queueScrub, { passive: true });
    window.addEventListener('resize', queueScrub);
    PIN_ANSWER.addEventListener('change', () => {
      if (PIN_ANSWER.matches || !scrubbing) return;
      scrubbing = false;
      renderAnswer(current, false);
    });
    updateScrub();
  } else if (!reduceMotion.matches && 'IntersectionObserver' in window) {
    /* First answer waits, hidden, until the message box is on screen, then plays once. */
    const firstRoot = renderAnswer(0, true);
    const chatIO = new IntersectionObserver((entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      chatIO.disconnect();
      showAnswer(current);
    }, { threshold: 1 });
    chatIO.observe($('.composer', firstRoot));
  } else {
    renderAnswer(0, false);
  }
  }

  /* ---------- "Or send a note" (Web3Forms delivers it by email) ---------- */
  const noteForm = $('#note-form');
  if (noteForm) {
    const noteKey = window.PRODUKTO_BOOKING?.noteKey?.trim();
    const status = $('#note-status');
    const say = (msg, ok) => { status.textContent = msg; status.hidden = false; status.classList.toggle('is-ok', !!ok); };
    noteForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!noteForm.checkValidity()) { say('Please add your name, a valid email and a short note.'); return; }
      if (!noteKey) { say('Notes aren\u2019t switched on yet. Please book a time above instead.'); return; }
      const btn = noteForm.querySelector('button');
      btn.disabled = true;
      const data = Object.fromEntries(new FormData(noteForm));
      data.access_key = noteKey;
      data.subject = `Produkto note from ${data.name}`;
      data.from_name = 'Produkto website';
      try {
        const r = await fetch('https://api.web3forms.com/submit', { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(data) });
        const j = await r.json();
        if (!j.success) throw new Error(j.message);
        noteForm.reset();
        say('Thanks \u2014 your note is on its way. Kelian will reply by email.', true);
      } catch (err) {
        say('That didn\u2019t send. Please try again in a moment.');
      } finally { btn.disabled = false; }
    });
  }

  /* ---------- Calendly booking (inline, dark navy to match the section) ---------- */
  const calendly = window.PRODUKTO_BOOKING?.calendly?.trim();
  if (calendly && $('#booking-calendar') && /^https:\/\/calendly\.com\/[\w.-]+\/[\w.-]+$/.test(calendly)) {
    const u = new URL(calendly);
    Object.entries({ hide_gdpr_banner: '1', background_color: '050f22', text_color: 'ffffff', primary_color: 'ffffff' })
      .forEach(([k, v]) => u.searchParams.set(k, v));
    const box = document.createElement('div');
    box.className = 'calendly-inline-widget';
    box.dataset.url = u.href;
    $('#booking-calendar').append(box);
    const js = document.createElement('script');
    js.src = 'https://assets.calendly.com/assets/external/widget.js';
    js.async = true;
    document.head.append(js);
    $('#booking-pending').hidden = true;
    $('#demo-booking').classList.add('is-calendly');
  }

  /* ---------- Cal.com booking (month view, dark, Produkto navy) ---------- */
  const calLink = !calendly && window.PRODUKTO_BOOKING?.calLink?.trim().replace(/^https?:\/\/(app\.)?cal\.com\//, '');
  if (calLink && /^[\w.-]+\/[\w.-]+$/.test(calLink)) {
    /* Cal.com's official loader: queues calls until embed.js arrives. */
    (function (C, A, L) { const p = (a, ar) => a.q.push(ar); const d = C.document; C.Cal = C.Cal || function () { const cal = C.Cal; const ar = arguments; if (!cal.loaded) { cal.ns = {}; cal.q = cal.q || []; d.head.appendChild(d.createElement('script')).src = A; cal.loaded = true; } if (ar[0] === L) { const api = function () { p(api, arguments); }; const ns = ar[1]; api.q = api.q || []; if (typeof ns === 'string') { cal.ns[ns] = cal.ns[ns] || api; p(cal.ns[ns], ar); p(cal, ['initNamespace', ns]); } else p(cal, ar); return; } p(cal, ar); }; })(window, 'https://app.cal.com/embed/embed.js', 'init');
    Cal('init', 'demo', { origin: 'https://cal.com' });
    Cal.ns.demo('inline', { elementOrSelector: '#booking-calendar', calLink, config: { layout: 'month_view', theme: 'dark' } });
    Cal.ns.demo('ui', { theme: 'dark', layout: 'month_view', hideEventTypeDetails: false, styles: { body: { background: 'transparent' } },
      cssVarsPerTheme: { dark: { 'cal-brand': '#ffffff', 'cal-brand-emphasis': '#e6ebf2', 'cal-brand-text': '#0b1b35',
        'cal-bg': '#050f22', 'cal-bg-muted': '#0b1b35', 'cal-bg-emphasis': '#14284a', 'cal-bg-subtle': '#0b1b35',
        'cal-border': '#ffffff1a', 'cal-border-subtle': '#ffffff12', 'cal-text': '#ffffff', 'cal-text-emphasis': '#ffffff', 'cal-text-subtle': '#b8c3d6', 'cal-text-muted': '#8fa0bb' } } });
    const external = $('#booking-external');
    external.href = 'https://cal.com/' + calLink;
    external.hidden = false;
    $('#booking-pending').hidden = true;
    $('#demo-booking').classList.add('is-cal');
  }

  /* ---------- Google Calendar appointment booking (older option) ---------- */
  const bookingUrl = !calLink && window.PRODUKTO_BOOKING?.url?.trim();
  if (bookingUrl) {
    try {
      const url = new URL(bookingUrl);
      if (url.protocol !== 'https:' || url.hostname !== 'calendar.google.com' ||
          !/^\/calendar\/(?:u\/\d+\/)?appointments\/schedules\/[^/]+/.test(url.pathname)) {
        throw new Error('Use the Google Calendar appointment schedule URL from Website embed.');
      }
      const external = $('#booking-external');
      external.href = url.href;
      external.hidden = false;
      url.searchParams.set('gv', 'true');
      const frame = document.createElement('iframe');
      frame.src = url.href;
      frame.title = 'Book a Produkto demo with Kelian';
      frame.loading = 'lazy';
      frame.referrerPolicy = 'strict-origin-when-cross-origin';
      $('#booking-calendar').append(frame);
      $('#booking-pending').hidden = true;
    } catch (error) {
      console.error('Booking configuration:', error.message);
    }
  }

  // Use the untransformed section as the scroll reference to avoid tilt feedback.
  const tiltSection = $('#answer');
  const tiltPanel = $('#answer .chat');
  let tiltFrame = 0;
  const updatePanelTilt = () => {
    tiltFrame = 0;
    if (!tiltSection || !tiltPanel) return;
    const top = tiltSection.getBoundingClientRect().top;
    const progress = Math.max(0, Math.min(1, (window.innerHeight * .85 - top) / (window.innerHeight * .8)));
    const remaining = reduceMotion.matches ? 0 : 1 - progress;
    const strength = window.innerWidth <= 700 ? .45 : 1;
    tiltPanel.style.setProperty('--chat-rx', `${remaining * 8 * strength}deg`);
    tiltPanel.style.setProperty('--chat-ry', `${remaining * -10 * strength}deg`);
    tiltPanel.style.setProperty('--chat-rz', `${remaining * -2 * strength}deg`);
  };
  const queuePanelTilt = () => { if (!tiltFrame) tiltFrame = requestAnimationFrame(updatePanelTilt); };
  window.addEventListener('scroll', queuePanelTilt, { passive: true });
  window.addEventListener('resize', queuePanelTilt);
  reduceMotion.addEventListener('change', queuePanelTilt);
  updatePanelTilt();
  const faqCard = $('#faq .faq-list');
  let faqFrame = 0;
  const updateFaqMotion = () => {
    faqFrame = 0;
    if (!faqCard) return;
    const top = faqCard.offsetTop + faqCard.offsetParent.getBoundingClientRect().top;
    const travel = innerHeight + faqCard.offsetHeight;
    const progress = Math.max(0, Math.min(1, (innerHeight - top) / travel));
    const direction = reduceMotion.matches ? 0 : 1 - progress * 2;
    faqCard.style.setProperty('--faq-lift', `${direction * 42}px`);
    faqCard.style.setProperty('--faq-tilt', `${direction * 12}deg`);
  };
  const queueFaqMotion = () => { if (!faqFrame) faqFrame = requestAnimationFrame(updateFaqMotion); };
  window.addEventListener('scroll', queueFaqMotion, { passive:true });
  window.addEventListener('resize', queueFaqMotion);
  reduceMotion.addEventListener('change', queueFaqMotion);
  updateFaqMotion();
})();
