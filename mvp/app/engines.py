"""Which AI engines the dashboard is currently showing.

A scan buys every question from all three engines, so every panel could show
any mix of them. This module reads that choice off the page address and names
it; the filtering itself happens once, in `evidence.load`, so no panel has to
know the selection exists.

Selecting nothing is treated as selecting everything. A dashboard that goes
blank because a checkbox was unticked reads as a bug, and there is nothing
useful to show for an empty set anyway.
"""

import config
from html import escape


def logo(engine):
    """Use the provider's cached site icon alongside its visible name."""
    domain = {'chatgpt': 'chatgpt.com', 'ai-overview': 'google.com',
              'perplexity': 'perplexity.ai'}.get(engine)
    return ('<img class="engine-logo" src="/icon?d=%s" alt="" aria-hidden="true">'
            % escape(domain)) if domain else ''


def all_ids():
    return [e for e in config.ENGINE_ORDER if e in config.ENGINES]


def parse(query):
    """Read `engines=chatgpt,perplexity` off the address.

    Unknown names are dropped rather than rejected, so a stale link from
    before an engine was renamed still opens.
    """
    known = all_ids()
    raw = (query or {}).get('engines') or ''
    picked = [e.strip() for e in raw.split(',') if e.strip()]
    kept = [e for e in known if e in picked]
    return kept or known


def is_all(selected):
    return set(selected or []) >= set(all_ids())


def param(selected):
    """The value to put back in the address, or '' when everything is on."""
    return '' if is_all(selected) else ','.join(selected or [])


def label(selected):
    """How the selection reads on the button: 'All engines', or the names."""
    if is_all(selected):
        return 'All engines'
    if not selected:
        return 'All engines'
    if len(selected) == 1:
        return config.engine_label(selected[0])
    return '%d engines' % len(selected)


def note(selected):
    """A phrase naming the engines, for the sentence under the filter bar."""
    names = [config.engine_label(e) for e in (selected or all_ids())]
    if len(names) == 1:
        return names[0]
    return ', '.join(names[:-1]) + ' and ' + names[-1]


def options():
    """(id, label) for every engine, in display order."""
    return [(e, config.engine_label(e)) for e in all_ids()]
