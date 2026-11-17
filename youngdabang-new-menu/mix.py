# score (synthesized: kalimba, plucked guitar, glockenspiel, bass) + foley from events.json → out/mix.wav (48 kHz stereo)
# usage: "$LIB/.venv/bin/python" mix.py
import json, os, numpy as np, soundfile as sf
from scipy.signal import butter, sosfilt, lfilter, fftconvolve
HERE = os.path.dirname(os.path.abspath(__file__))
EV = json.load(open(os.path.join(HERE, 'events.json')))
SR = 48000; DUR = EV['dur']; N = int(DUR * SR)
rng = np.random.default_rng(7)
BPM = 96; BEAT = 60 / BPM; BAR = 4 * BEAT
HUSH = next(e['t'] for e in EV['ev'] if e['type'] == 'hush')

def bp(x, lo, hi, o=2): return sosfilt(butter(o, [lo, hi], 'band', fs=SR, output='sos'), x)
def lp(x, f, o=2): return sosfilt(butter(o, f, 'low', fs=SR, output='sos'), x)
def hp(x, f, o=2): return sosfilt(butter(o, f, 'high', fs=SR, output='sos'), x)
def noise(n): return rng.standard_normal(n)
def pink(n):
    w = np.fft.rfft(noise(n)); f = np.arange(len(w)); f[0] = 1
    return np.fft.irfft(w / np.sqrt(f), n) * 20
def norm(x, p=1.0): return x / (np.abs(x).max() + 1e-9) * p
def st(x, pan=0.0):
    return np.stack([x * np.cos((pan + 1) * np.pi / 4), x * np.sin((pan + 1) * np.pi / 4)], 1) * 1.414
def env(n, a, r):
    t = np.arange(n) / SR; return np.minimum(1, t / max(a, 1e-4)) * np.exp(-np.maximum(0, t - a) / max(r, 1e-4))
def put(buf, t, x):
    i = int(t * SR); j = min(len(buf), i + len(x))
    if 0 <= i < j: buf[i:j] += x[:j - i]
def hz(m): return 440 * 2 ** ((m - 69) / 12)
IRn = int(1.6 * SR); IR = np.stack([noise(IRn), noise(IRn)], 1) * np.exp(-np.arange(IRn) / SR * 3.6)[:, None]
IR = np.stack([lp(IR[:, 0], 5000), lp(IR[:, 1], 5000)], 1); IR /= np.sqrt((IR ** 2).sum(0))
def verb(x2, wet=.25):
    y = np.stack([fftconvolve(x2[:, 0], IR[:, 0])[:len(x2)], fftconvolve(x2[:, 1], IR[:, 1])[:len(x2)]], 1)
    return x2 * (1 - wet) + y * wet

# ---------------- instruments ----------------
def kalimba(m, d=1.6, v=.6):
    n = int(d * SR); t = np.arange(n) / SR; f = hz(m)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t * 2.6) + .28 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t * 14) + .12 * np.sin(2 * np.pi * f * 3.0 * t) * np.exp(-t * 8)
    x += hp(noise(n), 2000) * env(n, .0005, .006) * .15
    return x * env(n, .002, 9) * v
def glock(m, d=1.8, v=.4):
    n = int(d * SR); t = np.arange(n) / SR; f = hz(m)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t * 2.0) + .35 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 6) + .15 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t * 12)
    return x * env(n, .001, 9) * v
def pluck(m, d=1.4, v=.5, bright=.5, decay=.996):   # Karplus–Strong as a feedback comb (lfilter)
    n = int(d * SR); f = hz(m); P = int(round(SR / f))
    exc = np.zeros(n); burst = lp(noise(P), 1500 + 6000 * bright); exc[:P] = burst
    a = np.zeros(P + 2); a[0] = 1; a[P] = -decay * .5; a[P + 1] = -decay * .5
    y = lfilter([1], a, exc)
    y = lp(y, 5500) * env(n, .001, 9)
    y[-int(.05 * SR):] *= np.linspace(1, 0, int(.05 * SR))
    return norm(y, v)
def pad(ms, d, v=.06):
    n = int(d * SR); t = np.arange(n) / SR; x = np.zeros(n)
    for m in ms:
        for det in (-.004, .004): x += np.sin(2 * np.pi * hz(m) * (1 + det) * t) + .3 * np.sin(2 * np.pi * hz(m) * 2 * (1 + det) * t)
    sw = np.minimum(1, t / .8) * np.minimum(1, (d - t) / .8)
    return lp(x, 1800) * sw * v / len(ms)

# ---------------- score ----------------
CH = {'F': [53, 57, 60, 65], 'Am': [57, 60, 64, 69], 'Bb': [58, 62, 65, 70], 'C': [55, 60, 64, 67], 'Dm': [50, 57, 62, 65]}
ROOT = {'F': 41, 'Am': 45, 'Bb': 46, 'C': 48, 'Dm': 50}
PROG = ['F', 'Am', 'Bb', 'C', 'F', 'Am', 'Bb', 'C', 'Dm', 'Bb', 'C', 'F']
mus = np.zeros((N + SR * 3, 2))
def m_put(t, x, pan=0.0):
    if HUSH - .02 < t < 25.0 - .01: return          # the brush is lifted: no music in the hush
    put(mus, t, st(x, pan))
ARP = [0, 1, 2, 3, 2, 1, 2, 3]
MEL = {  # kalimba motif per bar: (beat, scale step over chord top)
    1: [(0, 72), (1.5, 74), (3, 72)], 2: [(0, 72), (2, 69)], 3: [(0, 74), (1.5, 72), (3, 70)], 4: [(0, 72), (2, 67)],
    5: [(0, 77), (1, 76), (1.5, 74), (3, 72)], 6: [(0, 76), (2, 72)], 7: [(0, 74), (1, 72), (1.5, 74), (3, 77)], 8: [(0, 79), (2, 76)],
    9: [(0, 77), (1.5, 74), (3, 72)], 10: [(0, 79), (1, 77), (2, 74)],
}
for b, c in enumerate(PROG):
    t0 = b * BAR; ch = CH[c]
    if b == 0:
        m_put(.3, kalimba(72, 2.0, .45), -.2); m_put(1.25, kalimba(77, 2.0, .4), .2)
        continue
    if b == 11:   # final bar: the full chord rings on the seal
        for k, m in enumerate(ch + [ch[0] + 12]): m_put(t0 + k * .045, pluck(m, 2.6, .42, .45, .998), -.3 + k * .15)
        m_put(t0, kalimba(77, 2.6, .5)); m_put(t0, glock(84, 2.4, .32), .3); m_put(t0, pluck(ROOT[c] - 12, 2.6, .5, .2, .998))
        put(mus, t0 - .3, st(pad(ch, 2.9, .07)))
        continue
    dense = 1 if b < 4 else 2
    for k in range(8 if dense == 2 or b >= 2 else 4):
        step = BEAT / 2 if (dense == 2 or b >= 2) else BEAT
        m = ch[ARP[k % 8]] + (12 if k in (3, 7) else 0)
        m_put(t0 + k * step, pluck(m, 1.2, .34 if k % 2 else .42, .4 + .1 * (k == 0)), -.35 + .1 * (k % 4))
    if b >= 4:   # bass on 1 and 3
        m_put(t0, pluck(ROOT[c] - 12, 1.3, .55, .2, .997)); m_put(t0 + 2 * BEAT, pluck(ROOT[c] - 12, 1.1, .42, .2, .997))
    for bt, m in MEL.get(b, []): m_put(t0 + bt * BEAT, kalimba(m, 1.6, .38), .15)
    if b in (7, 8, 9):   # glockenspiel counter-line in the fast section
        for bt, m in [(.5, 84), (2.5, 81)]: m_put(t0 + bt * BEAT, glock(m, 1.4, .18), .4)
    if b in (2, 3, 6, 7): put(mus, t0, st(pad(ch, BAR + .4, .05)))
mus = verb(mus[:N], .28)
# fade the music tail into the hush, so reverb doesn't spill into the silence
i0, i1 = int((HUSH - .05) * SR), int((HUSH + .45) * SR); g = np.ones(N); g[i0:i1] = np.linspace(1, 0, i1 - i0); g[i1:int(25.0 * SR) - 200] = 0; g[int(25.0 * SR) - 200:int(25.0 * SR)] = np.linspace(0, 1, 200)
mus *= g[:, None]

# ---------------- foley ----------------
sfx = np.zeros((N + SR * 3, 2))
def brush(d, g, pan0=-.5, pan1=.5):
    n = int(d * SR); p = np.arange(n) / n
    x = bp(noise(n), 1500, 7000) * (.6 + .4 * np.abs(np.sin(np.arange(n) / SR * 2 * np.pi * 9))) + bp(pink(n), 300, 1500) * .5
    y = norm(x * np.sin(np.pi * p) ** .8, .5) * g; pan = pan0 + (pan1 - pan0) * p
    return np.stack([y * np.cos((pan + 1) * np.pi / 4), y * np.sin((pan + 1) * np.pi / 4)], 1) * 1.414
def pencil(d, g=.22):
    n = int(d * SR); t = np.arange(n) / SR
    am = np.clip(np.sin(2 * np.pi * 7.5 * t + 3 * np.sin(2 * np.pi * 1.3 * t)), 0, 1) ** .6
    return st(norm(bp(noise(n), 2500, 8000) * am * np.minimum(1, (d - t) / .1), .5) * g, .3)
def drop(g=.5):
    n = int(.35 * SR); t = np.arange(n) / SR; f = 1300 * np.exp(-t * 9) + 380
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, .001, .06) + bp(noise(n), 800, 3000) * env(n, .001, .01) * .4
    return verb(st(norm(x, .6) * g), .35)
def swell(d, g, lo, hi, pan0=-.3, pan1=.3):
    n = int(d * SR); p = np.arange(n) / n
    y = norm(bp(pink(n), lo, hi) * np.sin(np.pi * p) ** 1.4, .5) * g; pan = pan0 + (pan1 - pan0) * p
    return np.stack([y * np.cos((pan + 1) * np.pi / 4), y * np.sin((pan + 1) * np.pi / 4)], 1) * 1.414
def stamp(g, f0=90):
    n = int(1.0 * SR); t = np.arange(n) / SR
    x = np.sin(2 * np.pi * np.cumsum(f0 * (1 + .5 * np.exp(-t * 30))) / SR) * np.exp(-t * 10) + lp(noise(n), 900) * env(n, .002, .04) * .6
    return verb(st(norm(x, .8) * g), .2)
def crunch(d=.7, g=.35):
    n = int(d * SR); x = np.zeros(n)
    for k in range(26):
        i = int(rng.uniform(0, .85) * n); L = int(rng.uniform(.004, .02) * SR); x[i:i + L] += hp(noise(L), 1800) * rng.uniform(.3, 1) * np.exp(-np.arange(L) / (L / 3))
    return st(norm(x, .7) * g, .1)
def sizzle(d, g=.12):
    n = int(d * SR); t = np.arange(n) / SR
    x = hp(noise(n), 3000) * (.5 + .5 * vn(n))
    for k in range(int(d * 40)):
        i = int(rng.uniform(0, n - 400)); x[i:i + 300] += hp(noise(300), 2500) * rng.uniform(.5, 2) * np.exp(-np.arange(300) / 60)
    e = np.minimum(1, t / 1.0) * np.minimum(1, (d - t) / 1.2)
    return st(norm(x * e, .5) * g, .35)
def vn(n):
    k = np.interp(np.arange(n), np.linspace(0, n, 40), rng.uniform(0, 1, 40)); return k

for e in EV['ev']:
    t, ty = e['t'], e['type']; d = e.get('d', 1.0); pan = {0: -.2, 1: 0, 2: .2}.get(e.get('i'), 0)
    if ty == 'pencil': put(sfx, t, pencil(d))
    elif ty == 'drop': put(sfx, t - .02, drop())
    elif ty == 'mist': put(sfx, t, swell(1.0, .18, 400, 3000, .6, -.6))
    elif ty == 'wash': put(sfx, t, swell(1.4, .22, 300, 2500, -.6, .6))
    elif ty == 'brush': put(sfx, t, brush(d, .32, pan - .5, pan + .5))
    elif ty == 'burst':
        for k in range(4): put(sfx, t + k * .07, brush(.6, .28, -.9 + k * .5, -.6 + k * .5))
    elif ty == 'stamp': put(sfx, t - .01, stamp(.5))
    elif ty == 'seal': put(sfx, t - .01, stamp(.75, 75)); put(sfx, t, st(glock(91, 1.6, .12), .4))
    elif ty == 'dolly': put(sfx, t, swell(1.8, .2, 200, 1800, -.7, .7))
    elif ty == 'pullback': put(sfx, t, swell(2.2, .26, 150, 2400, .5, -.5))
    elif ty == 'crunch': put(sfx, t, crunch())
    elif ty == 'sizzle': put(sfx, t, sizzle(d))
sfx = sfx[:N]
room = st(lp(pink(N), 900) * .004)

mix = mus * .9 + sfx + room
# hush: only paper and room — make sure nothing but foley/room sits there
pk = np.abs(mix).max(); mix = mix / pk * .89
out = os.path.join(HERE, 'out', 'mix.wav'); os.makedirs(os.path.dirname(out), exist_ok=True)
sf.write(out, mix.astype(np.float32), SR, subtype='FLOAT')
print('wrote', out, f'{DUR}s', 'peak', round(float(np.abs(mix).max()), 3))
