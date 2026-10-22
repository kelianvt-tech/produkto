"""Synthesised sound bed for the launch film (timings read from shots.json, written by render.py), modelled on the Algosoup film:
a ~45 Hz sub drone that swells in waves, fine digital ticks, a riser into a low boom on each big cut.
No samples, no music licence. Writes mix.wav and muxes it onto silent.mp4 -> produkto-test-4-5s.mp4.
"""
import os, sys, subprocess, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
FF = os.path.expanduser('~/Library/Python/3.9/lib/python/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1')
import json
_meta = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots.json")))
SHOTS = {r[0]: (r[4], r[2] * r[3], r[3]) for r in _meta["shots"]}   # real start, real length, stretch
SR = 44100
DUR = max(s + l for s, l, _ in SHOTS.values())
N = int(SR * DUR); t = np.arange(N) / SR
rng = np.random.default_rng(7)
L = np.zeros(N); R = np.zeros(N)

def lowpass(x, a):  # one-pole, a in (0,1): smaller = darker
    y = np.empty_like(x); acc = 0.0
    for i, v in enumerate(x): acc += a * (v - acc); y[i] = acc
    return y
def add(sig, at, gain=1.0, pan=0.0):
    s = int(at * SR); e = min(N, s + len(sig)); seg = sig[:e - s] * gain
    L[s:e] += seg * (1 - max(0, pan)); R[s:e] += seg * (1 + min(0, pan))

# 1. sub drone: 45 Hz + a little 90 Hz, slow swell, dark rumble noise on top
swell = 0.55 + 0.45 * np.sin(2 * np.pi * t / 3.4 - 1.2) ** 2
drone = (np.sin(2 * np.pi * 45 * t) + 0.25 * np.sin(2 * np.pi * 90.4 * t + 1)) * swell
rumble = lowpass(rng.standard_normal(N), 0.004) * 6 * swell
env = np.clip(t / 0.25, 0, 1) * np.clip((DUR - t) / 1.2, 0, 1)
add((drone * 0.30 + rumble * 0.12) * env, 0)

# 2. boom: pitch drop 110 -> 32 Hz with a short noise crack
def boom(len_s=1.6, f0=110, f1=32, crack=0.5):
    n = int(len_s * SR); tt = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-tt * 9); ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-tt * 2.6)
    cr = rng.standard_normal(n) * np.exp(-tt * 60) * crack
    return np.tanh((body + lowpass(cr, 0.25)) * 1.6)

# 3. riser: noise + sine sweeping up, cut dead at the hit
def riser(len_s, f0=180, f1=1700):
    n = int(len_s * SR); tt = np.arange(n) / SR; k = tt / len_s
    f = f0 * (f1 / f0) ** k; ph = 2 * np.pi * np.cumsum(f) / SR
    hiss = rng.standard_normal(n); hiss = hiss - lowpass(hiss, 0.2 + 0.6 * 0)
    return (np.sin(ph) * 0.35 + hiss * 0.25) * k ** 2.2

# 4. ticks: 2-4 ms bright clicks
def tick(bright=1.0):
    n = int(0.004 * SR); x = rng.standard_normal(n) * np.exp(-np.arange(n) / (0.0007 * SR))
    return (x - lowpass(x, 0.3)) * bright

# 5. glitch: a short burst of bit-crushed noise for the slice-offset frames
def glitch(len_s=0.07):
    n = int(len_s * SR); x = np.sign(np.sin(2 * np.pi * rng.uniform(300, 900) * np.arange(n) / SR)) * 0.4
    x *= (rng.random(n // 200 + 1).repeat(200)[:n] > 0.4); return x * np.exp(-np.arange(n) / (0.03 * SR))

def at(shot, dt=0.0): return SHOTS[shot][0] + dt * SHOTS[shot][2]   # dt is in film time, stretched like the picture
def chirp(f0=1400, f1=2200, len_s=0.06):  # an agent landing
    n = int(len_s * SR); tt = np.arange(n) / SR; f = f0 + (f1 - f0) * tt / len_s
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 45)

add(boom(), at('logo'), 0.9); add(glitch(), at('logo'), 0.35, -0.3)          # 1 logo
add(riser(0.5, 300, 2400), at('question', -0.5), 0.3)
add(glitch(0.05), at('question'), 0.4); add(boom(0.6, 85, 40, 0.6), at('question'), 0.35)   # 2 question
q = 'What are the best dog leashes for my dog golden retriever?'
for i in range(0, len(q), 2): add(tick(0.8), at('question', 0.25 + i / 48 + rng.uniform(-.004, .004)), 0.28, rng.uniform(-.5, .5))
add(riser(0.5, 250, 2600), at('answer', -0.5), 0.45)                          # whip to the answer
add(tick(1.4), at('answer', -0.04), 0.5)                                      # send
add(boom(1.0, 105, 36, 0.8), at('answer'), 0.8); add(glitch(0.05), at('answer'), 0.35)   # 3 the answer
for i in range(5): add(tick(1.2), at('answer', 0.12 + i * 0.09), 0.4, (-.4, .4)[i % 2])
def buzz(len_s=0.12):  # low error buzz for each 'not in this answer'
    n = int(len_s * SR); tt = np.arange(n) / SR
    return np.sign(np.sin(2 * np.pi * 110 * tt)) * 0.5 * np.exp(-tt * 18) + np.sin(2 * np.pi * 55 * tt) * np.exp(-tt * 10)
add(riser(0.3, 400, 2400), at('quad-type', -0.3), 0.3)
add(boom(0.9, 100, 36, 0.8), at('quad-type'), 0.7); add(glitch(0.05), at('quad-type'), 0.35)      # 4 pull out to four screens
for i, qq in enumerate(['What are the best running shoes under $100?', 'What is the best moisturizer for dry, sensitive skin?',
                        'Which magnesium glycinate supplement should I buy for better sleep?']):
    for k in range(0, len(qq), 3): add(tick(0.7), at('quad-type', 0.22 + i * 0.08 + k / 70), 0.14, (-.8, .8, 0)[i])
add(boom(0.8, 95, 38, 0.7), at('quad-answer'), 0.6); add(glitch(0.05), at('quad-answer'), 0.3)     # 5 all four answer
for i in range(1, 4):
    for r in range(5): add(tick(1.1), at('quad-answer', 0.06 + i * 0.05 + r * 0.08), 0.2, (-.8, .8, 0, .5)[i])
for i in range(4): add(buzz(), at('quad-miss', 0.05 + i * 0.09), 0.45, (-.6, .6, -.6, .6)[i])       # 6 not in any of them
add(riser(0.35, 300, 2000), at('quad-miss', 0.15), 0.35)
add(boom(1.8, 120, 30, 0.9), at('quad-miss', 0.5), 1.1); add(glitch(0.07), at('quad-miss', 0.5), 0.45)
add(glitch(0.05), at('scan'), 0.4, -0.4); add(boom(0.6, 85, 40, 0.6), at('scan'), 0.35)      # 4 scan
for i in range(len('produkto scan')): add(tick(0.9), at('scan', 0.03 + i / 42 + rng.uniform(-.004, .004)), 0.35, rng.uniform(-.5, .5))
for t0 in [1.14, 1.22, 1.32, 1.42, 1.52]:
    for k in range(3): add(tick(1.2), at('scan', t0 - 0.95 + k * 0.012), 0.3, rng.uniform(-.7, .7))
add(glitch(0.05), at('loader'), 0.4, 0.3); add(boom(0.8, 90, 38, 0.6), at('loader'), 0.45)    # 5 filling P
for k in range(24): add(tick(0.7), at('loader', 0.03 + k * 0.022 + rng.uniform(0, .006)), 0.14, rng.uniform(-1, 1))
add(riser(0.65), at('vis-dark', -0.65), 0.6)
add(boom(2.0, 120, 30, 0.9), at('vis-dark'), 1.15); add(glitch(0.08), at('vis-dark'), 0.5, 0.2)   # 6 Your AI visibility
add(tick(1.4), at('vis-dark', 0.45), 0.6)                                        # the switch click
add(boom(1.0, 100, 34, 0.8), at('vis-light'), 0.75); add(glitch(0.05), at('vis-light'), 0.35, 0.3)  # 7 light mode
add(boom(0.7, 80, 40, 0.5), at('daily'), 0.45); add(glitch(0.04), at('daily'), 0.3)                # 8 measured every day
add(riser(0.45, 300, 2400), at('llm-text', -0.45), 0.4)
add(boom(1.4, 115, 32, 0.9), at('llm-text'), 0.95); add(glitch(0.06), at('llm-text'), 0.4)         # 9 across LLMs
for k in range(6):                                                               # 10 six engine logos
    add(boom(0.4, 140, 45, 1.0), at('llm-logos', k * 0.17), 0.55); add(glitch(0.06), at('llm-logos', k * 0.17), 0.45, (-.6, .6)[k % 2])
add(boom(1.2, 110, 32, 0.8), at('llm-logos', 1.02), 0.8)                         # all of them in a row
for k in range(6): add(tick(1.2), at('llm-logos', 1.02 + k * 0.025), 0.25, -0.6 + k * 0.24)
add(boom(1.0, 100, 34, 0.8), at('agents'), 0.7); add(glitch(0.05), at('agents'), 0.35)             # 11 agents
for n in range(56):   # same spawn times as AG in film.html: launch blip, then a chirp on landing
    t0 = 0.08 + n * 0.014
    add(chirp(1500 + (n % 7) * 120, 2300 + (n % 5) * 150), at('agents', t0 + 0.38), 0.07, ((n * 37) % 100) / 50 - 1)
for k in range(30): add(tick(0.6), at('agents', 0.1 + k * 0.035), 0.1, rng.uniform(-1, 1))
add(boom(1.2, 110, 32, 0.9), at('remediation'), 0.85); add(glitch(0.05), at('remediation'), 0.35)  # 12 Remediation.
add(boom(0.8, 90, 38, 0.6), at('revamp'), 0.6); add(glitch(0.05), at('revamp'), 0.3)              # 13 the agent rebuilds a page
add(chirp(1200, 2400, 0.12), at('revamp', 0.3), 0.18)                            # agent arrives
for st in [.50, .64, .78, .92, 1.00, 1.18, 1.34]:
    add(boom(0.25, 160, 70, 0.4), at('revamp', st), 0.25)
    for k in range(5): add(tick(0.9), at('revamp', st + 0.02 + k * 0.022), 0.18, rng.uniform(-.6, .6))
add(riser(0.45, 300, 2200), at('revamp', 1.35), 0.4)
add(boom(1.6, 120, 30, 0.9), at('revamp', 1.8), 1.0)                             # ready to be cited
add(chirp(880, 880, 0.5), at('revamp', 1.8), 0.12); add(chirp(1320, 1320, 0.5), at('revamp', 1.86), 0.1)
add(boom(1.1, 100, 34, 0.8), at('articles'), 0.75); add(glitch(0.05), at('articles'), 0.3)        # 14 an article every month
for i in range(5):
    t0 = 0.35 + i * 0.32
    add(chirp(1300, 2100, 0.07), at('articles', t0 - 0.08), 0.08, -0.7 + i * 0.35)     # agent hop
    add(boom(0.3, 130, 60, 0.4), at('articles', t0), 0.3, -0.7 + i * 0.35)             # card lands
    for k in range(6): add(tick(0.8), at('articles', t0 + 0.04 + k * 0.027), 0.15, -0.7 + i * 0.35)
    add(chirp(990, 990, 0.25), at('articles', t0 + 0.26), 0.07, -0.7 + i * 0.35)       # published
add(riser(0.4, 200, 1800), at('articles', 1.6), 0.4)
add(boom(1.6, 115, 30, 0.9), at('articles', 1.95), 1.0); add(glitch(0.06), at('articles', 1.95), 0.4)   # pull back to the whole year
_rr = np.random.default_rng(31)
for n in range(67):                                                               # the wall of articles filling in
    tt = 2.10 + _rr.random() * 1.5
    add(tick(1.0), at('articles', tt), 0.12, _rr.uniform(-1, 1)); add(chirp(1500 + _rr.random() * 900, 2400, 0.04), at('articles', tt + 0.14), 0.035, _rr.uniform(-1, 1))
add(riser(0.4, 400, 2600), at('care', -0.4), 0.35)
add(boom(1.6, 110, 30, 0.9), at('care'), 1.0); add(glitch(0.06), at('care'), 0.45, -0.2)          # 13 taken care of
add(boom(1.4, 60, 30, 0.3), at('url'), 0.55)                                     # 14 url
for i in range(len('getprodukto.com')): add(tick(0.9), at('url', 0.08 + i / 24), 0.3, rng.uniform(-.4, .4))   # typed out
add(tick(0.7), at('url', 0.08 + 15 / 24 + 0.385), 0.15)                                                            # one blink
SH = 0.08 + 15 / 24 + 0.45                                                                                         # the snap to white
add(boom(2.2, 140, 28, 1.0), at('url', SH), 1.3); add(glitch(0.09), at('url', SH), 0.6); add(tick(1.6), at('url', SH), 0.7)

mix = np.stack([L, R], 1)
mix /= max(1e-9, np.abs(mix).max() / 0.95)
if os.environ.get('MUSIC', '1') == '1':                 # the score sits under the effects
    style = os.environ.get('MUSIC_STYLE', 'D')         # D (dark synth) chosen 2026-10-20; A = music.py; B, C, D = music_styles.py
    if style == 'A':
        import music; m = music.score(SHOTS, DUR, SR, at('url', SH))
    else:
        import music_styles; m = getattr(music_styles, 'score_' + style)(SHOTS, DUR, SR, at('url', SH))
    m /= max(1e-9, np.abs(m).max() / 0.55)
    mix = mix + m
    mix /= max(1e-9, np.abs(mix).max() / 0.95)
raw = f'{HERE}/mix.f32'; mix.astype(np.float32).tofile(raw)
subprocess.run([FF, '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', raw,
                '-af', 'loudnorm=I=-14:TP=-1:LRA=11', '-ar', str(SR), f'{HERE}/mix.wav'], check=True)
os.remove(raw)
subprocess.run([FF, '-v', 'error', '-y', '-i', f'{HERE}/silent.mp4', '-i', f'{HERE}/mix.wav', '-c:v', 'copy',
                '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-shortest', f'{HERE}/' + (sys.argv[1] if len(sys.argv) > 1 else 'produkto-launch-v14.mp4')], check=True)
print('produkto-launch-v14.mp4')
