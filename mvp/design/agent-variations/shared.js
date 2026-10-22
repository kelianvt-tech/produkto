/* Shared shell for the five agent variations: rail, theme, router, helpers.
   Each variation sets window.V = {name, render(route) -> html, after?(route)} before this runs. */
(function () {
  var A = window.AGENT;
  try { if (localStorage.getItem('pk-theme') === 'dark') document.documentElement.classList.add('dark'); } catch (e) {}

  var H = window.H = {
    esc: function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); },
    TYPES: {product_fix: 'Product page fix', faq: 'FAQ', comparison: 'Comparison page', guide: 'Buying guide'},
    STEPS: [['voice', 'Your voice'], ['brand', 'Your brand'], ['scope', 'What it may change'], ['schedule', 'Time zone and pace'], ['facts', 'Missing facts'], ['shopify', 'Shopify']],
    drafts: A.drafts,
    draft: function (id) { return A.drafts.filter(function (d) { return d.id === +id; })[0]; },
    byStatus: function (s) { return A.drafts.filter(function (d) { return s.indexOf(d.status) >= 0; }); },
    needsFacts: function (d) { return d.status === 'draft' && d.gaps > 0; },
    date: function (iso, opt) { if (!iso) return 'Not planned'; var d = new Date(iso + 'T12:00:00'); return d.toLocaleDateString('en-US', opt || {weekday: 'short', month: 'short', day: 'numeric'}); },
    today: '2026-10-16',
    img: function (d, cls) { return d && d.image ? '<img class="' + (cls || 'thumb') + '" src="' + H.esc(d.image) + '" alt="" loading="lazy">' : '<span class="' + (cls || 'thumb') + '"></span>'; },
    typeTag: function (d) { return '<span class="tag t-' + d.type + '"><i class="type-dot"></i>' + H.TYPES[d.type] + '</span>'; },
    status: function (d) {
      if (d.status === 'published') return '<span class="tag ok">Live</span>';
      if (d.status === 'approved' || d.status === 'scheduled') return '<span class="tag info">Scheduled</span>';
      if (d.status === 'rejected') return '<span class="tag">Rejected</span>';
      return H.needsFacts(d) ? '<span class="tag warn">' + d.gaps + ' fact' + (d.gaps > 1 ? 's' : '') + ' needed</span>' : '<span class="tag">Ready to review</span>';
    },
    link: function (r) { return '#' + r; },
    icon: function (n) {
      var p = {
        check: '<path d="M4.5 10.5l3.5 3.5 7.5-8"/>', x: '<path d="M5 5l10 10M15 5L5 15"/>', arrow: '<path d="M4 10h12M11 5l5 5-5 5"/>',
        back: '<path d="M16 10H4M9 5l-5 5 5 5"/>', cal: '<rect x="3" y="4.5" width="14" height="12" rx="2"/><path d="M3 8.5h14M7 2.8v3.4M13 2.8v3.4"/>',
        doc: '<path d="M6 2.8h6l3.5 3.5V17H6z"/><path d="M12 2.8v3.5h3.5M8.5 10h5M8.5 13h5"/>', live: '<circle cx="10" cy="10" r="2.4"/><path d="M5.5 5.5a6.4 6.4 0 000 9M14.5 5.5a6.4 6.4 0 010 9"/>',
        gear: '<circle cx="10" cy="10" r="2.6"/><path d="M10 2.5v2.2M10 15.3v2.2M2.5 10h2.2M15.3 10h2.2M4.7 4.7l1.6 1.6M13.7 13.7l1.6 1.6M4.7 15.3l1.6-1.6M13.7 6.3l1.6-1.6"/>',
        spark: '<path d="M10 3l1.6 4.4L16 9l-4.4 1.6L10 15l-1.6-4.4L4 9l4.4-1.6z"/>', link: '<path d="M8.5 11.5l3-3M7 9.5L5.5 11a2.5 2.5 0 003.5 3.5l1.5-1.5M13 10.5l1.5-1.5A2.5 2.5 0 0011 5.5L9.5 7"/>',
        undo: '<path d="M7 6L3.5 9.5 7 13"/><path d="M3.5 9.5h8a4.5 4.5 0 010 9H9"/>', bolt: '<path d="M11 2.5L4.5 11H10l-1 6.5L15.5 9H10z"/>', grid: '<rect x="3" y="3" width="6" height="6" rx="1.5"/><rect x="11" y="3" width="6" height="6" rx="1.5"/><rect x="3" y="11" width="6" height="6" rx="1.5"/><rect x="11" y="11" width="6" height="6" rx="1.5"/>',
        chev: '<path d="M8 5l5 5-5 5"/>', drag: '<circle cx="8" cy="6" r=".9"/><circle cx="12" cy="6" r=".9"/><circle cx="8" cy="10" r=".9"/><circle cx="12" cy="10" r=".9"/><circle cx="8" cy="14" r=".9"/><circle cx="12" cy="14" r=".9"/>'
      }[n] || '';
      return '<svg viewBox="0 0 20 20" aria-hidden="true">' + p + '</svg>';
    },
    title: function () {
      return '<h1 class="agent-title"><svg viewBox="0 0 20 20" aria-hidden="true"><defs><linearGradient id="ag" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7c3aed"/><stop offset="1" stop-color="#2f80ff"/></linearGradient></defs><path d="M8 2.5l1.5 4.2 4.2 1.5-4.2 1.5L8 13.9 6.5 9.7 2.3 8.2l4.2-1.5z" fill="url(#ag)"/><path d="M15 11.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" fill="url(#ag)"/></svg><span>Catalog Optimization Agent</span></h1>';
    },
    // October 2026 month grid, weeks starting Sunday: [[Date,...7],...]
    month: function (y, m) {
      var first = new Date(y, m, 1), start = new Date(y, m, 1 - first.getDay()), weeks = [];
      for (var w = 0; w < 6; w++) { var row = []; for (var i = 0; i < 7; i++) { row.push(new Date(start.getFullYear(), start.getMonth(), start.getDate() + w * 7 + i)); } weeks.push(row); if (row[6].getMonth() !== m && w > 3) break; }
      return weeks;
    },
    iso: function (dt) { return dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0') + '-' + String(dt.getDate()).padStart(2, '0'); },
    onDay: function (iso) { return A.drafts.filter(function (d) { return d.planned === iso && d.status !== 'rejected'; }); },
    paras: function (html) { return html; },
    missingTotal: A.missing.reduce(function (n, m) { return n + m.items.length; }, 0)
  };


  /* Setup step content, the same facts in every variation; each variation lays it out its own way. */
  H.setupBody = function (step) {
    var e = H.esc, v = A.voice, b = A.brief || {};
    var foot = function (label) { return '<div class="s-foot"><button class="btn primary">' + (label || 'Save and continue') + '</button></div>'; };
    return {
      voice: '<dl class="s-traits">' + v.traits.map(function (t) { return '<div><dt>' + e(t.name) + '</dt><dd>' + e(t.how) + '</dd></div>'; }).join('') + '</dl>' +
        (v.examples && v.examples.length ? '<ul class="s-quotes">' + v.examples.map(function (x) { return '<li>“' + e(x) + '”</li>'; }).join('') + '</ul>' : '') +
        '<figure class="s-sample"><figcaption>A sample in your voice: ' + e(v.sample_product) + '</figcaption><blockquote>' + e(v.sample) + '</blockquote></figure>' +
        '<div class="s-field"><label for="adj">Not quite? Tell it what to change</label><div class="s-inline"><input class="input" id="adj" placeholder="e.g. shorter sentences, less poetic"><button class="btn">Try again</button></div></div>' + foot('Sounds like us'),
      brand: '<div class="s-fields">' + [['customers', 'Who buys from you?'], ['story', 'Your brand in one or two sentences'], ['different', 'What makes your products different?'], ['policies', 'Shipping, returns and guarantees'], ['objections', 'What customers ask or worry about most'], ['never_words', 'Words you never want used']].map(function (f) {
        var val = b[f[0]]; val = Array.isArray(val) ? val.join('\n') : val;
        return '<div class="s-field"><label for="b-' + f[0] + '">' + f[1] + '</label><textarea class="input" id="b-' + f[0] + '">' + e(val) + '</textarea></div>';
      }).join('') + '</div>' + foot(),
      scope: '<div class="s-checks">' + [['titles', 'Product titles'], ['descriptions', 'Product descriptions'], ['specs', 'Spec tables'], ['faqs', 'FAQs on product pages'], ['comparisons', 'Comparison pages'], ['guides', 'Buying guides on your blog']].map(function (c) {
        return '<label class="s-check"><input type="checkbox"' + (A.allowed.indexOf(c[0]) >= 0 ? ' checked' : '') + '><span>' + c[1] + '</span></label>';
      }).join('') + '</div><div class="s-field"><label for="leave">Products to leave alone</label><select class="input" id="leave"><option>None</option>' + A.products.map(function (p) { return '<option>' + e(p.title) + '</option>'; }).join('') + '</select></div>' + foot(),
      schedule: '<div class="s-fields"><div class="s-field"><label for="tz">Time zone</label><select class="input" id="tz"><option>Europe/London (' + A.store.tz + ')</option><option>America/New_York (ET)</option><option>America/Los_Angeles (PT)</option></select></div>' +
        '<div class="s-field"><label>Days the agent publishes</label><div class="s-days">' + ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(function (x, i) { return '<label><input type="checkbox"' + (A.schedule.days.indexOf(i) >= 0 ? ' checked' : '') + '><span>' + x + '</span></label>'; }).join('') + '</div></div>' +
        '<div class="s-row2"><div class="s-field"><label for="pace">Pages a week</label><select class="input" id="pace"><option>' + A.schedule.pace + ' a week</option><option>5 a week</option></select></div><div class="s-field"><label for="hour">Publish time</label><select class="input" id="hour"><option>09:00</option><option>12:00</option></select></div></div></div>' + foot(),
      facts: A.missing.slice(0, 3).map(function (p) {
        return '<div class="s-prod"><img src="' + e(p.image) + '" alt=""><div><h3>' + e(p.title) + '</h3><div class="s-qa">' + p.items.slice(0, 4).map(function (it, i) {
          var web = p.handle === 'helsinki-face-moisturiser' && i === 0;
          return '<div class="s-field"><label for="m' + p.handle + i + '">' + e(it.question) + '</label><input class="input" id="m' + p.handle + i + '" value="' + e(it.suggestion || '') + '" placeholder="Leave empty if you don\'t know">' +
            (web ? '<p class="s-web">goodhoodstore.com says <b>75ml</b>. <a href="#">See the page</a> · <button class="s-link">Use this</button></p>' : '') + '</div>';
        }).join('') + '</div></div></div>';
      }).join('') + foot('Save and plan my first two weeks'),
      shopify: '<div class="s-shop"><svg viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="10" fill="#95BF47"/><path d="M25 12.5c-.1-.6-.6-.9-1-.9l-2-.1-1.6-1.5c-.2-.1-.4-.1-.5-.1l-1 .3C18.4 9.1 17.7 8.5 16.7 8.5c-2.4 0-3.6 3-4 4.6l-1.7.5c-.5.2-.5.2-.6.7L8.5 28.5l13.4 2.5 7.3-1.6z" fill="#fff"/></svg><div><b>Not connected</b><p>Until you connect, approved pages download as a file to import into Shopify.</p></div><button class="btn primary">Connect Shopify</button></div>'
    }[step || 'voice'];
  };
  H.setupIntro = {
    voice: ['This is how you write', 'Read from ' + (A.voice.pages || []).join(', ') + '.'],
    brand: ['Your brand', 'Filled in from your pages. Correct anything that isn’t right.'],
    scope: ['What it may change', 'Nothing reaches your store until you approve it.'],
    schedule: ['Time zone and pace', 'The calendar and publish times use your store’s time zone.'],
    facts: ['Facts your pages leave out', 'Buyers check these before buying. Answer what you know; skip the rest.'],
    shopify: ['Shopify', 'Connect once and approved pages publish themselves on their date, with undo.']
  };

  var NAV = [['', 'Dashboard', '<path d="M3 10.5 12 3l9 7.5"/><path d="M5.5 9.5V21h13V9.5"/>'], ['', 'Buyer questions', '<path d="M4 5.5h16v10H9l-5 4z"/>'],
    ['', 'Opportunities', '<path d="M12 3.5 14.6 9l5.9.6-4.4 4 1.3 5.9L12 16.5l-5.4 3 1.3-5.9-4.4-4 5.9-.6z"/>'],
    ['agent', 'Catalog Optimization Agent', '<rect x="4.2" y="6.4" width="15.6" height="12" rx="3.4"/><path d="M12 3.4v3"/><circle cx="9.2" cy="12" r="1.15"/><circle cx="14.8" cy="12" r="1.15"/>']];

  function rail() {
    var hat = A.products.filter(function (p) { return p.handle === 'full-clubhouse-routine'; })[0] || A.products[0];
    return '<aside class="rail" aria-label="Produkto"><div class="rail-store"><img src="' + H.esc(hat.image) + '" alt=""><div><b>' + H.esc(A.store.name) + '</b><span>' + A.store.domain + '</span></div></div><nav aria-label="Sections">' +
      NAV.map(function (n) { return '<a class="rail-item" href="' + (n[0] ? '#drafts' : '#') + '"' + (n[0] ? ' aria-current="page"' : '') + '><svg viewBox="0 0 24 24" aria-hidden="true">' + n[2] + '</svg><span>' + n[1] + '</span>' + (n[1] === 'Opportunities' ? '<span class="rail-badge">38</span>' : '') + '</a>'; }).join('') +
      '</nav><div class="rail-foot"><button class="theme-btn" id="theme" type="button"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M15.5 12.5A6 6 0 017.5 4.5a6 6 0 108 8z"/></svg><span>Light / dark</span></button></div></aside>';
  }

  var PAGES = [['drafts', 'Drafts'], ['draft/6', 'A draft'], ['calendar', 'Calendar'], ['calendar/7', 'Calendar + detail'], ['live', 'Live'], ['setup/voice', 'Setup']];

  function vbar(route) {
    var here = location.pathname.split('/').pop();
    return '<div class="vbar"><span>Variation</span>' + [1, 2, 3, 4, 5].map(function (n) {
      var f = 'v' + n + '.html'; return '<a href="' + f + location.hash + '"' + (f === here ? ' aria-current="page"' : '') + '>' + n + '</a>';
    }).join('') + '<strong style="margin-left:8px;color:var(--ink)">' + H.esc(window.V.name) + '</strong><div class="vbar-pages">' +
      PAGES.map(function (p) { var on = route.join('/') === p[0] || (p[0] === 'setup/voice' && route[0] === 'setup'); return '<a href="#' + p[0] + '"' + (on ? ' aria-current="page"' : '') + '>' + p[1] + '</a>'; }).join('') + '</div></div>';
  }

  function go() {
    var route = (location.hash.replace(/^#/, '') || 'drafts').split('/');
    document.body.innerHTML = rail() + vbar(route) + '<main id="main">' + window.V.render(route) + '</main>';
    document.getElementById('theme').onclick = function () {
      var on = document.documentElement.classList.toggle('dark');
      try { localStorage.setItem('pk-theme', on ? 'dark' : 'light'); } catch (e) {}
    };
    if (window.V.after) window.V.after(route);
    window.scrollTo(0, 0);
  }
  window.addEventListener('hashchange', go);
  document.addEventListener('DOMContentLoaded', go);
})();
