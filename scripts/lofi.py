"""Generate original lo-fi background music for Tree of Wishes reels.

Synthesizes a short, loop-friendly lo-fi track from scratch — Rhodes-ish keys, a
soft bass, an optional gentle beat, a sparse bell melody, plus vinyl hiss + tape
"wow". No samples, no licensing: the audio is original, so it's safe for
commercial Reels. Emits a small *sweep of candidates* (like wish-pixelize) so the
user can listen and pick the one that fits.

Pairs with scripts/video_anim.py (Task 3 / wish-reel): render the silent reel,
make 3 tracks here, let the user pick, then mux the chosen .wav into the mp4
(ffmpeg -i reel.mp4 -i track.wav -c:v copy -c:a aac -shortest reel.final.mp4).

Usage:
    .venv/bin/python scripts/lofi.py --mood tree --seconds 12 \
        --out-prefix instagram_videos/reel_NAME.track
    # -> reel_NAME.track_c1.wav  reel_NAME.track_c2.wav  reel_NAME.track_c3.wav

    # re-render just one candidate (e.g. tweak length):
    .venv/bin/python scripts/lofi.py --mood tree --candidate c2 --seconds 15 \
        --out-prefix instagram_videos/reel_NAME.track
"""
import argparse
import math
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SR = 44100

# Voicing registers (MIDI note numbers). A4 = 69 = 440 Hz.
CHORD_BASE = 48   # C3 — Rhodes chord roots sit here
BASS_BASE = 36    # C2 — sub/bass
MEL_BASE = 64     # E4 — bell melody floats above

QUAL = {"maj7": [0, 4, 7, 11], "min7": [0, 3, 7, 10],
        "dom7": [0, 4, 7, 10], "maj": [0, 4, 7], "min": [0, 3, 7]}

# 4-chord progressions (root offset from tonic, chord quality), per mood.
PROG = {
    "tree": [
        [(0, "maj7"), (9, "min7"), (5, "maj7"), (7, "dom7")],   # I  vi IV V
        [(2, "min7"), (7, "dom7"), (0, "maj7"), (9, "min7")],   # ii V  I  vi
        [(0, "maj7"), (5, "maj7"), (9, "min7"), (7, "dom7")],   # I  IV vi V
    ],
    "columbarium": [
        [(0, "min7"), (8, "maj7"), (3, "maj7"), (10, "dom7")],  # i  VI III VII
        [(0, "min7"), (5, "min7"), (10, "maj7"), (3, "maj7")],  # i  iv VII III
        [(0, "min7"), (8, "maj7"), (5, "min7"), (7, "min7")],   # i  VI iv  v
    ],
}
SCALE = {"tree": [0, 2, 4, 5, 7, 9, 11], "columbarium": [0, 2, 3, 5, 7, 8, 10]}

# Per-candidate character. drums/pad/mel + a friendly name shown to the user.
CANDIDATES = {
    "c1": dict(key=0,  drums=False, pad=0.16, mel=0.34, bpm_mul=1.00,
               name={"tree": "Warm Keys", "columbarium": "Quiet Keys"},
               blurb="mellow Rhodes + soft bass, no beat — calm"),
    "c2": dict(key=2,  drums=True,  pad=0.0,  mel=0.40, bpm_mul=1.02,
               name={"tree": "Chill Beat", "columbarium": "Faded Beat"},
               blurb="Rhodes + bass + a gentle lo-fi beat — classic study vibe"),
    "c3": dict(key=-3, drums=False, pad=0.26, mel=0.22, bpm_mul=0.96,
               name={"tree": "Dreamy Pad", "columbarium": "Distant Pad"},
               blurb="airy pad + sparse keys, no beat — ambient/floaty"),
}


def f_of(midi):
    return 440.0 * 2 ** ((midi - 69) / 12.0)


def lp_fir(x, taps=9):
    """Cheap warm low-pass via a short Hann FIR (no scipy needed)."""
    w = np.hanning(taps + 2)[1:-1]
    w /= w.sum()
    return np.convolve(x, w, mode="same")


# ── voices ───────────────────────────────────────────────────────────────────
def ep(freq, dur, amp=0.5, bright=1.0):
    """FM electric-piano (Rhodes-ish): bell-y attack, soft exponential decay."""
    n = int(dur * SR); t = np.arange(n) / SR
    env = np.exp(-t * 3.0) * (1 - np.exp(-t * 400))
    idx = 1.8 * bright * np.exp(-t * 5)                      # FM index decays
    car = np.sin(2 * np.pi * freq * t + idx * np.sin(2 * np.pi * freq * t))
    tone = car + 0.28 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t * 6)
    return amp * env * tone


def bass(freq, dur, amp=0.5):
    n = int(dur * SR); t = np.arange(n) / SR
    env = np.exp(-t * 1.7) * (1 - np.exp(-t * 200))
    tone = np.sin(2 * np.pi * freq * t) + 0.22 * np.sin(2 * np.pi * 2 * freq * t)
    return amp * env * tone


def bell(freq, dur, amp=0.24):
    n = int(dur * SR); t = np.arange(n) / SR
    env = np.exp(-t * 2.0) * (1 - np.exp(-t * 300))
    tone = np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t * 4)
    return amp * env * tone


def pad(freqs, dur, amp=0.2):
    n = int(dur * SR); t = np.arange(n) / SR
    env = np.clip(t / 0.6, 0, 1) * np.clip((dur - t) / 0.5, 0, 1)   # slow swell
    sig = np.zeros(n)
    for f in freqs:
        sig += np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.005 * t)
    return amp * env * lp_fir(sig, 13) / max(1, len(freqs))


def kick(amp=0.8):
    dur = 0.22; n = int(dur * SR); t = np.arange(n) / SR
    f = 110 * np.exp(-t * 30) + 45
    return amp * np.exp(-t * 9) * np.sin(2 * np.pi * np.cumsum(f) / SR)


def snare(rng, amp=0.4):
    dur = 0.18; n = int(dur * SR); t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 22)
    s = 0.7 * nz + 0.5 * body
    return amp * np.exp(-t * 16) * (s - lp_fir(s, 9))             # brightened


def hat(rng, amp=0.12, dur=0.05):
    n = int(dur * SR); t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    return amp * np.exp(-t * 60) * (nz - lp_fir(nz, 7))           # high-passed


# ── mixing ─────────────────────────────────────────────────────────────────────
def add(master, sig, start, gain=1.0, pan=0.0):
    """Place a mono voice into the stereo master at `start` seconds (constant-power pan)."""
    i0 = int(start * SR)
    if i0 >= len(master) or len(sig) == 0:
        return
    i1 = min(len(master), i0 + len(sig))
    sig = sig[:i1 - i0]
    ang = (pan + 1) * math.pi / 4
    master[i0:i1, 0] += sig * math.cos(ang) * gain
    master[i0:i1, 1] += sig * math.sin(ang) * gain


def tape_wow(stereo, depth_samp=5.0, rate=0.7):
    """Subtle pitch instability (wow/flutter) by reading at a wobbling index."""
    n = len(stereo); t = np.arange(n)
    idx = np.clip(t + depth_samp * np.sin(2 * np.pi * rate * t / SR), 0, n - 1)
    out = np.empty_like(stereo)
    out[:, 0] = np.interp(idx, t, stereo[:, 0])
    out[:, 1] = np.interp(idx, t, stereo[:, 1])
    return out


def voice_chord(roots_offsets, base_midi, key):
    """Compact chord voicing (MIDI freqs), keeping tones from getting too high."""
    freqs = []
    for off in roots_offsets:
        m = base_midi + key + off
        while m > base_midi + 16:      # fold the 7th/upper tones down an octave
            m -= 12
        freqs.append(f_of(m))
    return freqs


# ── one candidate ──────────────────────────────────────────────────────────────
def render(mood, cand, seconds, bpm):
    cfg = CANDIDATES[cand]
    rng = np.random.default_rng(abs(hash((mood, cand))) % (2 ** 32))
    key = cfg["key"]
    prog = PROG[mood][list(CANDIDATES).index(cand)]
    scale = SCALE[mood]

    beat = 60.0 / bpm
    bar = 4 * beat
    eighth = beat / 2
    swing = 0.16 * eighth
    nbars = int(math.ceil(seconds / bar)) + 1
    master = np.zeros((int(nbars * bar * SR) + SR, 2))

    soft = 0.8 if mood == "columbarium" else 1.0          # wistful = quieter
    for b in range(nbars):
        t0 = b * bar
        root_off, qual = prog[b % len(prog)]
        chord = [root_off + o for o in QUAL[qual]]
        cfreqs = voice_chord(chord, CHORD_BASE, key)

        # keys: a soft rolled chord at the downbeat, a lighter one on beat 3
        for hit, when in ((1.0, 0.0), (0.7, 2 * beat)):
            for j, f in enumerate(cfreqs):
                add(master, ep(f, bar * 0.95, amp=0.42 * hit * soft, bright=0.9 + 0.1 * j),
                    t0 + when + j * 0.028, pan=-0.12)

        # bass on beats 1 and 3
        broot = f_of(BASS_BASE + key + root_off)
        add(master, bass(broot, beat * 1.9, amp=0.5 * soft), t0)
        add(master, bass(broot, beat * 1.4, amp=0.32 * soft), t0 + 2 * beat)

        # pad: sustained chord under the bar
        if cfg["pad"] > 0:
            add(master, pad(cfreqs, bar, amp=cfg["pad"] * soft), t0, pan=0.0)

        # bell melody: sparse, swung, biased to chord tones
        if cfg["mel"] > 0:
            for s in range(8):
                if rng.random() > cfg["mel"]:
                    continue
                if rng.random() < 0.7:
                    deg = chord[rng.integers(len(chord))]
                else:
                    deg = scale[rng.integers(len(scale))]
                m = MEL_BASE + key + deg + 12 * rng.integers(0, 2)
                when = t0 + s * eighth + (swing if s % 2 else 0)
                add(master, bell(f_of(m), eighth * rng.uniform(1.4, 2.6),
                                 amp=0.2 * soft * rng.uniform(0.7, 1.0)),
                    when, pan=rng.uniform(0.05, 0.35))

        # gentle beat
        if cfg["drums"]:
            add(master, kick(0.8 * soft), t0)
            add(master, kick(0.55 * soft), t0 + 2 * beat + eighth)     # syncopated
            add(master, snare(rng, 0.38 * soft), t0 + beat)
            add(master, snare(rng, 0.38 * soft), t0 + 3 * beat)
            for s in range(8):                                          # swung hats
                add(master, hat(rng, 0.10 * soft), t0 + s * eighth + (swing if s % 2 else 0),
                    pan=rng.uniform(-0.3, 0.3))

    # vinyl texture: continuous hiss + sparse crackle pops
    N = len(master)
    hiss = lp_fir(rng.standard_normal(N), 5) * 0.012
    master[:, 0] += hiss; master[:, 1] += lp_fir(rng.standard_normal(N), 5) * 0.012
    for _ in range(int(seconds * 7)):
        i = rng.integers(0, N - 200)
        ln = int(rng.uniform(20, 120))
        tt = np.arange(ln) / SR
        pop = rng.uniform(0.05, 0.18) * np.exp(-tt * 120) * rng.standard_normal(ln)
        master[i:i + ln, 0] += pop; master[i:i + ln, 1] += pop * 0.8

    # trim to length, master-bus warmth, wow, fade, normalize, soft-clip
    master = master[:int(seconds * SR)]
    master[:, 0] = lp_fir(master[:, 0], 7); master[:, 1] = lp_fir(master[:, 1], 7)
    master = tape_wow(master, depth_samp=5.0, rate=0.6 + 0.2 * rng.random())
    fade = int(0.5 * SR)
    master[:fade] *= np.linspace(0, 1, fade)[:, None]
    master[-fade:] *= np.linspace(1, 0, fade)[:, None]
    peak = np.max(np.abs(master)) or 1.0
    master = np.tanh(master * (0.92 / peak) * 1.05) * 0.94
    return master


def write_wav(path, stereo):
    data = np.clip(stereo, -1, 1)
    pcm = (data * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser(description="Original lo-fi track generator for wish-reel.")
    ap.add_argument("--mood", default="tree", choices=["tree", "columbarium"],
                    help="tree = warm/hopeful (major); columbarium = wistful (minor)")
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--bpm", type=float, default=0.0,
                    help="override tempo (default 74 tree / 64 columbarium)")
    ap.add_argument("--candidate", choices=list(CANDIDATES),
                    help="render only this candidate (default: all three)")
    ap.add_argument("--out-prefix", default=str(ROOT / "instagram_videos" / "track"),
                    help="output path prefix; writes <prefix>_c1.wav … _c3.wav")
    args = ap.parse_args()

    base_bpm = args.bpm or (64.0 if args.mood == "columbarium" else 74.0)
    cands = [args.candidate] if args.candidate else list(CANDIDATES)
    out_prefix = Path(args.out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating {len(cands)} lo-fi track(s) [{args.mood}, {args.seconds:.0f}s]…\n")
    results = []
    for c in cands:
        cfg = CANDIDATES[c]
        bpm = base_bpm * cfg["bpm_mul"]
        stereo = render(args.mood, c, args.seconds, bpm)
        path = out_prefix.with_name(f"{out_prefix.name}_{c}.wav")
        write_wav(path, stereo)
        results.append((c, cfg["name"][args.mood], cfg["blurb"], bpm, path))

    print("Pick one — then mux it into the reel:\n")
    for c, name, blurb, bpm, path in results:
        print(f"  {c}  “{name}”  ({bpm:.0f} BPM) — {blurb}")
        print(f"       {path}")
    print("\nMux (after you pick, e.g. c2):")
    ex = results[0][4]
    final = out_prefix.with_name(out_prefix.name.replace('.track', '') + ".final.mp4")
    print(f"  ffmpeg -y -i REEL.mp4 -i {ex} \\\n"
          f"    -c:v copy -c:a aac -b:a 192k -shortest {final}")


if __name__ == "__main__":
    main()
