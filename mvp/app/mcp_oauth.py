"""OAuth for the hosted MCP endpoint, so a merchant can add Produkto in
claude.ai or ChatGPT and sign in with their normal Produkto login.

The standard MCP flow (OAuth 2.1 with PKCE and dynamic client registration):

1. The assistant calls /mcp, gets 401 with a link to
   /.well-known/oauth-protected-resource, which names this app as the
   authorization server.
2. It reads /.well-known/oauth-authorization-server, registers itself at
   /oauth/register and gets a client id.
3. It sends the merchant to /oauth/authorize. They sign in if needed and
   click Allow. We send them back to the assistant with a one-time code.
4. The assistant swaps the code for an access token at /oauth/token, and
   later swaps its refresh token for new ones.

Only hashes of codes and tokens are stored. An access token sees exactly
what its user sees in the app; revoking happens in Settings.
"""
import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from html import escape as E

import accounts
import config
import db

ACCESS_SECONDS = 3600
REFRESH_SECONDS = 90 * 86400
CODE_SECONDS = 600

SCHEMA = """
CREATE TABLE IF NOT EXISTS oauth_clients (client_id TEXT PRIMARY KEY, name TEXT, redirect_uris TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS oauth_codes (code_hash TEXT PRIMARY KEY, client_id TEXT, user_id INTEGER, redirect_uri TEXT,
    challenge TEXT, expires_at REAL, used INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS oauth_tokens (token_hash TEXT PRIMARY KEY, kind TEXT, user_id INTEGER, client_id TEXT,
    expires_at REAL, created_at REAL);
"""
def init():
    # Cheap (IF NOT EXISTS), and run every time so a switched database (tests) gets the tables too.
    with db.conn() as c:
        c.executescript(SCHEMA)


def _h(value):
    return hashlib.sha256(value.encode()).hexdigest()


def base():
    return (config.env("PRODUKTO_BASE_URL") or accounts.base_url()).rstrip("/")


def _json(code, obj, headers=None):
    return code, json.dumps(obj), dict({"Content-Type": "application/json", "Cache-Control": "no-store"}, **(headers or {}))


def _error(code, err, desc=""):
    return _json(code, dict(error=err, error_description=desc))


# --- discovery -----------------------------------------------------------------

def resource_metadata():
    return _json(200, dict(resource=base() + "/mcp", authorization_servers=[base()],
                           bearer_methods_supported=["header"], resource_name="Produkto"))


def server_metadata():
    b = base()
    return _json(200, dict(issuer=b, authorization_endpoint=b + "/oauth/authorize", token_endpoint=b + "/oauth/token",
                           registration_endpoint=b + "/oauth/register", response_types_supported=["code"],
                           grant_types_supported=["authorization_code", "refresh_token"],
                           code_challenge_methods_supported=["S256"], token_endpoint_auth_methods_supported=["none"],
                           scopes_supported=["produkto"]))


def challenge_header():
    """What /mcp sends with a 401 so the assistant knows where to sign in."""
    return 'Bearer resource_metadata="%s/.well-known/oauth-protected-resource"' % base()


# --- registration --------------------------------------------------------------

def _ok_redirect(uri):
    u = urllib.parse.urlparse(uri or "")
    if u.scheme == "https":
        return bool(u.netloc)
    if u.scheme == "http":
        return u.hostname in ("localhost", "127.0.0.1")
    # Desktop apps (e.g. cursor://) use their own scheme; never script or file ones.
    return bool(u.scheme) and u.scheme not in ("javascript", "data", "file", "vbscript")


def register(body):
    init()
    try:
        req = json.loads(body or "{}")
    except ValueError:
        return _error(400, "invalid_client_metadata", "Bad JSON.")
    uris = req.get("redirect_uris") or []
    if not uris or not all(isinstance(u, str) and _ok_redirect(u) for u in uris):
        return _error(400, "invalid_redirect_uri", "Give https redirect URIs.")
    cid = "pkc_" + secrets.token_urlsafe(16)
    name = str(req.get("client_name") or "AI assistant")[:80]
    db.write("INSERT INTO oauth_clients VALUES (?,?,?,?)", (cid, name, json.dumps(uris), time.time()))
    return _json(201, dict(client_id=cid, client_name=name, redirect_uris=uris, token_endpoint_auth_method="none",
                           grant_types=["authorization_code", "refresh_token"], response_types=["code"],
                           client_id_issued_at=int(time.time())))


def _client(cid):
    init()
    row = db.one("SELECT * FROM oauth_clients WHERE client_id=?", (cid or "",))
    return dict(row, redirect_uris=json.loads(row["redirect_uris"])) if row else None


# --- authorize (a signed-in page) ------------------------------------------------

def _check(q):
    c = _client(q.get("client_id"))
    if not c:
        return None, "This connection link isn't valid. Start again from your AI assistant."
    if q.get("redirect_uri") not in c["redirect_uris"]:
        return None, "This connection link points somewhere unexpected. Start again from your AI assistant."
    if q.get("response_type") != "code" or q.get("code_challenge_method") != "S256" or not q.get("code_challenge"):
        return None, "Your AI assistant sent an incomplete request. Start again from it."
    return c, ""


def authorize_page(q):
    """GET /oauth/authorize. The app's sign-in gate has already run, so a user is present."""
    c, err = _check(q)
    if err:
        return 400, '<div class="plain-page"><h1>Can\'t connect</h1><p>%s</p></div>' % E(err)
    user = accounts.current()
    stores = sorted(accounts.owned(user["id"])) if not user["is_admin"] else ["every store (admin)"]
    hidden = "".join('<input type="hidden" name="%s" value="%s">' % (E(k), E(v)) for k, v in q.items())
    return 200, """<div class="plain-page set-page"><h1>Connect %s to Produkto</h1>
<p class="page-description">Signed in as <b>%s</b>. It will see %s.</p>
<section class="set-card"><header><h2>It will be able to</h2></header><div class="set-body"><ul>
<li>Read your visibility, buyer questions, answers, citations, opportunities and content drafts</li>
<li>Edit buyer questions, mark opportunities, and draft, approve or schedule content</li>
<li>Start a paid scan or publish to Shopify, but only after you say yes in the chat</li></ul>
<p class="set-hint">You can turn this off at any time in Settings.</p></div>
<footer><form method="post" action="/oauth/authorize">%s<button name="allow" value="1">Allow</button>
<button name="allow" value="0">Cancel</button></form></footer></section></div>""" % (
        E(c["name"]), E(user["email"]), E(", ".join(stores) or "no store yet"), hidden)


def authorize_act(_q, form):
    """POST /oauth/authorize: Allow or Cancel, then back to the assistant."""
    c, err = _check(form)
    if err:
        return 400, '<div class="plain-page"><h1>Can\'t connect</h1><p>%s</p></div>' % E(err)
    back = dict(state=form["state"]) if form.get("state") else {}
    if form.get("allow") != "1":
        back["error"] = "access_denied"
    else:
        code = secrets.token_urlsafe(32)
        db.write("INSERT INTO oauth_codes(code_hash,client_id,user_id,redirect_uri,challenge,expires_at) VALUES (?,?,?,?,?,?)",
                 (_h(code), c["client_id"], accounts.current()["id"], form["redirect_uri"], form["code_challenge"],
                  time.time() + CODE_SECONDS))
        back["code"] = code
    sep = "&" if "?" in form["redirect_uri"] else "?"
    return 303, form["redirect_uri"] + sep + urllib.parse.urlencode(back)


# --- tokens ---------------------------------------------------------------------

def _issue(user_id, client_id):
    access, refresh = "pka_" + secrets.token_urlsafe(32), "pkr_" + secrets.token_urlsafe(32)
    now = time.time()
    with db.conn() as c:
        c.execute("INSERT INTO oauth_tokens VALUES (?,?,?,?,?,?)", (_h(access), "access", user_id, client_id, now + ACCESS_SECONDS, now))
        c.execute("INSERT INTO oauth_tokens VALUES (?,?,?,?,?,?)", (_h(refresh), "refresh", user_id, client_id, now + REFRESH_SECONDS, now))
    return _json(200, dict(access_token=access, token_type="Bearer", expires_in=ACCESS_SECONDS,
                           refresh_token=refresh, scope="produkto"))


def token(body):
    """POST /oauth/token (form-encoded)."""
    init()
    form = dict(urllib.parse.parse_qsl(body or ""))
    grant = form.get("grant_type")
    if grant == "authorization_code":
        row = db.one("SELECT * FROM oauth_codes WHERE code_hash=?", (_h(form.get("code", "")),))
        if not row or row["used"] or row["expires_at"] < time.time() or row["client_id"] != form.get("client_id") \
                or row["redirect_uri"] != form.get("redirect_uri"):
            return _error(400, "invalid_grant", "Code is invalid or expired.")
        db.write("UPDATE oauth_codes SET used=1 WHERE code_hash=?", (row["code_hash"],))
        verifier = form.get("code_verifier", "")
        test = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        if not verifier or not secrets.compare_digest(test, row["challenge"]):
            return _error(400, "invalid_grant", "PKCE check failed.")
        return _issue(row["user_id"], row["client_id"])
    if grant == "refresh_token":
        h = _h(form.get("refresh_token", ""))
        row = db.one("SELECT * FROM oauth_tokens WHERE token_hash=? AND kind='refresh' AND expires_at>?", (h, time.time()))
        if not row or (form.get("client_id") and form["client_id"] != row["client_id"]):
            return _error(400, "invalid_grant", "Refresh token is invalid or expired.")
        db.write("DELETE FROM oauth_tokens WHERE token_hash=?", (h,))      # one use each: rotate
        return _issue(row["user_id"], row["client_id"])
    return _error(400, "unsupported_grant_type")


def user_for_token(tok):
    if not tok or not tok.startswith("pka_"):
        return None
    init()
    row = db.one("SELECT u.* FROM oauth_tokens t JOIN users u ON u.id=t.user_id WHERE t.token_hash=? AND t.kind='access' "
                 "AND t.expires_at>? AND COALESCE(u.disabled,0)=0", (_h(tok), time.time()))
    return dict(row) if row else None


def connections(user_id):
    init()
    return db.all_("SELECT c.client_id, c.name, MAX(t.created_at) AS last FROM oauth_tokens t JOIN oauth_clients c "
                   "ON c.client_id=t.client_id WHERE t.user_id=? AND t.expires_at>? GROUP BY c.client_id ORDER BY last DESC",
                   (user_id, time.time()))


def revoke(user_id, client_id=None):
    init()
    if client_id:
        db.write("DELETE FROM oauth_tokens WHERE user_id=? AND client_id=?", (user_id, client_id))
    else:
        db.write("DELETE FROM oauth_tokens WHERE user_id=?", (user_id,))


def handle(method, path, body):
    """The public OAuth endpoints (no cookie). Returns (code, text, headers) or None."""
    if path.startswith("/.well-known/oauth-protected-resource"):
        return resource_metadata()
    if path.startswith("/.well-known/oauth-authorization-server") or path.startswith("/.well-known/openid-configuration"):
        return server_metadata()
    if path == "/oauth/register" and method == "POST":
        return register(body)
    if path == "/oauth/token" and method == "POST":
        return token(body)
    return None
