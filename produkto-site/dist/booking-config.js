// Demo booking runs on Cal.com (month view, availability from Kelian's calendar).
// Paste the event's link, without https://cal.com/ — e.g. 'kelian/produkto-demo'.
// This is a public booking link, never a password or API key.
// `url` is the older Google Calendar appointment option; leave it empty.
// Calendly (chosen 2026-09-28) wins over Cal.com when both are set.
// noteKey: Web3Forms access key (free, public by design) - notes go to the email it was made for.
window.PRODUKTO_BOOKING = Object.freeze({ noteKey: '', calendly: 'https://calendly.com/kelianvtla/30min', calLink: '', url: '' });
