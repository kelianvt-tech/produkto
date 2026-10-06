const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// The softphone page a phone app loads (static/phone-engine.js) in a hidden web view
// and drives over postMessage. These run it against a fake Twilio
// SDK, because the one rule that matters most -- answer only while armed -- decides
// whether the phone steals a call that a laptop session placed.

const source = fs.readFileSync(path.join(__dirname, '../parallel_dialer/static/phone-engine.js'), 'utf8');

function makeCall() {
  const handlers = {};
  return {
    accepted: null,
    rejected: false,
    muted: false,
    disconnected: false,
    on(name, fn) { handlers[name] = fn; },
    emit(name, value) { if (handlers[name]) handlers[name](value); },
    accept(options) { this.accepted = options; },
    reject() { this.rejected = true; },
    mute(value) { this.muted = value; },
    disconnect() { this.disconnected = true; this.emit('disconnect'); },
  };
}

async function boot({ micGranted = true } = {}) {
  const posted = [];
  const devices = [];
  const listeners = { window: {}, document: {} };
  class Device {
    constructor(token, options) {
      this.token = token;
      this.options = options;
      this.handlers = {};
      this.registered = false;
      this.audio = { incoming() {}, outgoing() {}, disconnect() {}, setAudioConstraints() {} };
      devices.push(this);
    }
    on(name, fn) { this.handlers[name] = fn; }
    emit(name, value) { if (this.handlers[name]) this.handlers[name](value); }
    updateToken(token) { this.token = token; }
    async register() { this.registered = true; this.emit('registered'); }
  }
  const window = {
    Twilio: { Device },
    ReactNativeWebView: { postMessage: (text) => posted.push(JSON.parse(text)) },
    addEventListener: (name, fn) => { listeners.window[name] = fn; },
  };
  const document = { addEventListener: (name, fn) => { listeners.document[name] = fn; } };
  const navigator = {
    mediaDevices: {
      getUserMedia: () => (micGranted
        ? Promise.resolve({ getTracks: () => [{ stop() {} }] })
        : Promise.reject(new Error('NotAllowedError'))),
    },
  };
  vm.runInNewContext(source, { window, document, navigator, JSON, Object, Promise });
  const engine = window.__powerDialerEngine;
  const send = async (message) => {
    engine.handle(JSON.stringify(message));
    // Let the microphone warm-up and register() promises settle.
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setImmediate(resolve));
  };
  return { posted, devices, engine, send, types: () => posted.map((m) => m.type) };
}

test('announces itself so the app knows when to hand over a token', async () => {
  const { types } = await boot();
  assert.deepEqual(types(), ['loaded']);
});

test('starting registers one device, warms the microphone first, then reports ready', async () => {
  const { send, devices, posted, types } = await boot();
  await send({ type: 'start', token: 'tok-1' });
  assert.equal(devices.length, 1);
  assert.equal(devices[0].token, 'tok-1');
  assert.equal(devices[0].registered, true);
  // Same codec order and silenced sounds as the web dialer's ensureDevice().
  assert.deepEqual(Array.from(devices[0].options.codecPreferences), ['opus', 'pcmu']);
  assert.equal(devices[0].options.sounds.incoming, false);
  const order = types();
  assert.ok(order.indexOf('mic') < order.indexOf('ready'), 'the permission sheet must come before any call can ring');
  assert.equal(posted.find((m) => m.type === 'mic').granted, true);
  // A second start refreshes the token instead of registering a second device.
  await send({ type: 'start', token: 'tok-2' });
  assert.equal(devices.length, 1);
  assert.equal(devices[0].token, 'tok-2');
});

test('an unarmed phone neither answers nor rejects, so a laptop session keeps its call', async () => {
  const { send, devices, types } = await boot();
  await send({ type: 'start', token: 'tok' });
  const call = makeCall();
  devices[0].emit('incoming', call);
  assert.equal(call.accepted, null);
  assert.equal(call.rejected, false);
  assert.equal(types().includes('call'), false);
});

test('an armed phone answers the operator leg the way the browser does', async () => {
  const { send, devices, posted } = await boot();
  await send({ type: 'start', token: 'tok' });
  await send({ type: 'arm', armed: true });
  const call = makeCall();
  devices[0].emit('incoming', call);
  assert.ok(call.accepted, 'the leg is accepted');
  assert.equal(call.accepted.rtcConstraints.audio.echoCancellation, true);
  assert.deepEqual({ ...posted.at(-1) }, { type: 'call', state: 'connected' });
});

test('mute reaches the live call and is reported back; hangup ends it', async () => {
  const { send, devices, posted } = await boot();
  await send({ type: 'start', token: 'tok' });
  await send({ type: 'arm', armed: true });
  const call = makeCall();
  devices[0].emit('incoming', call);

  await send({ type: 'mute', muted: true });
  assert.equal(call.muted, true);
  assert.deepEqual({ ...posted.at(-1) }, { type: 'muted', muted: true });

  await send({ type: 'hangup' });
  assert.equal(call.disconnected, true);
  assert.deepEqual({ ...posted.at(-1) }, { type: 'call', state: 'ended' });
});

test('a refused microphone is reported, not swallowed', async () => {
  const { send, posted } = await boot({ micGranted: false });
  await send({ type: 'start', token: 'tok' });
  assert.equal(posted.find((m) => m.type === 'mic').granted, false);
});

test('a refused microphone during a call reads as a microphone problem', async () => {
  const { send, devices, posted } = await boot();
  await send({ type: 'start', token: 'tok' });
  devices[0].emit('error', { code: 31401, message: 'Permission denied' });
  assert.match(posted.at(-1).message, /microphone was refused/);
});

test('garbage from the app is ignored rather than thrown', async () => {
  const { engine, types } = await boot();
  assert.doesNotThrow(() => engine.handle('not json'));
  assert.doesNotThrow(() => engine.handle(JSON.stringify({ nope: true })));
  assert.deepEqual(types(), ['loaded']);
});
