"""Buy answers by scraping, through Apify, instead of paying an API.

Why this exists: an answer bought from the OpenAI Responses API costs about
9.6 cents, because OpenAI bills back every word of every web page the model
read before answering. The same answer scraped off ChatGPT Search costs half
a cent. See DECISIONS.md, 2026-09-20.

Three engines, one module. ChatGPT, Google's AI Overview and Perplexity each
have their own Apify actor, but all three take the same input - a
newline-separated `queries` string and nothing else - and all three return the
same shape:

    {"query": "...", "text": "...", "sources": [{"url": ..., "title": ...}]}

so the parsing below is shared. Verified against live runs of all three on
2026-09-21. If an actor ever changes shape, `collect()` is the one place to fix.

There is no country, no proxy, no model setting on any of them. That is a real
limitation: answers come back from wherever the scraper's proxy sits, so a UK
store can get euro prices. Known and accepted; see the decision log.

Shape of a scan under this module:

  one actor run per engine per run number, each containing every buyer question

Not one run per answer. An actor run charges a (tiny) start fee and takes
about 45 seconds per query, so batching is both cheaper and faster. Three
engines x five runs of fifty questions is fifteen actor runs, fired together.

A note on AI Overview: Google does not show an overview for every search, and
the actor only bills for the ones it captures. A question that comes back
empty there is a real finding - no overview was shown - not a failure, but it
does mean the three engines will not always return the same number of answers.

Standard library only, same as llm.py.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import config

BASE = "https://api.apify.com/v2"


class ApifyError(Exception):
    """Message is meant to be shown to the user as-is."""


def _token():
    token = config.env("APIFY_TOKEN")
    if not token:
        raise ApifyError(
            "No Apify token found. Add APIFY_TOKEN=... to mvp/app/.env "
            "(get one at console.apify.com/settings/integrations), then "
            "restart the app.")
    return token


def _request(method, path, body=None, timeout=60):
    url = "%s%s%stoken=%s" % (BASE, path, "&" if "?" in path else "?",
                              urllib.parse.quote(_token()))
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read()).get("error", {}).get("message", "")
        except Exception:                                       # noqa: BLE001
            pass
        if e.code == 401:
            raise ApifyError("Apify rejected the token (401). Check "
                             "APIFY_TOKEN in mvp/app/.env.")
        raise ApifyError("Apify returned HTTP %d: %s" % (e.code, detail or e.reason))
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise ApifyError("Couldn't reach Apify (%s)." % e)


def _citations(item):
    """Apify's `sources` -> the {url, title} shape the rest of the app uses."""
    out = []
    for s in item.get("sources") or []:
        if s.get("url"):
            out.append({"url": s["url"], "title": s.get("title", "")})
    return out


def actor_for(engine):
    """The Apify actor that answers as this engine."""
    spec = config.ENGINES.get(engine)
    if not spec:
        raise ApifyError("No Apify actor is configured for engine %r." % engine)
    return spec["actor"]


def start_run(questions, engine=config.DEFAULT_ENGINE):
    """Fire the actor and return (run_id, dataset_id) straight away.

    Split out from the waiting so the caller can write both ids down before
    a single answer exists. From that moment the batch is recoverable: the
    dataset outlives our process, so a crash costs time, not money.
    """
    actor = actor_for(engine).replace("/", "~")
    run = _request("POST", "/acts/%s/runs" % actor,
                   {"queries": "\n".join(questions)})["data"]
    return run["id"], run["defaultDatasetId"]


def wait(run_id, poll=10, timeout=1800):
    deadline = time.time() + timeout
    while True:
        status = _request("GET", "/actor-runs/%s" % run_id)["data"]["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            return status
        if time.time() > deadline:
            raise ApifyError("Apify run %s did not finish within %d seconds."
                             % (run_id, timeout))
        time.sleep(poll)


def collect(dataset_id, status="SUCCEEDED", run_id="", engine=config.DEFAULT_ENGINE):
    """Read a finished run's answers. Safe to call again after a crash."""
    items = _request("GET", "/datasets/%s/items?clean=true" % dataset_id)
    if status != "SUCCEEDED" and not items:
        raise ApifyError("Apify run %s ended as %s with no answers."
                         % (run_id or dataset_id, status))
    actor = config.ENGINES.get(engine, {}).get("actor", engine)
    results = {}
    for item in items if isinstance(items, list) else []:
        text = (item.get("text") or "").strip()
        query = item.get("query") or ""
        if text and query:
            results[query] = (text, _citations(item), actor)
    return results


def ask_batch(questions, usage=None, poll=10, timeout=1800, on_start=None,
              engine=config.DEFAULT_ENGINE):
    """Ask every question once, on one engine.

    Returns {question: (text, citations, model)}.

    `on_start(run_id, dataset_id)` is called before any waiting begins - that
    is the hook that makes the batch survive a restart.

    Questions that came back empty are simply absent from the result, so the
    caller can record them as failures rather than storing a blank answer.
    On AI Overview that is the normal case for some questions, because Google
    does not always show an overview.
    """
    run_id, dataset_id = start_run(questions, engine)
    if on_start:
        on_start(run_id, dataset_id)
    status = wait(run_id, poll=poll, timeout=timeout)
    results = collect(dataset_id, status, run_id, engine)
    if usage is not None:
        usage.add_scraped(len(results), engine)
    return results


def check():
    """Tiny live call to confirm the token works. Buys one answer per engine."""
    out = []
    for engine in config.SCAN_ENGINES:
        try:
            got = ask_batch(["What are the top 5 CRM tools?"], engine=engine)
            out.append("%s (%s) -> %d answer(s)"
                       % (config.engine_label(engine), actor_for(engine), len(got)))
        except ApifyError as e:
            out.append("%s -> FAILED: %s" % (config.engine_label(engine), e))
    return out

