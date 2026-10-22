/* Interactive dashboard illustration on the homepage.
   Example brands with illustrative numbers, not measured results.
   Each KPI tab has its own chart, like the real dashboard and Promptwatch:
     Visibility      line per product over time
     Share of voice  stacked 100% bar per date (the rest of the market on top)
     Position        rank chart: each product's photo at its rank on each date
   Hover a product: the dashboard switches to it. Hover the chart: tooltip and
   crosshair follow the pointer and the nearest product lights up. */
(() => {
  const stage = document.querySelector('[data-mk]');
  if (!stage) return;

  const N = 40;                       // daily points
  const END = new Date(2026, 9, 12);  // 12 Oct 2026
  const W = 400, H = 256, TOP = 16;
  const BARS = 14, RANKS = 10;        // dates shown in the bar and rank charts

  // Seeded so the illustration is the same on every visit.
  let seed = 7;
  const rnd = () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  const series = (a, b, noise, wave = 0) => Array.from({ length: N }, (_, i) => {
    const t = i / (N - 1);
    return Math.max(1, a + (b - a) * t ** 1.3 + (rnd() * 2 - 1) * noise + wave * Math.sin(i / 3));
  });

  const P = [
    { id: 'pat', name: 'Torrentshell 3L Jacket', brand: 'Patagonia', img: 'chatgpt-jacket-torrentshell.webp', color: '#4c8dff', s: series(13, 33, 1.2), pos: [3.4, 1.6], rank: '▲ 3', dir: 'up' },
    { id: 'fire', name: 'Firewall Light Jacket', brand: 'Rab', img: 'chatgpt-jacket-firewall.webp', color: '#f2836b', s: series(26, 21, 1.5, 1), pos: [1.6, 1.9], rank: '▼ 1', dir: 'down' },
    { id: 'down', name: 'Downpour Eco Jacket', brand: 'Rab', img: 'chatgpt-jacket-downpour.webp', color: '#5bb8e8', s: series(22, 19, 1.5, 1), pos: [2.0, 2.3], rank: '▼ 1', dir: 'down' },
    { id: 'del', name: 'Deluge 2.0 Pant', brand: 'Berghaus', img: 'chatgpt-trousers-deluge.webp', color: '#3fae7a', s: series(12, 14, 1.2), pos: [2.6, 2.8], rank: '▼ 1', dir: 'down' },
    { id: 'pre', name: 'PreCip Eco Pant', brand: 'Marmot', img: 'chatgpt-trousers-precip.webp', color: '#a78bfa', s: series(6, 8.5, .8), pos: [3.5, 3.4], rank: '– 0', dir: 'flat' },
    { id: 'dpp', name: 'Downpour Eco Pant', brand: 'Rab', img: 'chatgpt-trousers-downpour.webp', color: '#e0a84e', s: series(5, 5.6, .6), pos: [4.0, 3.9], rank: '▲ 1', dir: 'up' },
  ];
  const HOME = 'pat';
  const byId = Object.fromEntries(P.map((p) => [p.id, p]));
  const sums = Array.from({ length: N }, (_, i) => P.reduce((a, p) => a + p.s[i], 0));
  P.forEach((p) => {
    const [a, b] = p.pos;
    p.m = {
      vis: p.s,
      sov: p.s.map((v, i) => v / sums[i] * 46),
      pos: Array.from({ length: N }, (_, i) => Math.min(5, Math.max(1, a + (b - a) * i / (N - 1) + (rnd() * 2 - 1) * .18))),
    };
  });
  const others = (i) => 100 - P.reduce((a, p) => a + p.m.sov[i], 0);
  // Rank on a date = order by visibility that day.
  const rankAt = (i) => Object.fromEntries(P.slice().sort((a, b) => b.s[i] - a.s[i]).map((p, n) => [p.id, n + 1]));

  const gy = (k, n) => TOP + k * (H - TOP) / (n - 1);   // k-th of n evenly spaced guides
  const METRICS = {
    vis: { label: 'visibility', axis: ['36%', '27%', '18%', '9%', '0%'], fmt: (v) => v.toFixed(1) + '%', better: 1, y: (v) => H - v / 36 * (H - TOP) },
    sov: { label: 'share of voice', axis: ['100%', '75%', '50%', '25%', '0%'], fmt: (v) => v.toFixed(1) + '%', better: 1, y: (v) => H - v / 100 * (H - TOP) },
    pos: { label: 'position', axis: ['#1', '#2', '#3', '#4', '#5', '#6'], fmt: (v) => '#' + v.toFixed(1), better: -1, y: (r) => gy(r - 1, 6) },
  };
  let metric = 'vis';
  const Mx = () => METRICS[metric];

  const sample = (k) => Array.from({ length: k }, (_, j) => Math.round(j * (N - 1) / (k - 1)));
  const barIdx = sample(BARS), rankIdx = sample(RANKS);
  const xLine = (i) => i * W / (N - 1);
  const xSlot = (j, k) => (j + .5) * W / k;
  const linePath = (vals, y) => 'M' + vals.map((v, i) => `${xLine(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' L');
  const date = (i) => { const d = new Date(END); d.setDate(d.getDate() - (N - 1 - i)); return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); };

  const $ = (sel) => stage.querySelector(sel);
  const svg = $('.mk-plot'), plot = $('.mk-chart');
  const NS = 'http://www.w3.org/2000/svg';
  const el = (tag, attrs = {}, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.append(e); return e; };
  const area = $('.mk-area'), cursor = $('.mk-cursor'), dot = $('.mk-dot'), tip = $('.mk-tip');
  const grid = $('.mk-grid');

  // Visibility: one line per product
  const lines = $('.mk-lines');
  P.slice().reverse().forEach((p, n) => {
    const l = el('path', { d: linePath(p.m.vis, METRICS.vis.y), pathLength: 1, class: 'mk-line', 'data-id': p.id }, lines);
    l.style.stroke = p.color;
    l.style.transitionDelay = `${.3 + n * .08}s, 0s, 0s`;
  });

  // Share of voice: stacked bars, products at the bottom, the rest of the market on top
  const bars = el('g', { class: 'mk-bars' });
  lines.after(bars);
  const bw = W / BARS * .58;
  barIdx.forEach((i, j) => {
    const col = el('g', { class: 'mk-col', 'data-j': j }, bars);
    col.style.setProperty('--d', `${j * .03}s`);
    let acc = 0;
    const x0 = (xSlot(j, BARS) - bw / 2).toFixed(1);
    for (const p of P) {
      const v = p.m.sov[i], y1 = METRICS.sov.y(acc + v), y0 = METRICS.sov.y(acc);
      el('rect', { x: x0, y: y1.toFixed(1), width: bw.toFixed(1), height: (y0 - y1).toFixed(1), fill: p.color, 'data-id': p.id }, col);
      acc += v;
    }
    el('rect', { x: x0, y: METRICS.sov.y(100), width: bw.toFixed(1), height: (METRICS.sov.y(acc) - METRICS.sov.y(100)).toFixed(1), class: 'mk-other', rx: 2 }, col);
  });

  // Position: each product's photo at its rank on each date, joined by a line
  const bump = el('g', { class: 'mk-bump' });
  bars.after(bump);
  const ranks = rankIdx.map(rankAt);
  const S = 19;
  P.slice().reverse().forEach((p) => {
    const pts = ranks.map((r, j) => [xSlot(j, RANKS), METRICS.pos.y(r[p.id])]);
    const g = el('g', { class: 'mk-brank', 'data-id': p.id }, bump);
    const l = el('path', { d: 'M' + pts.map(([a, b]) => `${a.toFixed(1)} ${b.toFixed(1)}`).join(' L'), class: 'mk-bline' }, g);
    l.style.stroke = p.color;
    pts.forEach(([a, b], j) => {
      const m = el('g', { class: 'mk-mark' }, g);
      m.style.setProperty('--d', `${j * .04}s`);
      const r = el('rect', { x: a - S / 2, y: b - S / 2, width: S, height: S, rx: 5, class: 'mk-mark-bg' }, m);
      r.style.stroke = p.color;
      el('image', { href: `assets/${p.img}`, x: a - S / 2 + 2, y: b - S / 2 + 2, width: S - 4, height: S - 4, preserveAspectRatio: 'xMidYMid meet' }, m);
    });
  });

  // Right-hand list
  const list = $('.mk-list');
  list.innerHTML = P.map((p) => `
    <div class="mk-row" data-id="${p.id}">
      <span class="mk-tile"><img src="assets/${p.img}" alt="" width="34" height="34" loading="lazy"></span>
      <span class="mk-name">${p.name}<small>${p.brand}</small></span>
      <span class="mk-pct"></span>
      <span class="mk-${p.dir === 'up' ? 'up' : p.dir === 'down' ? 'down' : 'flat'}">${p.rank}</span>
    </div>`).join('');

  let active = HOME;
  const setActive = (id) => {
    active = id;
    const p = byId[id];
    stage.style.setProperty('--mk-active', p.color);
    svg.querySelectorAll('[data-id]').forEach((e) => e.classList.toggle('is-active', e.dataset.id === id));
    stage.classList.toggle('is-focus', id !== HOME);
    area.setAttribute('d', `${linePath(p.m.vis, METRICS.vis.y)} L${W} ${H} L0 ${H}Z`);
    dot.setAttribute('cy', METRICS.vis.y(p.m.vis[N - 1]).toFixed(1));
    list.querySelectorAll('.mk-row').forEach((r) => r.classList.toggle('is-you', r.dataset.id === id));
    $('[data-k="title"]').textContent = id === HOME ? 'Catalog overview' : `${p.brand} · ${p.name}`;
    for (const k of Object.keys(METRICS)) {
      const v = p.m[k], last = v[N - 1], d = (last - v[N - 8]) * METRICS[k].better;  // vs 7 days earlier; lower position is better
      $(`[data-k="${k}"]`).textContent = METRICS[k].fmt(last);
      const e = $(`[data-k="${k}-d"]`);
      e.textContent = `${d > .05 ? '▲ +' : d < -.05 ? '▼ −' : '– '}${Math.abs(d).toFixed(1)}`;
      e.className = d > .05 ? 'mk-up' : d < -.05 ? 'mk-down' : 'mk-flat';
    }
  };

  // Which date the pointer is on, for the current chart.
  const slotFor = (fx) => {
    if (metric === 'vis') { const i = Math.round(fx * (N - 1)); return { i, x: xLine(i) }; }
    const k = metric === 'sov' ? BARS : RANKS, idx = metric === 'sov' ? barIdx : rankIdx;
    const j = Math.min(k - 1, Math.max(0, Math.floor(fx * k)));
    return { i: idx[j], j, x: xSlot(j, k) };
  };

  const showTip = (slot) => {
    const { i, j, x } = slot;
    cursor.setAttribute('x1', x); cursor.setAttribute('x2', x);
    bars.querySelectorAll('.mk-col').forEach((c) => c.classList.toggle('is-col', metric === 'sov' && +c.dataset.j === j));
    const name = (p) => `${p.brand} ${p.name.replace(/ Jacket$/, '')}`;
    let rows;
    if (metric === 'pos') {
      const r = rankAt(i);
      rows = P.map((p) => ({ p, v: r[p.id], t: '#' + r[p.id] })).sort((a, b) => a.v - b.v);
    } else {
      rows = P.map((p) => ({ p, v: p.m[metric][i], t: Mx().fmt(p.m[metric][i]) })).sort((a, b) => b.v - a.v);
    }
    tip.innerHTML = `<b>${date(i)}</b>` + rows.map(({ p, t }) =>
      `<span class="${p.id === active ? 'is-on' : ''}"><i style="color:${p.color}"></i>${name(p)}<em>${t}</em></span>`).join('')
      + (metric === 'sov' ? `<span class="mk-tip-other"><i></i>Other products<em>${others(i).toFixed(1)}%</em></span>` : '');
    const box = svg.getBoundingClientRect();
    const off = box.left - plot.getBoundingClientRect().left;  // SVG has no offsetLeft
    const left = x / W * box.width;
    tip.style.left = `${off + (left > box.width * .55 ? left - tip.offsetWidth - 16 : left + 16)}px`;
  };
  const restTip = () => showTip(slotFor(metric === 'vis' ? .3 : .33));

  // Chart hover
  plot.addEventListener('pointermove', (e) => {
    const box = svg.getBoundingClientRect();
    const fx = Math.min(1, Math.max(0, (e.clientX - box.left) / box.width));
    const py = (e.clientY - box.top) / box.height * H;
    const slot = slotFor(fx);
    let near = byId[active];
    if (metric === 'vis') {
      near = P.reduce((a, p) => Math.abs(METRICS.vis.y(p.m.vis[slot.i]) - py) < Math.abs(METRICS.vis.y(a.m.vis[slot.i]) - py) ? p : a);
    } else if (metric === 'sov') {
      let acc = 0;
      for (const p of P) { const v = p.m.sov[slot.i]; if (py <= METRICS.sov.y(acc) && py >= METRICS.sov.y(acc + v)) { near = p; break; } acc += v; }
    } else {
      const r = rankAt(slot.i);
      near = P.reduce((a, p) => Math.abs(METRICS.pos.y(r[p.id]) - py) < Math.abs(METRICS.pos.y(r[a.id]) - py) ? p : a);
    }
    stage.classList.add('is-hover');
    if (near.id !== active) setActive(near.id);
    showTip(slot);
  });
  plot.addEventListener('pointerleave', () => { stage.classList.remove('is-hover'); setActive(HOME); restTip(); });

  // Product hover: the dashboard switches to that product
  list.addEventListener('pointerover', (e) => { const r = e.target.closest('.mk-row'); if (r && r.dataset.id !== active) { setActive(r.dataset.id); showTip(slotFor(1)); } });
  list.addEventListener('pointerleave', () => { setActive(HOME); restTip(); });

  // KPI tabs switch the chart type
  const setMetric = (k) => {
    metric = k;
    const M = Mx();
    stage.dataset.metric = k;
    stage.querySelectorAll('[data-metric]').forEach((c) => c.classList.toggle('is-on', c.dataset.metric === k));
    const n = M.axis.length;
    grid.innerHTML = '';
    M.axis.forEach((_, i) => el('line', { x1: 0, x2: W, y1: gy(i, n), y2: gy(i, n) }, grid));
    $('.mk-yaxis').innerHTML = M.axis.map((t, i) => `<span style="top:${(gy(i, n) / H * 100).toFixed(2)}%">${t}</span>`).join('');
    $('[data-k="list-label"]').textContent = `Top products by ${M.label}`;
    list.querySelectorAll('.mk-row').forEach((r) => { r.querySelector('.mk-pct').textContent = M.fmt(byId[r.dataset.id].m[k][N - 1]); });
    // replay the entry animation for bars and ranks
    [bars, bump].forEach((g) => { g.classList.remove('is-enter'); void g.getBBox(); g.classList.add('is-enter'); });
    setActive(active);
    restTip();
  };
  stage.querySelectorAll('[data-metric]').forEach((c) => c.addEventListener('click', () => setMetric(c.dataset.metric)));

  setMetric('vis');
  requestAnimationFrame(restTip);
  window.addEventListener('resize', restTip);
})();
