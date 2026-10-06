"""Run today's due scans, then exit. Meant for launchd, not for a person.

The Flask app runs the same scheduler in a thread, but only while the app is
open. This script is the version that does not need the app: launchd wakes it
every half hour, it asks the same `scheduler.due()` which stores still owe
today a scan, runs them, and quits.

Running both is safe. `scan.start` claims a store inside a BEGIN IMMEDIATE
transaction, so two processes cannot start the same store's scan; whichever
asks first wins and the other finds nothing due.

Exit codes: 0 if every scan it started finished, 1 if any failed, so launchd's
log shows a bad night rather than hiding it.
"""

import sys
import time

import db
import scan
import scheduler

# A scan is minutes of work. This is the point at which we stop waiting and
# call it a bad night rather than leaving launchd holding a process all day.
MAX_WAIT_SECONDS = 90 * 60
POLL_SECONDS = 15


def log(msg):
    print("%s  %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


def status_of(token):
    row = db.one("SELECT status FROM scans WHERE token=?", (token,))
    return row["status"] if row else None


def wait_for(tokens, deadline):
    """Block until every token leaves 'running', or the deadline passes."""
    pending = dict(tokens)
    while pending and time.time() < deadline:
        for domain, token in list(pending.items()):
            state = status_of(token)
            if state != "running":
                log("%s finished: %s" % (domain, state))
                del pending[domain]
        if pending:
            time.sleep(POLL_SECONDS)
    for domain in pending:
        log("%s still running when we gave up waiting" % domain)
    return pending


def main():
    db.init()
    # A scan interrupted by a reboot or a closed laptop is marked failed, so it
    # does not sit as 'running' forever and block tonight's scan.
    scan.recover_interrupted()

    due = scheduler.due()
    if not due:
        log("nothing due")
        return 0

    log("due: %s" % ", ".join(due))
    started = {}
    for domain in due:
        try:
            started[domain] = scan.start(domain)
            log("%s started" % domain)
        except Exception as e:                                  # noqa: BLE001
            # One store's problem must not stop the others.
            log("%s could not be started (%s)" % (domain, e))

    if not started:
        return 1

    stuck = wait_for(started, time.time() + MAX_WAIT_SECONDS)
    bad = [d for d, t in started.items()
           if d in stuck or status_of(t) not in ("done", "partial")]
    if bad:
        log("finished with problems: %s" % ", ".join(bad))
        return 1
    log("all done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
