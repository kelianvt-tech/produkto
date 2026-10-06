"""The "Improve visibility" button and the waitlist behind it.

The product page agent is not built. What IS built is the place a merchant
would reach for it: a button on every buyer question, a pop-up that shows
where they stand on that question, and a waitlist.

Each sign-up records WHICH question the merchant was looking at and how
visible they were on it. That is the point. Whether merchants want fixes, and
for which questions, is one of the two unproven risks in the brief, and a
waitlist click from a real merchant is evidence on it. A bare email count
would throw that away.

Copy rule: the pop-up says what the agent will DO, never the result it will
get. Nobody has shown that fixing product pages moves AI visibility yet, so
"designed to rank well" style promises stay out.
"""

import json
import re
import time
from html import escape as E

import db

SCHEMA = """CREATE TABLE IF NOT EXISTS waitlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    store_domain TEXT,
    prompt TEXT,
    visibility REAL,
    top_competitor TEXT,
    source TEXT NOT NULL DEFAULT 'improve-visibility',
    created_at REAL NOT NULL
)"""

# Deliberately loose: something@something.tld. A stricter pattern rejects real
# addresses, and a typo here costs one lost contact, not a broken page.
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def init():
    db.write(SCHEMA)


def save(email, store_domain, prompt, visibility, top_competitor,
         source='improve-visibility'):
    """Record a waitlist sign-up.

    `source` keeps the two doors apart. A merchant who clicked "Improve
    visibility" on one buyer question is telling us which question they want
    fixed; a merchant who joined from the Content agents page is telling us
    they want the agents at all. Pooling them would throw away the difference,
    and which questions merchants reach for is the signal worth having.
    """
    email = (email or '').strip().lower()
    if not EMAIL.match(email) or len(email) > 254:
        raise ValueError('Enter a valid email address.')
    init()
    # One row per email per question per door. Joining twice from the same
    # question is one signal, not two; a different question is a new one.
    if db.one('SELECT 1 AS x FROM waitlist WHERE email=? AND store_domain IS ?'
              ' AND prompt IS ? AND source=?',
              (email, store_domain, prompt, source)):
        return False
    db.write('INSERT INTO waitlist(email,store_domain,prompt,visibility,'
             'top_competitor,source,created_at) VALUES(?,?,?,?,?,?,?)',
             (email, store_domain or None, (prompt or '')[:1000] or None,
              visibility, (top_competitor or '')[:200] or None, source, time.time()))
    return True


def api(q, form):
    """POST /api/waitlist"""
    try:
        vis = form.get('visibility')
        vis = float(vis) if vis not in (None, '') else None
    except ValueError:
        vis = None
    try:
        new = save(form.get('email'), form.get('store'), form.get('prompt'), vis,
                   form.get('competitor'), form.get('source') or 'improve-visibility')
    except ValueError as e:
        return 200, ('json', json.dumps({'error': str(e)}))
    return 200, ('json', json.dumps({'ok': True, 'new': new}))


def row_data(prompt, rate, runs, mentions, by_answer, p, index, insight_panels, evidence):
    """What the pop-up shows for one question, built from saved answers only."""
    answers_with = {}
    for m in mentions:
        if by_answer.get(m['answer_id']) != prompt:
            continue
        if evidence.own(m, p):
            continue
        if not ((m['brand'] or '').strip() or (m['url'] or '').strip()):
            continue                     # generic advice is not a competitor
        label = insight_panels.display_brand(m['brand']) if (m['brand'] or '').strip() else ''
        if not label:
            continue
        g = answers_with.setdefault(label, dict(ids=set(), url=m['url'] or ''))
        g['ids'].add(m['answer_id'])
        g['url'] = g['url'] or (m['url'] or '')
    top = None
    if answers_with and runs:
        label, g = max(answers_with.items(), key=lambda kv: (len(kv[1]['ids']), kv[0]))
        top = dict(name=label, share=round(100 * len(g['ids']) / runs),
                   site=insight_panels.brand_site(dict(brand=label, url=g['url'])) or '')
    ps = p['_ps']
    ids = ps['relevance'][index] if index < len(ps.get('relevance') or []) else []
    by_id = {c['id']: c for c in p['_catalog']}
    products = [dict(title=by_id[i]['title'], image=by_id[i]['image'] or '')
                for i in ids if i in by_id][:3]
    return dict(prompt=prompt, rate=None if rate is None else round(rate),
                runs=runs, top=top, products=products, store=p['store_domain'])


def button(data):
    return ('<button type="button" class="wl-open" data-wl="%s" aria-haspopup="dialog">'
            '%s<span>Improve visibility</span></button>') % (E(json.dumps(data)), SPARK)


SPARK = ('<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M8 2.5l1.3 3.7L13 7.5 9.3 8.8 8 12.5 6.7 8.8 3 7.5l3.7-1.3z"/>'
         '<path d="M14.5 11l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/><path d="M3.5 17.5l4-4"/></svg>')

DIALOG = r'''<dialog class="wl-dialog" id="wl-dialog" aria-labelledby="wl-title">
<form method="dialog" class="wl-card" id="wl-form" novalidate>
 <header class="wl-head">
  <div><h2 id="wl-title">Improve visibility</h2><p class="wl-q" id="wl-q"></p></div>
  <button type="button" class="wl-x" id="wl-close" aria-label="Close"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg></button>
 </header>
 <section class="wl-stand" aria-label="Where you stand on this question">
  <div class="wl-stat"><span class="wl-label">Your visibility</span><b id="wl-rate"></b><small id="wl-runs"></small></div>
  <div class="wl-stat" id="wl-top-wrap"><span class="wl-label">Most recommended</span><b class="wl-brand" id="wl-top"></b><small id="wl-top-share"></small></div>
  <div class="wl-stat" id="wl-prod-wrap"><span class="wl-label">Your products for this question</span><div class="wl-prods" id="wl-prods"></div></div>
 </section>
 <section class="wl-agent">
  <div class="wl-agent-id">
   <span class="wl-avatar" id="wl-avatar" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3.2v2.6"/><circle cx="12" cy="2.6" r=".9"/><rect x="4.2" y="5.8" width="15.6" height="12.4" rx="3.6"/><g class="wl-look"><g class="wl-eyes"><circle cx="9" cy="11.4" r="1.3"/><circle cx="15" cy="11.4" r="1.3"/></g></g><path d="M9.6 15.2h4.8"/><path d="M2.4 10.6v3.2M21.6 10.6v3.2"/></svg></span>
   <div><span class="wl-badge"><i></i>In development</span>
   <h3>Product page agent</h3></div>
  </div>
  <p>Finds the details buyers ask about that are missing from your product pages, and drafts the fixes for you to review.</p>
  <ul>
   <li>Finds the product details AI answers look for</li>
   <li>Drafts updates for your product pages</li>
   <li>You review everything before it goes live</li>
  </ul>
  <div class="wl-join" id="wl-join">
   <label for="wl-email" class="wl-label">Get early access</label>
   <div class="wl-row">
    <input type="email" id="wl-email" name="email" placeholder="you@yourbrand.com" autocomplete="email" required>
    <button type="submit" class="wl-submit" id="wl-submit">Join the waitlist</button>
   </div>
   <p class="wl-err" id="wl-err" role="alert" hidden></p>
  </div>
  <div class="wl-done" id="wl-done" hidden role="status">
   <b><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7"/></svg>You&rsquo;re on the list</b>
   <span>We&rsquo;ll email <span id="wl-done-email"></span> when the agent is ready.</span>
  </div>
 </section>
</form>
</dialog>'''

CSS = r'''<style>
/* Its own column at the right of the table, like PromptWatch: empty until the
   row is hovered, so the button never sits on top of another column. */
.qtable{min-width:1000px}
.qtable col.c-act{width:186px}
.qtable td.act{vertical-align:middle;text-align:right;padding-left:0}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.wl-open{display:inline-flex;align-items:center;gap:7px;height:34px;padding:0 14px;border:1px solid var(--ink);border-radius:8px;background:var(--ink);color:#fff;font:500 13px/1 var(--font,Geist,system-ui,sans-serif);cursor:pointer;opacity:0;pointer-events:none;transition:opacity .15s,background .15s;white-space:nowrap}
.wl-open svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linejoin:round;stroke-linecap:round}
.qtable tbody tr:hover .wl-open,.qtable tbody tr:focus-within .wl-open,.wl-open:focus-visible{opacity:1;pointer-events:auto}
.wl-open:hover{background:#1c2c48}
.wl-open:focus-visible{outline:2px solid #7ea0e0;outline-offset:2px}
@media (hover:none){.wl-open{opacity:1;pointer-events:auto;height:32px;padding:0 10px}.wl-open span{font-size:12px}}
.wl-dialog{padding:0;border:0;border-radius:16px;width:min(620px,calc(100vw - 32px));max-height:calc(100vh - 32px);background:transparent;color:var(--text,#263650);box-shadow:0 24px 70px rgba(11,27,53,.28)}
.wl-dialog::backdrop{background:rgba(11,27,53,.36);backdrop-filter:blur(3px)}
.wl-dialog[open]{animation:wl-in .18s ease-out}
@keyframes wl-in{from{opacity:0;transform:translateY(8px) scale(.985)}to{opacity:1;transform:none}}
.wl-card{background:#fff;border-radius:16px;overflow:hidden;margin:0}
.wl-head{display:flex;gap:16px;justify-content:space-between;align-items:flex-start;padding:22px 24px 18px;background:var(--tint,#f3f7fd);border-bottom:1px solid var(--tint-line,#e6ecf8)}
.wl-head h2{margin:0;font-size:18px;font-weight:600;color:var(--ink)}
.wl-q{margin:6px 0 0;font-size:14px;line-height:1.5;color:var(--muted)}
.wl-x{flex:none;width:32px;height:32px;display:grid;place-items:center;border:1px solid var(--line,#e2e8f3);border-radius:8px;background:#fff;cursor:pointer;color:var(--muted)}
.wl-x svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round}
.wl-x:hover{color:var(--ink)}
.wl-stand{display:grid;grid-template-columns:1fr 1fr 1.25fr;border-bottom:1px solid var(--line,#e2e8f3)}
.wl-stat{padding:16px 20px;min-width:0;display:flex;flex-direction:column;gap:4px}
.wl-stat+.wl-stat{border-left:1px solid var(--line,#e2e8f3)}
.wl-label{font:500 11px/1.4 var(--font,Geist,sans-serif);letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.wl-stat>b{font-size:22px;font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums;line-height:1.3}
.wl-stat small{font-size:12px;color:var(--muted)}
.wl-brand{display:flex;align-items:center;gap:8px;font-size:15px!important;overflow:hidden}
.wl-brand img,.wl-brand .wl-ini{width:22px;height:22px;border-radius:6px;flex:none;object-fit:contain;background:#fff;border:1px solid var(--line,#e2e8f3)}
.wl-ini{display:grid;place-items:center;font-size:11px;font-weight:600;color:var(--muted)}
.wl-brand span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wl-prods{display:flex;flex-direction:column;gap:6px;margin-top:2px}
.wl-prod{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--ink);min-width:0}
.wl-prod img,.wl-prod i{width:26px;height:26px;border-radius:6px;object-fit:cover;flex:none;background:var(--subtle,#f0f4ff);border:1px solid var(--line,#e2e8f3)}
.wl-prod span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wl-agent{padding:22px 24px 24px}
.wl-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;background:var(--signal-bg,#fef3c7);color:var(--signal,#b45309);font-size:12px;font-weight:500}
.wl-badge i{width:6px;height:6px;border-radius:50%;background:currentColor}
.wl-agent-id{display:flex;align-items:center;gap:14px;margin-bottom:14px}.wl-agent-id h3{margin:8px 0 0}
.wl-avatar{flex-shrink:0;width:52px;height:52px;border-radius:14px;background:linear-gradient(145deg,#1a3160,#0b1b35);display:grid;place-items:center;box-shadow:0 4px 14px #0b1b3530,inset 0 1px 0 #ffffff1f}
.wl-avatar svg{width:30px;height:30px;fill:none;stroke:#fff;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
.wl-avatar .wl-eyes circle{fill:#fff;stroke:none}.wl-avatar .wl-eyes{transform-origin:12px 11.4px;animation:wl-blink 4.5s infinite}
.wl-look{transition:transform .12s ease-out}
@keyframes wl-blink{0%,92%,100%{transform:scaleY(1)}95%{transform:scaleY(.1)}}
@media(prefers-reduced-motion:reduce){.wl-avatar .wl-eyes{animation:none}}
.wl-agent h3{margin:12px 0 6px;font-size:17px;font-weight:600;color:var(--ink)}
.wl-agent>p{margin:0;font-size:14px;line-height:1.6;color:var(--text,#263650)}
.wl-agent ul{list-style:none;margin:14px 0 20px;padding:0;display:grid;gap:9px}
.wl-agent li{position:relative;padding-left:28px;font-size:14px;color:var(--text,#263650)}
.wl-agent li:before{content:"";position:absolute;left:0;top:1px;width:18px;height:18px;border-radius:50%;background:var(--up-bg,#d1fae5) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M4.5 8.5l2.5 2.5 4.5-5.5' fill='none' stroke='%23047857' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") center/13px no-repeat}
.wl-join{padding-top:18px;border-top:1px solid var(--line,#e2e8f3)}
.wl-row{display:flex;gap:8px;margin-top:8px}
.wl-row input{flex:1;min-width:0;height:42px;padding:0 13px;border:1px solid var(--line-2,#d2ddf0);border-radius:9px;font:15px var(--font,Geist,sans-serif);color:var(--ink);background:#fff}
.wl-row input:focus{outline:none;border-color:var(--ink);box-shadow:0 0 0 3px rgba(11,27,53,.1)}
.wl-row input[aria-invalid=true]{border-color:var(--down,#be123c)}
.wl-submit{flex:none;height:42px;padding:0 18px;border:0;border-radius:9px;background:var(--ink);color:#fff;font:500 14px var(--font,Geist,sans-serif);cursor:pointer}
.wl-submit:hover{background:#1c2c48}
.wl-submit:disabled{opacity:.6;cursor:progress}
.wl-err{margin:8px 0 0;font-size:13px;color:var(--down,#be123c)}
.wl-done{display:flex;flex-direction:column;gap:4px;padding:16px 18px;margin-top:18px;border-radius:10px;background:var(--up-bg,#d1fae5);color:var(--up,#047857)}
.wl-done b{display:flex;align-items:center;gap:8px;font-size:15px}
.wl-done b svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.wl-done span{font-size:13px;color:#065f46}
@media(max-width:600px){.wl-stand{grid-template-columns:1fr 1fr}.wl-stat:last-child{grid-column:1/-1;border-left:0;border-top:1px solid var(--line,#e2e8f3)}.wl-row{flex-direction:column}.wl-row input,.wl-submit{flex:none;width:100%;height:44px}.wl-head,.wl-agent{padding-left:18px;padding-right:18px}}
</style>'''

SCRIPT = r'''<script>
(()=>{
const dlg=document.getElementById('wl-dialog');if(!dlg)return;
const $=id=>document.getElementById(id),KEY='produkto-waitlist-email';
let cur=null,opener=null;
const get=()=>{try{return localStorage.getItem(KEY)||''}catch(e){return ''}};
const put=v=>{try{localStorage.setItem(KEY,v)}catch(e){}};
function text(el,v){el.textContent=v;}
function initials(s){return (s.split(/\s+/).slice(0,2).map(w=>w[0]).join('')||'?').toUpperCase();}
function fill(d){
 cur=d;text($('wl-q'),'“'+d.prompt+'”');
 text($('wl-rate'),d.rate==null?'—':d.rate+'%');
 text($('wl-runs'),d.runs?'of '+d.runs+' answer'+(d.runs===1?'':'s'):'No answers yet');
 const top=$('wl-top');top.replaceChildren();
 if(d.top){
  const ini=document.createElement('span');ini.className='wl-ini';ini.textContent=initials(d.top.name);
  if(d.top.site){const img=new Image();img.alt='';img.src='/icon?d='+encodeURIComponent(d.top.site);img.onerror=()=>img.replaceWith(ini);top.append(img);}else top.append(ini);
  const n=document.createElement('span');n.textContent=d.top.name;top.append(n);
  text($('wl-top-share'),'in '+d.top.share+'% of answers');
 }else{text(top,'—');text($('wl-top-share'),'No competitor named');}
 const pr=$('wl-prods');pr.replaceChildren();
 $('wl-prod-wrap').hidden=!d.products.length;
 d.products.forEach(p=>{const row=document.createElement('div');row.className='wl-prod';
  if(p.image){const img=new Image();img.alt='';img.loading='lazy';img.src=p.image;img.onerror=()=>img.replaceWith(document.createElement('i'));row.append(img);}else row.append(document.createElement('i'));
  const t=document.createElement('span');t.textContent=p.title;row.append(t);pr.append(row);});
 const joined=get();
 // Already on the list: still record that this merchant reached for help on
 // THIS question. Which questions they want fixed is the signal worth having;
 // the server keeps one row per email per question, so reopening is harmless.
 if(joined)fetch('/api/waitlist',{method:'POST',body:new URLSearchParams({email:joined,store:d.store,prompt:d.prompt,visibility:d.rate??'',competitor:d.top?d.top.name:''})}).catch(()=>{});
 $('wl-join').hidden=!!joined;$('wl-done').hidden=!joined;text($('wl-done-email'),joined);
 $('wl-err').hidden=true;$('wl-email').removeAttribute('aria-invalid');$('wl-email').value=joined;
}
document.addEventListener('click',e=>{const b=e.target.closest('.wl-open');if(!b)return;
 e.preventDefault();e.stopPropagation();opener=b;fill(JSON.parse(b.dataset.wl));dlg.showModal();
 if(!get())setTimeout(()=>$('wl-email').focus(),30);});
$('wl-close').addEventListener('click',()=>dlg.close());
(()=>{const bot=$('wl-avatar');if(!bot)return;const look=bot.querySelector('.wl-look');
// Eyes follow the pointer while it is over the robot; they settle back when it leaves.
bot.addEventListener('pointermove',e=>{const r=bot.getBoundingClientRect(),dx=(e.clientX-r.left)/r.width-.5,dy=(e.clientY-r.top)/r.height-.5;look.style.transform='translate('+(dx*3.2).toFixed(2)+'px,'+(dy*2.6).toFixed(2)+'px)';});
bot.addEventListener('pointerleave',()=>{look.style.transform='';});})();
dlg.addEventListener('click',e=>{if(e.target===dlg)dlg.close();});
dlg.addEventListener('close',()=>{opener&&opener.focus();});
$('wl-form').addEventListener('submit',async e=>{
 e.preventDefault();const email=$('wl-email').value.trim(),err=$('wl-err'),btn=$('wl-submit');
 if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)){err.textContent='Enter a valid email address.';err.hidden=false;$('wl-email').setAttribute('aria-invalid','true');$('wl-email').focus();return;}
 btn.disabled=true;btn.textContent='Joining…';err.hidden=true;
 try{
  const body=new URLSearchParams({email,store:cur.store,prompt:cur.prompt,visibility:cur.rate??'',competitor:cur.top?cur.top.name:''});
  const r=await fetch('/api/waitlist',{method:'POST',body});const j=await r.json();
  if(j.error)throw Error(j.error);
  put(email);$('wl-join').hidden=true;$('wl-done').hidden=false;text($('wl-done-email'),email);
 }catch(x){err.textContent=x.message||'Could not join. Try again.';err.hidden=false;}
 finally{btn.disabled=false;btn.textContent='Join the waitlist';}
});
})();
</script>'''


def assets():
    return CSS + DIALOG + SCRIPT
