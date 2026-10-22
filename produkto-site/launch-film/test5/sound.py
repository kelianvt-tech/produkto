"""Synthesised sound bed for the 5 s test, modelled on the Algosoup film:
a ~45 Hz sub drone that swells in waves, fine digital ticks, a riser into a low boom on each big cut.
No samples, no music licence. Writes mix.wav and muxes it onto silent.mp4 -> produkto-test-5s.mp4.
"""
import os, subprocess, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
FF = os.path.expanduser('~/Library/Python/3.9/lib/python/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1')
SR, DUR = 44100, 5.0
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
env = np.clip(t / 0.25, 0, 1) * np.clip((DUR - t) / 0.9, 0, 1)
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

add(boom(), 0.08, 0.9)                      # logo in
add(glitch(), 0.08, 0.35, -0.3)
add(riser(0.55, 300, 2400), 0.40, 0.35)     # into the halftone
add(glitch(0.05), 0.95, 0.4, 0.4)
add(boom(0.7, 90, 40, 0.8), 0.95, 0.35)
add(glitch(0.05), 1.35, 0.4, -0.4)          # terminal cut
add(boom(0.5, 80, 40, 0.6), 1.35, 0.3)
for i in range(len('produkto scan')):        # typing, matches 40 chars/s in film.html
    add(tick(0.9), 1.38 + i / 40 + rng.uniform(-.004, .004), 0.35, rng.uniform(-.5, .5))
for tt in [1.74, 1.84, 1.96, 2.08, 2.16, 2.26, 2.34, 2.42, 2.50]:   # each log line
    for k in range(3): add(tick(1.2), tt + k * 0.012, 0.3, rng.uniform(-.7, .7))
for k in range(40):                          # machine chatter under the scan
    add(tick(0.6), 1.9 + k * 0.025 + rng.uniform(0, .01), 0.12, rng.uniform(-1, 1))
add(riser(0.75), 2.15, 0.6)                  # riser into "Visibility"
add(boom(2.0, 120, 30, 0.9), 2.90, 1.15)     # the big hit
add(glitch(0.08), 2.90, 0.5, 0.2)
add(boom(1.0, 70, 35, 0.7), 3.60, 0.55)      # flip to dark
add(glitch(0.06), 3.60, 0.45, -0.2)
add(boom(1.2, 60, 30, 0.3), 4.55, 0.5)       # url
for k in range(3): add(tick(1.0), 4.55 + 0.385 * k, 0.25)  # cursor blinks

mix = np.stack([L, R], 1)
mix /= max(1e-9, np.abs(mix).max() / 0.95)
raw = f'{HERE}/mix.f32'; mix.astype(np.float32).tofile(raw)
subprocess.run([FF, '-v', 'error', '-y', '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', raw,
                '-af', 'loudnorm=I=-14:TP=-1:LRA=11', '-ar', str(SR), f'{HERE}/mix.wav'], check=True)
os.remove(raw)
subprocess.run([FF, '-v', 'error', '-y', '-i', f'{HERE}/silent.mp4', '-i', f'{HERE}/mix.wav', '-c:v', 'copy',
                '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-shortest', f'{HERE}/produkto-test-5s.mp4'], check=True)
print('produkto-test-5s.mp4')
