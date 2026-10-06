"""Asks for each dialer key (typing stays hidden), then writes them into the server's .env.
Press Enter on any question to leave that value unchanged."""
import getpass, subprocess, shlex

SSH = ["ssh", "-i", "/Users/kelianvantulder/.ssh/produkto_hetzner", "root@2.28.131.206"]
ENV = "/opt/parallel-dialer/.env"
FIELDS = [
    ("TWILIO_ACCOUNT_SID", "Twilio Account SID (starts AC..., on the Twilio console home page)", True),
    ("TWILIO_API_KEY_SID", "Twilio API key SID (starts SK...; Account > API keys & tokens > Create API key, Standard)", True),
    ("TWILIO_API_KEY_SECRET", "Twilio API key Secret (shown once when you create the key)", True),
    ("TWILIO_PHONE_NUMBER", "Your Twilio phone number, like +15551234567", False),
    ("CLOSE_API_KEY", "Close API key (Close > Settings > Developer > API keys > New)", True),
    ("OPENAI_API_KEY", "OpenAI API key (platform.openai.com > API keys)", True),
    ("DIALER_ALLOWED_TEST_NUMBERS", "Your own mobile, like +34600111222 (the only number it may call for now)", False),
    ("DIALER_CALLBACK_NUMBER", "Your Close phone number, like +15551234567", False),
]

updates = {}
for key, question, secret in FIELDS:
    ask = getpass.getpass if secret else input
    value = ask(f"\n{question}\n> ").strip()
    if value:
        updates[key] = value
updates["DIALER_LIVE_MODE"] = "enabled"

script = "set -e; f=%s\n" % ENV
for k, v in updates.items():
    line = shlex.quote(f"{k}={v}")
    script += (f"grep -q '^{k}=' $f && sed -i '/^{k}=/d' $f; "
               f"sed -i '/^#{k}=/d' $f; echo {line} >> $f\n")
script += "systemctl restart parallel-dialer; sleep 3; curl -s 127.0.0.1:8767/health"
out = subprocess.run(SSH + ["bash", "-s"], input=script, text=True, capture_output=True)
print("\nSaved", len(updates), "settings." if out.returncode == 0 else "-- something went wrong:\n" + out.stderr)
print(out.stdout)
