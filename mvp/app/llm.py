"""Talk to OpenAI's Responses API using only the Python standard library.

Two kinds of call:

* ask_buyer_question()  - the "ChatGPT" answer, with web search switched on.
  Without web search the model answers from memory, which measures something
  the merchant can't influence.
* json_call()           - a helper call that must return JSON in a fixed
  shape (the buyer questions, or the list of products in an answer).

Failures that are worth retrying (rate limits, OpenAI hiccups) are retried
with a growing wait. Failures that aren't (bad key, unknown model) stop at
once with a message a person can act on.
"""

import json
import random
import threading
import time
import urllib.error
import urllib.request

import config

URL = "https://api.openai.com/v1/responses"
RETRYABLE = {408, 409, 429, 500, 502, 503, 504}


class LLMError(Exception):
    """Message is meant to be shown to the user as-is."""


# Shown to a customer when the problem is on our side (missing or revoked key,
# no OpenAI credit). The technical reason goes to Kelian by email instead.
OUR_SIDE = ("This step is unavailable right now because of a problem on our side. "
            "We've been alerted and are fixing it. Please try again in a little while.")


def _account_problem(detail):
    """Missing key, rejected key or no credit: alert Kelian (at most once an
    hour), log it, and give the customer a plain message."""
    print("OpenAI account problem:", detail, flush=True)
    try:
        import mailer
        mailer.alert("openai", "OpenAI is failing: %s" % detail[:120], [
            "The app could not use OpenAI: %s" % detail,
            "Customers see a 'problem on our side' message at the Topics and Questions steps, and scans "
            "can't read their answers until it's fixed. Put a working key in /opt/produkto/app/.env "
            "(OPENAI_API_KEY=...) and run: systemctl restart produkto",
        ])
    except Exception:                                       # noqa: BLE001
        pass
    return LLMError(OUR_SIDE)


class Usage:
    """Running token/search count for one scan (thread-safe)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.input_tokens = 0
        self.output_tokens = 0
        self.searches = 0
        self.models = set()
        self.by_model = {}
        self.scraped = 0        # answers bought from Apify, priced per answer
        self.by_engine = {}     # and the same split by engine, which is how
                                # they are priced - the three differ by 6.5x

    def add_scraped(self, n, engine=config.DEFAULT_ENGINE):
        """Count answers bought by scraping. They have no token usage."""
        with self.lock:
            self.scraped += n
            self.by_engine[engine] = self.by_engine.get(engine, 0) + n
            self.models.add(config.ENGINES.get(engine, {}).get("actor", engine))

    def add(self, resp):
        u = resp.get("usage") or {}
        with self.lock:
            self.input_tokens += u.get("input_tokens") or 0
            self.output_tokens += u.get("output_tokens") or 0
            self.searches += sum(1 for o in resp.get("output") or []
                                 if o.get("type") == "web_search_call")
            if resp.get("model"):
                self.models.add(resp["model"])
            model=resp.get('model') or 'unknown'
            row=self.by_model.setdefault(model,dict(input_tokens=0,cached_tokens=0,output_tokens=0,searches=0))
            row['input_tokens']+=u.get('input_tokens') or 0
            row['cached_tokens']+=(u.get('input_tokens_details') or {}).get('cached_tokens') or 0
            row['output_tokens']+=u.get('output_tokens') or 0
            row['searches']+=sum(1 for o in resp.get('output') or [] if o.get('type')=='web_search_call')

    def as_dict(self):
        with self.lock:
            return {"models": sorted(self.models),
                    "input_tokens": self.input_tokens,
                    "output_tokens": self.output_tokens,
                    "searches": self.searches, "scraped_answers": self.scraped,
                    "by_engine": dict(self.by_engine),
                    "by_model": {k:dict(v) for k,v in self.by_model.items()},
                    "price_date":config.PRICE_DATE}

    def cost_cents(self):
        total=0.0
        with self.lock:
            # Each engine has its own per-answer price. Anything counted
            # without an engine (older code paths) is priced as ChatGPT.
            counted=sum(self.by_engine.values())
            for engine,n in self.by_engine.items():
                total+=n*config.engine_price(engine)
            total+=max(0,self.scraped-counted)*config.engine_price(config.DEFAULT_ENGINE)
            for model,row in self.by_model.items():
                price=config.PRICES.get(model)
                if price is None:
                    candidates=[key for key in config.PRICES if model.startswith(key+'-')]
                    price=config.PRICES[max(candidates,key=len)] if candidates else None
                if price is None:
                    return None  # Unknown price is not free usage.
                uncached=max(0,row['input_tokens']-row['cached_tokens'])
                total+=(uncached*price[0]+row['cached_tokens']*price[1]+row['output_tokens']*price[2])/1000000
                total+=row['searches']*config.SEARCH_PRICE
        return total*100


def _post(body, attempts=5, timeout=180):
    key = config.api_key()
    if not key:
        raise _account_problem("No OpenAI API key found in mvp/app/.env.")
    data = json.dumps(body).encode()
    for attempt in range(attempts):
        req = urllib.request.Request(URL, data=data, method="POST", headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read()).get("error", {}).get("message", "")
            except Exception:                                   # noqa: BLE001
                pass
            if e.code == 401:
                raise _account_problem("OpenAI rejected the API key (401).")
            if e.code == 429 and "quota" in detail.lower():
                raise _account_problem("OpenAI is out of credit: " + detail)
            if e.code in RETRYABLE and attempt < attempts - 1:
                time.sleep(2 ** attempt + random.random())
                continue
            raise LLMError("OpenAI returned HTTP %d: %s" % (e.code, detail or e.reason))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt < attempts - 1:
                time.sleep(2 ** attempt + random.random())
                continue
            raise LLMError("Couldn't reach OpenAI (%s)." % e)
    raise LLMError("OpenAI kept failing after %d attempts." % attempts)


def _text_and_citations(resp):
    texts, cites = [], []
    for item in resp.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "output_text":
                texts.append(part.get("text") or "")
                for a in part.get("annotations") or []:
                    if a.get("type") == "url_citation" and a.get("url"):
                        cites.append({"url": a["url"], "title": a.get("title", "")})
    return "\n".join(texts).strip(), cites


def ask_buyer_question(question, usage=None, country=None):
    """Return (answer_text, citations, model_name)."""
    tool = {"type": "web_search"}
    where = country or config.BUYER_COUNTRY
    if where:
        tool["user_location"] = {"type": "approximate", "country": where}
    resp = _post({"model": config.ANSWER_MODEL, "tools": [tool],
                  "input": question})
    if usage:
        usage.add(resp)
    text, cites = _text_and_citations(resp)
    if not text:
        raise LLMError("OpenAI returned an empty answer.")
    return text, cites, resp.get("model") or config.ANSWER_MODEL


def json_call(instructions, user_input, schema_name, schema, usage=None, attempts=5):
    """`attempts` is lowered by optional callers (e.g. the onboarding brand
    profile) so a rate-limited key cannot stall a page the merchant is on."""
    resp = _post({
        "model": config.HELPER_MODEL,
        "instructions": instructions,
        "input": user_input,
        "text": {"format": {"type": "json_schema", "name": schema_name,
                            "schema": schema, "strict": True}},
    }, attempts=attempts)
    if usage:
        usage.add(resp)
    text, _ = _text_and_citations(resp)
    try:
        return json.loads(text)
    except ValueError:
        raise LLMError("OpenAI returned malformed JSON for %s." % schema_name)


def check():
    """Tiny live call to confirm the key and both model names work."""
    out = []
    for model in (config.ANSWER_MODEL, config.HELPER_MODEL):
        resp = _post({"model": model, "input": "Reply with the word ok."},
                     attempts=1, timeout=60)
        out.append("%s -> %s" % (model, resp.get("model")))
    return out
