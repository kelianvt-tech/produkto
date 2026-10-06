// Power Dialer voice engine: the web dialer's softphone, driven by the iOS app.
//
// Protocol, one JSON object per message:
//   app -> page  {type:"start", token}   register a Twilio.Device with a voice token
//                {type:"token", token}   refresh the token before it expires
//                {type:"arm", armed}     accept the operator leg only while armed
//                {type:"mute", muted}    mute or unmute the live call
//                {type:"hangup"}         drop the operator leg from this end
//   page -> app  loaded | ready | mic {granted} | call {state} | muted {muted}
//                token-expiring | error {code, message}
//
// Mirrors ensureDevice() in brain-dialer.js on purpose, down to the codec order and
// the silenced SDK sounds, so a fix to one is visibly a fix to the other.
(function () {
  "use strict";

  var MIC_CONSTRAINTS = {
    audio: { echoCancellation: true, noiseSuppression: false, autoGainControl: true },
  };

  var device = null;
  var call = null;
  // The server addresses the operator as one shared client identity, so a laptop
  // with the web dialer open receives the same leg. Answering only while armed
  // means this phone never grabs a call that a laptop session asked for.
  var armed = false;

  function post(type, detail) {
    var message = { type: type };
    if (detail) {
      for (var key in detail) {
        if (Object.prototype.hasOwnProperty.call(detail, key)) message[key] = detail[key];
      }
    }
    try {
      window.ReactNativeWebView.postMessage(JSON.stringify(message));
    } catch (_error) {
      // Opened outside the app: there is nobody to tell.
    }
  }

  function errorMessage(error) {
    if (error && error.code === 31401) {
      return "The microphone was refused, so the call cannot be taken on this phone.";
    }
    return "Softphone error: " + ((error && error.message) || "unknown");
  }

  // Ask for the microphone before any call exists. The first request raises iOS's
  // permission sheet, and raising it while an operator leg is ringing would let the
  // leg time out behind the sheet.
  function warmMicrophone() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      post("mic", { granted: false });
      return Promise.resolve(false);
    }
    return navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS).then(
      function (stream) {
        stream.getTracks().forEach(function (track) { track.stop(); });
        post("mic", { granted: true });
        return true;
      },
      function () {
        post("mic", { granted: false });
        return false;
      }
    );
  }

  function attach(incoming) {
    call = incoming;
    var ended = function () {
      if (call === incoming) call = null;
      post("call", { state: "ended" });
    };
    incoming.on("disconnect", ended);
    incoming.on("cancel", ended);
    incoming.on("reject", ended);
    incoming.on("error", function (error) {
      post("error", { code: error && error.code, message: errorMessage(error) });
    });
  }

  function start(token) {
    if (!window.Twilio || !window.Twilio.Device) {
      post("error", { message: "The softphone did not load. Check the connection and reopen the app." });
      return Promise.resolve();
    }
    if (device) {
      device.updateToken(token);
      post("ready");
      return Promise.resolve();
    }
    device = new window.Twilio.Device(token, {
      edge: ["ashburn", "umatilla", "roaming"],
      codecPreferences: ["opus", "pcmu"],
      maxAverageBitrate: 32000,
      logLevel: "error",
      sounds: { incoming: false, outgoing: false, disconnect: false },
      disableAudioContextSounds: true,
    });
    if (device.audio) {
      if (typeof device.audio.incoming === "function") device.audio.incoming(false);
      if (typeof device.audio.outgoing === "function") device.audio.outgoing(false);
      if (typeof device.audio.disconnect === "function") device.audio.disconnect(false);
      if (typeof device.audio.setAudioConstraints === "function") {
        device.audio.setAudioConstraints(MIC_CONSTRAINTS.audio);
      }
    }
    device.on("incoming", function (incoming) {
      if (!armed) {
        // Neither accept nor reject: a reject from one registered device can end the
        // ring for every device, which would break a session started on the laptop.
        return;
      }
      attach(incoming);
      incoming.accept({ rtcConstraints: MIC_CONSTRAINTS });
      post("call", { state: "connected" });
    });
    device.on("tokenWillExpire", function () { post("token-expiring"); });
    device.on("registered", function () { post("ready"); });
    device.on("unregistered", function () { post("call", { state: "unregistered" }); });
    device.on("error", function (error) {
      post("error", { code: error && error.code, message: errorMessage(error) });
    });
    return warmMicrophone().then(function () { return device.register(); });
  }

  function handle(raw) {
    var message;
    try {
      message = typeof raw === "string" ? JSON.parse(raw) : raw;
    } catch (_error) {
      return;
    }
    if (!message || typeof message.type !== "string") return;
    if (message.type === "start" && message.token) {
      start(message.token).catch(function (error) {
        post("error", { code: error && error.code, message: errorMessage(error) });
      });
    } else if (message.type === "token" && message.token && device) {
      device.updateToken(message.token);
    } else if (message.type === "arm") {
      armed = !!message.armed;
    } else if (message.type === "mute" && call) {
      call.mute(!!message.muted);
      post("muted", { muted: !!message.muted });
    } else if (message.type === "hangup" && call) {
      call.disconnect();
    }
  }

  // react-native-webview delivers postMessage on window for iOS and on document
  // for Android; listening on both costs nothing.
  window.addEventListener("message", function (event) { handle(event.data); });
  document.addEventListener("message", function (event) { handle(event.data); });

  // Exposed for the node test, which has no web view to post through.
  window.__powerDialerEngine = { handle: handle, isArmed: function () { return armed; } };

  post("loaded");
})();
