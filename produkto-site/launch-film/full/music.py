"""Synthesised score for the launch film: dark A-minor pulse, built in numpy so there is no licence to clear.
score(SHOTS, DUR, SR, shock) -> (N, 2) float array. SHOTS maps shot id -> (real start, real length, stretch).
Sections: heartbeat under the opening, full drive from "Your AI visibility", hats + arp through the agents,
a riser into the end card, then silence at the white snap.
"""
import numpy as np

BPM = 124
BEAT = 60 / BPM


def _saw(freq, t, bright):
    """Band-limited saw, `bright` (array 0..1) sets how many harmonics are let through."""
    out = np.zeros_like(t)
    hmax = 2 + bright * 14
    for n in range(1, 17):
        w = np.clip(hmax - n + 1, 0, 1) / n
        out += w * np.sin(2 * np.pi * freq * n * t)
    return out


def score(SHOTS, DUR, SR, shock):
    N = int(DUR * SR); t = np.arange(N) / SR
    L = np.zeros(N); R = np.zeros(N)
    def at(s, d=0.0): return SHOTS[s][0] + d * SHOTS[s][2]
    drive = at('vis-dark')                  # full beat from here
    busy = at('quad-type')                  # arp under the four screens
    busy_end = at('scan')
    hats_on = at('llm-text')                # hats from the LLMs onward
    peak = at('agents')
    end = at('url')
    # overall shape: fade in, build, hold, silence at the snap
    shape = np.clip(t / 1.2, 0, 1) * np.where(t < shock, 1, 0)
    build = np.clip((t - drive) / (peak - drive), 0, 1)

    # chords: Am, F, Dm, E (two bars each)
    chords = [(55.0, [110.0, 130.81, 164.81]), (43.65, [87.31, 110.0, 130.81]),
              (36.71, [73.42, 87.31, 110.0]), (41.20, [82.41, 103.83, 123.47])]
    bar = 4 * BEAT
    idx = (t // (2 * bar)).astype(int) % 4
    # sidechain pump: dips right after each kick once the drive starts
    ph = (t % BEAT) / BEAT
    pump = np.where(t >= drive, 0.35 + 0.65 * np.clip(ph / 0.45, 0, 1), 1.0)

    # pad: detuned saws, brightening across the film
    bright = 0.15 + 0.6 * np.clip(t / DUR, 0, 1) + 0.25 * build
    pad = np.zeros(N)
    for c, (_, tones) in enumerate(chords):
        m = idx == c
        if not m.any(): continue
        for f in tones:
            for det, pan in ((0.997, -1), (1.003, 1)):
                v = _saw(f * det, t[m], bright[m]) * 0.06
                if pan < 0: L[m] += v * pump[m] * shape[m]
                else: R[m] += v * pump[m] * shape[m]

    # sub bass on the root
    root = np.array([chords[i][0] for i in idx])
    sub = np.sin(2 * np.pi * np.cumsum(root) / SR) * 0.32 * pump * shape * (0.6 + 0.4 * build)
    L += sub; R += sub

    # kick: heartbeat (every 2 beats, soft) before the drive, every beat after
    def kick(at_s, gain):
        n = int(0.32 * SR); tt = np.arange(n) / SR
        f = 42 + 90 * np.exp(-tt * 28); x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 9) * gain
        s = int(at_s * SR); e = min(N, s + n)
        if s < N: L[s:e] += x[:e - s]; R[s:e] += x[:e - s]
    k = 0.0
    while k < shock - 0.05:
        if k >= drive: kick(k, 0.55)
        elif int(round(k / BEAT)) % 2 == 0 and k > 0.3: kick(k, 0.3)
        k += BEAT

    # hats: 16ths, accent on the off-beat, from the LLM section to the end card
    rng = np.random.default_rng(5)
    hn = int(0.03 * SR); env = np.exp(-np.arange(hn) / (0.004 * SR))
    st = 0.0
    while st < shock - 0.05:
        if st >= hats_on:
            noise = rng.standard_normal(hn); noise = np.diff(np.concatenate([[0], noise]))   # cheap high-pass
            g = 0.05 if (st / (BEAT / 4)) % 4 not in (2,) else 0.09
            s = int(st * SR); e = min(N, s + hn)
            pan = 0.6 if int(st / (BEAT / 4)) % 2 else -0.6
            L[s:e] += noise[:e - s] * env[:e - s] * g * (1 - max(0, pan)); R[s:e] += noise[:e - s] * env[:e - s] * g * (1 + min(0, pan))
        st += BEAT / 4

    # arp: chord tones in 16ths, two octaves up, under the four screens and again under the agents/articles
    an = int(0.12 * SR); aenv = np.exp(-np.arange(an) / (0.03 * SR))
    st, i = 0.0, 0
    while st < shock - 0.05:
        on = (busy <= st < busy_end) or (peak <= st < end)
        if on:
            c = int(st // (2 * bar)) % 4; tones = chords[c][1]
            f = tones[i % 3] * (4 if (i // 3) % 2 == 0 else 2)
            tt = np.arange(an) / SR; x = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt)) * aenv * 0.05
            s = int(st * SR); e = min(N, s + an); pan = (-0.4, 0.4)[i % 2]
            L[s:e] += x[:e - s] * (1 - max(0, pan)); R[s:e] += x[:e - s] * (1 + min(0, pan))
        st += BEAT / 4; i += 1

    # riser into the end card (noise swell), cut dead at the snap
    rs = int((shock - 1.6) * SR); re = int(shock * SR)
    if rs < re:
        n = re - rs; k = np.linspace(0, 1, n)
        noise = rng.standard_normal(n); noise = noise - np.convolve(noise, np.ones(30) / 30, 'same')
        sw = noise * k ** 2.5 * 0.12 + np.sin(2 * np.pi * np.cumsum(200 * (8 ** k)) / SR) * k ** 3 * 0.05
        L[rs:re] += sw; R[rs:re] += sw
    return np.stack([L, R], 1)
