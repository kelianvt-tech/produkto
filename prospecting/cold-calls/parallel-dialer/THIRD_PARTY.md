# Third-party components

Bundled in `parallel_dialer/static`:

- **Twilio Voice JavaScript SDK 2.18.5** (`twilio-voice-2.18.5.js`, `@twilio/voice-sdk`), the browser
  softphone. Apache License 2.0, Copyright Twilio Inc.; it bundles `rtcpeerconnection-shim`
  (BSD-3-Clause), `backoff` and `loglevel` (MIT). The licence text Twilio ships with it is in
  `licenses/twilio-voice-sdk-LICENSE.md`. Source: <https://github.com/twilio/twilio-voice.js>.
- **Manrope** (`fonts/manrope-latin.woff2`), the typeface. SIL Open Font License 1.1, Copyright 2018
  The Manrope Project Authors. The licence is in `licenses/manrope-OFL.txt`. Source:
  <https://github.com/googlefonts/manrope>.

Python dependencies are listed in `pyproject.toml` and installed from PyPI under their own licences.
