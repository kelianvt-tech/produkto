"""Content agents: what is coming, and a way to put your name down for it.

Reached from the rail, so there is no buyer question behind it — which is why
this is a page rather than the per-question dialog. The dialog answers "fix
THIS question"; this answers "what is this whole thing going to do".

Two copy rules carried over from the waitlist dialog, and neither is optional:

  * Say what an agent will DO, never the result it will get. Nobody has shown
    that changing product pages moves AI visibility — that is one of the open
    questions the product exists to answer — so nothing here promises a rank.
  * Do not overstate how finished this is. It is in development, the list is
    not settled, and saying so is what makes the rest of the page credible.
"""

from html import escape as E

import accounts
import scheduler
import waitlist

SOURCE = 'content-agents'

# What the agents draft. Each line says the work, not the outcome.
DOES = [
    ("Product pages",
     "Fills in the details buyers ask about that your pages leave out."),
    ("Specs and FAQs",
     "Drafts the specification and question-and-answer content that catalogs "
     "most often have nothing to say on."),
    ("Comparison pages",
     "Writes the side-by-side pages buyers look for when they are choosing "
     "between two products."),
    ("Category copy",
     "Gives collection and category pages something to say beyond a list of "
     "products."),
    ("A publishing schedule",
     "Plans the work across a calendar instead of dropping it on you at once, "
     "so it goes out at a pace you can review."),
]

# Line icons for the cards, in the same order as DOES.
ICONS = [
    '<path d="M7 3.5h7l4 4v13H7z"/><path d="M14 3.5v4h4"/><path d="M10 12h5M10 15.5h5"/>',
    '<circle cx="12" cy="12" r="8.5"/><path d="M9.8 9.6a2.3 2.3 0 1 1 3 2.2c-.6.2-.8.6-.8 1.2v.5"/><circle cx="12" cy="16.4" r=".6"/>',
    '<rect x="3.5" y="5" width="7" height="14" rx="1.5"/><rect x="13.5" y="5" width="7" height="14" rx="1.5"/>',
    '<rect x="4" y="4" width="6.5" height="6.5" rx="1.3"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.3"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.3"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.3"/>',
    '<rect x="4" y="5.5" width="16" height="14.5" rx="2"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/>',
]


def page(_q=None):
    stores = accounts.visible(scheduler.scannable())
    store = stores[0] if len(stores) == 1 else ''
    items = ''.join(
        '<li><span class="agent-icon" aria-hidden="true"><svg viewBox="0 0 24 24">%s</svg></span>'
        '<em class="agent-tag">Planned</em><b>%s</b><span>%s</span></li>'
        % (ICONS[i], E(t), E(d)) for i, (t, d) in enumerate(DOES))
    body = """<div class="plain-page agents-page"><h1>Content agents</h1>
<p class="page-description">Produkto measures where your products stand in AI answers. The agents are the next half: they write the content that answers the questions your catalog currently doesn't.</p>

<div class="agent-card">
 <div class="agent-id">
  <span class="agent-avatar" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3.2v2.6"/><circle cx="12" cy="2.6" r=".9"/><rect x="4.2" y="5.8" width="15.6" height="12.4" rx="3.6"/><g class="agent-eyes"><circle cx="9" cy="11.4" r="1.3"/><circle cx="15" cy="11.4" r="1.3"/></g><path d="M9.6 15.2h4.8"/><path d="M2.4 10.6v3.2M21.6 10.6v3.2"/></svg></span>
  <div><span class="agent-badge"><i></i>In development</span>
  <h2>What they'll write</h2></div>
 </div>
 <ul class="agent-does">%s</ul>
 <p class="agent-review"><span class="agent-shield" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3.5 5 6v5.5c0 4.3 3 7.6 7 9 4-1.4 7-4.7 7-9V6z"/><path d="m9 12 2.2 2.2L15.5 10"/></svg></span>You review everything before it goes near your store.</p>
</div>

<div class="agent-join">
 <form id="agents-form" novalidate>
  <input type="hidden" name="store" value="%s">
  <label for="agents-email">Get early access</label>
  <p class="agent-join-note">We'll email you when the first agent is ready, and we'll ask what you want it to write first.</p>
  <div class="agent-row">
   <input type="email" id="agents-email" name="email" placeholder="you@yourbrand.com" autocomplete="email" required>
   <button type="submit" class="btn">Join the waitlist</button>
  </div>
  <p class="err" id="agents-err" role="alert" hidden></p>
 </form>
 <div class="agent-done" id="agents-done" hidden role="status">
  <b><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7"/></svg>You're on the list</b>
  <span>We'll email <span id="agents-done-email"></span> when the first agent is ready.</span>
 </div>
</div>
</div>
<script>
(()=>{const f=document.getElementById('agents-form');if(!f)return;
const KEY='produkto-waitlist-email',err=document.getElementById('agents-err'),
      done=document.getElementById('agents-done'),email=document.getElementById('agents-email');
const get=()=>{try{return localStorage.getItem(KEY)||''}catch(e){return ''}};
const put=v=>{try{localStorage.setItem(KEY,v)}catch(e){}};
// The same remembered address as the buyer-question dialog: someone who
// already joined from a question should not be asked to join again here.
const joined=get();
function show(a){document.getElementById('agents-done-email').textContent=a;
  f.hidden=true;done.hidden=false;}
if(joined)show(joined);
f.addEventListener('submit',async e=>{e.preventDefault();err.hidden=true;
 const b=f.querySelector('button');b.disabled=true;b.textContent='Joining…';
 const d=new URLSearchParams(new FormData(f));d.set('source','%s');
 try{const r=await fetch('/api/waitlist',{method:'POST',body:d});const j=await r.json();
  if(j.error){err.textContent=j.error;err.hidden=false;b.disabled=false;b.textContent='Join the waitlist';return;}
  put(email.value.trim());show(email.value.trim());
 }catch(x){err.textContent='Could not join just now. Please try again.';err.hidden=false;
  b.disabled=false;b.textContent='Join the waitlist';}});})();
</script>""" % (items, E(store), E(SOURCE))
    return 200, body
