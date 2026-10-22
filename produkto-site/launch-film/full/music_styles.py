"""Three alternative scores for the launch film (A is music.py). Same contract as music.score:
score_X(SHOTS, DUR, SR, shock) -> (N, 2) float array. All synthesised, no licence to clear.
  B  Cold techno  - D minor, 132 BPM, four-on-the-floor, off-beat open hats, acid bassline
  C  Cinematic    - C minor, 90 BPM half-time, braams on section changes, toms, ticking clock
  D  Dark synth   - E minor, 118 BPM, rolling 16th octave bass, claps on 2 and 4, gated pad
"""
import numpy as np


def _saw(freq, t, bright, nh=16):
    out = np.zeros_like(t); hmax = 2 + bright * (nh - 2)
    for n in range(1, nh + 1):
        out += np.clip(hmax - n + 1, 0, 1) / n * np.sin(2 * np.pi * freq * n * t)
    return out


class Mix:
    def __init__(self, DUR, SR):
        self.SR = SR; self.N = int(DUR * SR); self.t = np.arange(self.N) / SR
        self.L = np.zeros(self.N); self.R = np.zeros(self.N); self.rng = np.random.default_rng(11)
    def add(self, x, at, gain=1.0, pan=0.0):
        s = int(at * self.SR)
        if s >= self.N or s + len(x) <= 0: return
        a = max(0, -s); s = max(0, s); e = min(self.N, s + len(x) - a); x = x[a:a + e - s] * gain
        self.L[s:e] += x * (1 - max(0, pan)); self.R[s:e] += x * (1 + min(0, pan))
    def bed(self, x, pan=0.0):  # full-length layer
        self.L += x * (1 - max(0, pan)); self.R += x * (1 + min(0, pan))
    def out(self): return np.stack([self.L, self.R], 1)
    # instruments
    def kick(self, f0=95, f1=42, dec=9, length=0.32):
        n = int(length * self.SR); tt = np.arange(n) / self.SR
        f = f1 + (f0 - f1) * np.exp(-tt * 30); return np.tanh(np.sin(2 * np.pi * np.cumsum(f) / self.SR) * np.exp(-tt * dec) * 1.4)
    def hat(self, length=0.03, dec=0.004):
        n = int(length * self.SR); x = np.diff(np.concatenate([[0], self.rng.standard_normal(n)]))
        return x * np.exp(-np.arange(n) / (dec * self.SR))
    def clap(self):
        n = int(0.18 * self.SR); x = np.diff(np.concatenate([[0], self.rng.standard_normal(n)]))
        env = np.zeros(n)
        for d in (0, .008, .016): s = int(d * self.SR); env[s:] += np.exp(-np.arange(n - s) / (0.01 * self.SR)) * .5
        env += np.exp(-np.arange(n) / (0.05 * self.SR)) * .6; return x * env
    def tom(self, f=70):
        n = int(0.6 * self.SR); tt = np.arange(n) / self.SR; ff = f * (1 + .6 * np.exp(-tt * 20))
        return np.tanh(np.sin(2 * np.pi * np.cumsum(ff) / self.SR) * np.exp(-tt * 5) * 1.8 + self.rng.standard_normal(n) * np.exp(-tt * 40) * .3)
    def braam(self, root, length=2.2):  # low brass-like stack, swells then decays
        n = int(length * self.SR); tt = np.arange(n) / self.SR; env = np.clip(tt / .06, 0, 1) * np.exp(-tt * 1.4)
        br = np.clip(1 - tt / length, 0, 1) * .9 + .1; out = np.zeros(n)
        for m, g in ((1, 1), (1.5, .5), (2, .45), (1.002, .8), (0.5, .7)):
            out += _saw(root * m, tt, br, 12) * g
        return np.tanh(out * env * .5)
    def pluck(self, f, length=0.14, bright=0.6):
        n = int(length * self.SR); tt = np.arange(n) / self.SR
        return _saw(f, tt, np.full(n, bright), 10) * np.exp(-tt * 22)
    def riser(self, start, stop, gain=.12):
        rs = int(start * self.SR); re = int(stop * self.SR)
        if rs >= re: return
        n = re - rs; k = np.linspace(0, 1, n); nz = self.rng.standard_normal(n); nz = nz - np.convolve(nz, np.ones(30) / 30, 'same')
        sw = nz * k ** 2.5 * gain + np.sin(2 * np.pi * np.cumsum(200 * (8 ** k)) / self.SR) * k ** 3 * gain * .4
        self.L[rs:re] += sw; self.R[rs:re] += sw


def _times(SHOTS):
    at = lambda s, d=0.0: SHOTS[s][0] + d * SHOTS[s][2]
    return dict(drive=at('vis-dark'), qs=at('quad-type'), scan=at('scan'), llm=at('llm-text'), agents=at('agents'),
                articles=at('articles'), url=at('url'), care=at('care'), at=at)


def score_B(SHOTS, DUR, SR, shock):   # cold techno
    m = Mix(DUR, SR); T = _times(SHOTS); B = 60 / 132; t = m.t
    roots = [73.42, 73.42, 58.27, 65.41]          # D, D, Bb, C (bars)
    k = m.kick(100, 45, 10); h = m.hat(0.025, 0.003); oh = m.hat(0.12, 0.03)
    step = 0.0; i = 0
    while step < shock - .05:
        bar = int(step // (4 * B)); root = roots[bar % 4]
        if step >= T['drive'] or (step > .4 and i % 8 == 0): m.add(k, step, .6 if step >= T['drive'] else .35)
        if step >= T['qs'] and i % 2 == 1: m.add(oh, step + B / 2 * 0, .07, .3)        # off-beat open hat
        if step >= T['llm']: m.add(h, step + B / 4, .05, -.5); m.add(h, step + 3 * B / 4, .05, .5)
        # acid bass: 16ths, accent pattern, filter opens over the film
        for s16 in range(4):
            tt0 = step + s16 * B / 4
            if tt0 < T['qs'] or tt0 >= shock: continue
            pat = [1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1][(i * 4 + s16) % 16]
            if not pat: continue
            n = int(B / 4 * .9 * SR); tt = np.arange(n) / SR
            br = min(1, .2 + .8 * (tt0 - T['qs']) / max(1, T['url'] - T['qs'])) * (0.5 + 0.5 * np.exp(-tt * 18))
            f = root * (2 if (i * 4 + s16) % 7 == 3 else 1)
            m.add(np.tanh(_saw(f, tt, br, 14) * np.exp(-tt * 9) * 1.5), tt0, .16)
        step += B; i += 1
    # dark drone pad under it all
    pad = (np.sin(2 * np.pi * 73.42 * t) + .5 * np.sin(2 * np.pi * 110.0 * t + 1) + .3 * np.sin(2 * np.pi * 146.83 * 1.003 * t)) * .05
    m.bed(pad * np.clip(t / 1.5, 0, 1) * (t < shock))
    m.riser(shock - 1.6, shock, .13)
    return m.out()


def score_C(SHOTS, DUR, SR, shock):   # cinematic half-time
    m = Mix(DUR, SR); T = _times(SHOTS); B = 60 / 90; t = m.t
    # braams on the big section changes
    for key, root in (('drive', 32.70), ('llm', 38.89), ('agents', 32.70), ('articles', 29.14), ('care', 32.70)):
        if T[key] < shock: m.add(m.braam(root), T[key], .55)
    m.add(m.braam(32.70, 1.6), 0.15, .35)
    # ticking clock: 8ths throughout, brighter later
    st = .3
    while st < shock - .05:
        m.add(m.hat(.02, .0025), st, .06 if st < T['drive'] else .09, (-.4, .4)[int(st / (B / 2)) % 2]); st += B / 2
    # toms: heartbeat before the drive, a rolling pattern after
    st = 0.0; i = 0
    while st < shock - .05:
        if st < T['drive']:
            if i % 4 == 0 and st > .3: m.add(m.tom(55), st, .45); m.add(m.tom(55), st + .18, .3)
        else:
            for off, f, g in ((0, 60, .55), (.5, 75, .35), (.75, 75, .3), (1.5, 50, .5)):
                if (i % 2 == 0) and st + off * B < shock: m.add(m.tom(f), st + off * B, g, (-.3, .3)[int(off * 4) % 2])
        st += B; i += 1
    # low string-like drone, C minor
    for f, g in ((65.41, .05), (77.78, .035), (98.0, .03)):
        m.bed(_saw(f, t, np.full(m.N, .25), 8) * g * np.clip(t / 2, 0, 1) * (t < shock) * (1 + .3 * np.sin(2 * np.pi * .13 * t)))
    m.riser(shock - 1.8, shock, .15)
    return m.out()


def score_D(SHOTS, DUR, SR, shock):   # dark synth
    m = Mix(DUR, SR); T = _times(SHOTS); B = 60 / 118; t = m.t
    roots = [41.20, 32.70, 36.71, 30.87]          # E, C, D, B (two bars each)
    chords = [[164.81, 196.0, 246.94], [130.81, 164.81, 196.0], [146.83, 185.0, 220.0], [123.47, 155.56, 185.0]]
    k = m.kick(90, 45, 8); cl = m.clap(); h = m.hat()
    st = 0.0; i = 0
    while st < shock - .05:
        c = int(st // (8 * B)) % 4
        if st >= T['drive'] or (i % 2 == 0 and st > .4): m.add(k, st, .55 if st >= T['drive'] else .3)
        if st >= T['drive'] and i % 2 == 1: m.add(cl, st, .22)
        if st >= T['llm']: [m.add(h, st + j * B / 4, .045, (-.5, .5)[j % 2]) for j in range(4)]
        # rolling octave bass in 16ths
        for j in range(4):
            tt0 = st + j * B / 4
            if tt0 < .3 or tt0 >= shock: continue
            f = roots[c] * (2 if j % 2 else 1)
            n = int(B / 4 * .85 * SR); tt = np.arange(n) / SR
            m.add(np.tanh(_saw(f, tt, np.full(n, .35), 10) * np.exp(-tt * 7) * 1.3), tt0, .13 if tt0 < T['drive'] else .18)
        # gated pad on 16ths from the drive
        if st >= T['qs']:
            for j in range(4):
                tt0 = st + j * B / 4; n = int(B / 4 * .6 * SR); tt = np.arange(n) / SR
                pad = sum(_saw(f, tt, np.full(n, .5), 8) for f in chords[c]) * np.exp(-tt * 10)
                m.add(pad, tt0, .025 if st < T['drive'] else .04, (-.3, .3)[j % 2])
        # lead plucks under the agents and articles
        if T['agents'] <= st < T['url']:
            for j in range(4):
                m.add(m.pluck(chords[c][(i + j) % 3] * 2), st + j * B / 4, .05, (-.5, .5)[j % 2])
        st += B; i += 1
    m.riser(shock - 1.6, shock, .13)
    return m.out()
