# Demo booking

The website now has Book a demo buttons and an inline booking area. It is not connected yet: `dist/booking-config.js` has an empty `url`.

Use a Google Calendar appointment schedule to collect bookings directly on the calendar. A Codex calendar connection alone does not provide public website booking.

## Account setup

In the intended Google account, create an appointment schedule named **Produkto demo**, duration **20 minutes**. Set the owner's chosen availability and timezone, enable conflict checks on the intended calendar, and choose Google Meet. Collect name, email, and a required store URL question. Suggested settings for the owner to confirm: 24 hours' minimum notice and a 10-minute buffer.

Use Booking pages → Sharing options → Website embed → Inline booking page. Copy the `src` URL into the `url` field in `dist/booking-config.js`. Use the full `https://calendar.google.com/calendar/appointments/schedules/...` URL, not a shortened link or a normal calendar embed.

Then check the actual public booking page, availability/timezone, required store URL, and confirmation flow. A test reservation should be made only with the owner's authorization for the chosen time and attendee address. Do not declare calendar sync verified until the resulting event has been checked.

No customer information is submitted to this static site. Google handles the booking form and confirmation. The unconfigured state shows an honest availability notice without invented dates or time slots. Do not publish that state as a working booking flow.

## Owner's confirmed settings — 26 September 2026

- Name: Produkto demo
- Duration: 20 minutes
- Availability: Monday–Friday, 10:00–17:00
- Timezone: Europe/Madrid
- Calendar account: still to be confirmed in the signed-in Calendar UI
- Creation is pending: built-in browser control failed to initialize; Chrome has JavaScript from Apple Events disabled. No schedule or calendar connection has been created yet.

## Cal.com — chosen 28 September 2026

Kelian chose Cal.com over the Google appointment schedule: real availability from his Google Calendar, real confirmations, and the month-view layout of his reference. The site is wired for it (`app.js`, "Cal.com booking"); it stays on the "available soon" notice until a link is pasted.

To switch it on:
1. Create a free Cal.com account and connect the Google Calendar that should block busy times (and receive bookings).
2. Create an event type: **Produkto demo**, 20 minutes, Google Meet, Mon–Fri 10:00–17:00 Europe/Madrid. Ask for name, email and store URL.
3. Paste the link part (e.g. `kelian/produkto-demo`) into `calLink` in `dist/booking-config.js`.
4. Check the live page, then make one test booking only with Kelian's say-so.

The embed runs dark with Produkto navy colours (`cssVarsPerTheme` in `app.js`). The "Or send a note" form from the reference is not built: a static site cannot send it.

## Calendly — replaced Cal.com, 28 September 2026

Kelian switched to Calendly (free) after learning Cal.com charges to remove its logo. Link: `https://calendly.com/kelianvtla/30min`, set as `calendly` in `dist/booking-config.js` (it takes priority over `calLink`). The inline embed runs dark navy (`background_color=050f22`, white text/accent) and is capped at 620px wide so Calendly uses its compact layout; wider, Calendly adds a white page margin around its card. The "Powered by Calendly" corner ribbon stays on the free plan. The event itself is 15 minutes despite the `/30min` slug; the heading avoids naming a length.

## "Or send a note" form — 28 September 2026

Built under the calendar after Kelian's reference. Delivery uses Web3Forms (free, no branding): get an access key at web3forms.com with the inbox that should receive notes, paste it into `noteKey` in `dist/booking-config.js`. The key is public by design (it only lets people send to that inbox). Until it is set, submitting shows "Notes aren't switched on yet" and nothing is sent. A hidden `botcheck` field filters simple spam.
