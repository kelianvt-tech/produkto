"""The Support page: status, a contact form, and operational answers.

Three rules shaped this, all of them from what a paying merchant needs rather
than from what is easy to write.

  * The status line is COMPUTED, never a hardcoded "All systems operational".
    Produkto's numbers come from services we do not control, so when one is
    failing every merchant is affected at once and every one of them writes in
    separately. Saying so first kills that whole category of email.

  * The form carries the merchant's store, their last scan and their browser,
    so "my numbers look wrong" arrives with the context needed to answer it.
    Asking which store costs a round trip and makes the merchant feel unknown.

  * Methodology questions are not support questions. "How is visibility
    measured" lives in docs.py; this page answers "it is broken" and "how do I".

Requests are stored in the database rather than emailed: there is no mail
server here, and a request that is silently lost is worse than one that is
plainly recorded. The email address is shown as well so nobody is trapped.
"""

import json
import re
import time
from html import escape as E

import config
import db
import accounts
import scheduler
import storetime

SCHEMA = """CREATE TABLE IF NOT EXISTS support_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    topic TEXT,
    message TEXT NOT NULL,
    store_domain TEXT,
    last_scan_at REAL,
    user_agent TEXT,
    created_at REAL NOT NULL
)"""

EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

CONTACT_EMAIL = "kelianvtla@gmail.com"
# Stated in the merchant's terms as well as ours. Most Produkto merchants are
# in the US, where 9-18 CET is the small hours to midday Eastern - so a message
# sent in their afternoon is answered the next morning, and saying that plainly
# is better than letting them discover it.
HOURS_CET = "9:00-18:00 CET, Monday to Friday"
HOURS_ET = "3:00am-12:00pm Eastern"

TOPICS = ["A scan failed or is late", "My numbers look wrong",
          "Adding or changing a store", "Buyer questions", "Something else"]

# A scan that has not started this long after its slot is late enough to say so.
LATE_AFTER_SECONDS = 3 * 3600


def init():
    db.write(SCHEMA)


# --- Status -----------------------------------------------------------------

def status(now=None):
    """What to say at the top of the page. Computed from real scan state.

    `now` exists so the "scans are late" branch can be tested at a fixed time
    rather than only when the clock happens to cooperate.

    Returns (level, headline, detail) where level is ok / warn / down.
    """
    stores = scheduler.scheduled()
    if not stores:
        return 'ok', 'No stores scanning', 'Set up a store to start daily scans.'

    late, failed, running = [], [], []
    now = time.time() if now is None else now
    for domain in stores:
        last = scheduler.last_scan_at(domain)
        slot = scheduler.slot_today(domain, now)
        row = db.one("SELECT s.status FROM scans s JOIN prompt_sets p"
                     " ON p.id = s.prompt_set_id WHERE p.store_domain = ?"
                     " ORDER BY s.run_at DESC LIMIT 1", (domain,))
        state = row['status'] if row else None
        if state == 'running':
            running.append(domain)
            continue
        if state == 'failed':
            failed.append(domain)
        # Late only counts once the slot is well past and today has no scan.
        if now > slot + LATE_AFTER_SECONDS and (last is None or last < slot):
            late.append(domain)

    if failed:
        return ('down', 'Scans failing',
                '%s could not complete its most recent scan. We are on it.'
                % _list(failed))
    if late:
        return ('warn', 'Scans delayed',
                "Today's scan for %s has not started yet. Your dashboard is "
                "showing the last completed reading." % _list(late))
    if running:
        return 'ok', 'Scan in progress', '%s is being scanned now.' % _list(running)
    return ('ok', 'All systems operational',
            'Every store was scanned on schedule.')


def _list(domains):
    if len(domains) == 1:
        return domains[0]
    return ', '.join(domains[:-1]) + ' and ' + domains[-1]


# --- Requests ---------------------------------------------------------------

def save(email, topic, message, store_domain, user_agent):
    email = (email or '').strip().lower()
    message = (message or '').strip()
    if not EMAIL.match(email) or len(email) > 254:
        raise ValueError('Enter a valid email address.')
    if len(message) < 10:
        raise ValueError('Tell us a little more about what happened.')
    init()
    last = scheduler.last_scan_at(store_domain) if store_domain else None
    db.write('INSERT INTO support_requests(email,topic,message,store_domain,'
             'last_scan_at,user_agent,created_at) VALUES(?,?,?,?,?,?,?)',
             (email, (topic or '')[:100] or None, message[:5000],
              store_domain or None, last, (user_agent or '')[:300] or None,
              time.time()))
    return True


def api(q, form):
    """POST /api/support"""
    try:
        save(form.get('email'), form.get('topic'), form.get('message'),
             form.get('store'), form.get('ua'))
    except ValueError as e:
        return 200, ('json', json.dumps({'error': str(e)}))
    return 200, ('json', json.dumps({'ok': True}))


# --- Page -------------------------------------------------------------------

def _describe(domain):
    """'clubhouseskin.com · last scan 27 Sep, 11:40 BST'"""
    last = scheduler.last_scan_at(domain)
    if not last:
        return '%s · no scan yet' % domain
    tz = storetime.zone(domain)
    return '%s · last scan %s %s' % (domain, storetime.label(last, tz, '%-d %b, %H:%M'),
                                     storetime.abbrev(tz))


def _store_field():
    """The store attached to a request.

    With one store it is attached silently and simply stated. With several
    there is nothing to guess from, so the merchant picks — saying "attached
    automatically" and then sending nothing would be worse than asking."""
    stores = accounts.visible(scheduler.scannable())
    if not stores:
        return '', ''
    if len(stores) == 1:
        return ('<input type="hidden" name="store" value="%s">' % E(stores[0]),
                '<p class="form-context">Attached automatically: %s</p>'
                % E(_describe(stores[0])))
    # Most recently scanned first: it is the one they were most likely reading.
    stores = sorted(stores, key=lambda d: scheduler.last_scan_at(d) or 0, reverse=True)
    options = ''.join('<option value="%s">%s</option>' % (E(d), E(_describe(d)))
                      for d in stores)
    return ('<label>Which store?<select name="store">%s</select></label>' % options,
            '<p class="form-context">Your last scan for that store is attached '
            'automatically.</p>')


FAQ = [
    ("My scan hasn't run today.",
     "Scans run early each morning in your store's own timezone, and take a few "
     "minutes. The status line above says whether today's run is late. Your "
     "dashboard header always shows the exact time of the reading you are looking "
     "at, so you are never guessing how fresh it is."),
    ("How do I add another store?",
     'Use <a href="/new">Switch catalog</a> and paste the store address. It joins '
     'the daily scan once you finish setting up its buyer questions.'),
    ("I want to change my buyer questions.",
     'You can edit them yourself from the <b>Buyer questions</b> tab. Changing them '
     'starts a fresh trend line rather than continuing the old one, because a '
     'different question is a different measurement — the old readings are kept.'),
    ("Where can I see what was actually asked and answered?",
     'The <b>Answers</b> tab shows every answer collected, word for word, with the '
     'products named in it. Nothing on the dashboard is calculated from anything '
     'else.'),
]


def page(_q=None):
    level, headline, detail = status()
    store_field, context_line = _store_field()
    faq = ''.join('<dt>%s</dt><dd>%s</dd>' % (E(q), a) for q, a in FAQ)
    options = ''.join('<option>%s</option>' % E(t) for t in TOPICS)
    body = """<div class="plain-page"><h1>Support</h1>
<p class="page-description">Something broken, or a question the dashboard doesn't answer? Write to us below.</p>

<div class="status-card status-%s"><span class="status-dot"></span>
<div><b>%s</b><span>%s</span></div></div>

<section><h2>Contact us</h2>
<form id="support-form" class="support-form" novalidate>
%s
<label>Your email<input type="email" name="email" required autocomplete="email" placeholder="you@yourstore.com"></label>
<label>What's this about?<select name="topic">%s</select></label>
<label>What happened?<textarea name="message" rows="5" required placeholder="What you expected, and what you saw instead."></textarea></label>
%s
<p class="err" id="support-error" role="alert" hidden></p>
<button type="submit" class="btn">Send message</button>
<p class="form-note">We reply <b>the same day</b> during %s (%s). Messages sent after hours are answered the next working morning.<br>
You can also email <a href="mailto:%s">%s</a>.</p>
</form>
<p class="sent" id="support-sent" hidden>Thanks — your message is recorded, along with your store and last scan. We'll reply to you the same working day.</p>
</section>

<section><h2>Common questions</h2><dl class="faq">%s</dl>
<p class="small">Looking for how the numbers are worked out? That's in <a href="/docs">how Produkto measures</a>.</p></section>
</div>
<script>
(()=>{const f=document.getElementById('support-form');if(!f)return;
const err=document.getElementById('support-error'),sent=document.getElementById('support-sent');
f.addEventListener('submit',async e=>{e.preventDefault();err.hidden=true;
  const b=f.querySelector('button');b.disabled=true;b.textContent='Sending…';
  const d=new URLSearchParams(new FormData(f));d.set('ua',navigator.userAgent);
  try{const r=await fetch('/api/support',{method:'POST',body:d});const j=await r.json();
    if(j.error){err.textContent=j.error;err.hidden=false;b.disabled=false;b.textContent='Send message';return;}
    f.hidden=true;sent.hidden=false;
  }catch(x){err.textContent='Could not send. Please email us instead.';err.hidden=false;
    b.disabled=false;b.textContent='Send message';}});})();
</script>""" % (E(level), E(headline), E(detail), store_field, options,
                context_line, E(HOURS_CET), E(HOURS_ET),
                E(CONTACT_EMAIL), E(CONTACT_EMAIL), faq)
    return 200, body
