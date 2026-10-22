"""Send one change to the cost tracker Google Sheet.

Usage: python3 log_cost.py '<json request without token>'
  e.g. python3 log_cost.py '{"action":"read"}'

Reads the web-app URL and token from ~/.produkto-cost-tracker (JSON: {"url": ..., "token": ...}),
so neither ever appears in chat or in this repo.
"""
import json
import pathlib
import sys
import urllib.request

cfg = json.loads((pathlib.Path.home() / ".produkto-cost-tracker").read_text())
req = json.loads(sys.argv[1])
req["token"] = cfg["token"]
# Apps Script answers a POST with a redirect to the result; urllib follows it as a GET.
r = urllib.request.urlopen(
    urllib.request.Request(cfg["url"], data=json.dumps(req).encode(), headers={"Content-Type": "application/json"}),
    timeout=60,
)
print(r.read().decode())
