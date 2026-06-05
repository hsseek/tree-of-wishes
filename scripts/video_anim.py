"""Animate a still pixel-art illustration into a vertical Instagram Reel.

The reliable route to reference-quality reels: take a beautiful still (licensed
pack / commission / AI-gen you have rights to) and let code add the motion —
a slow Ken-Burns pan, drifting wish-light particles, film grain, a vignette
breath — plus the real wishes fading in at the top and a brand handle.

This is what lofi channels actually do: one gorgeous illustration + subtle
animated overlay. Silent (add music in Instagram).

Wishes are fetched from the live API's private reel endpoint (no DB needed →
runs on any machine). Set REEL_API_TOKEN to the same secret the server uses;
without it the endpoint refuses (404). --base-url / TOW_BASE_URL override the
host (default tree-of-wishes.fyi).

Usage:
    .venv/bin/python scripts/video_anim.py --image ART.png --ids 14 36
    .venv/bin/python scripts/video_anim.py --image ART.png --ids 9 --board columbarium
"""
import argparse
import json
import math
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent

W, H = 1080, 1920
FPS = 24
PAN_FRAC = 0.16    # gentle drift: total pan ≈ this fraction of the frame (relaxing)
# Galmuri11 — retro bitmap/pixel font with full Hangul (OFL, commercial-OK).
FONT = str(ROOT / "static/fonts/Galmuri11.ttf")
rng = np.random.default_rng(7)

# particle tint per mood
TINT = {"tree": np.array([255, 216, 150.]),        # warm fireflies / wish-lights
        "columbarium": np.array([200, 214, 245.])}  # cool, lonelier motes

# precomputed soft round glow stamp
_R = 16
_gy, _gx = np.mgrid[-_R:_R + 1, -_R:_R + 1]
GLOW = np.clip(1 - np.sqrt(_gx ** 2 + _gy ** 2) / _R, 0, 1)[..., None] ** 2

# vignette
_yy, _xx = np.mgrid[0:H, 0:W]
VIGNETTE = (1 - 0.34 * np.clip(((np.abs(_xx - W / 2) / (W / 2)) ** 3
            + (np.abs(_yy - H / 2) / (H / 2)) ** 3), 0, 1))[..., None]


def load_cover(path):
    """Nearest-upscale the still to cover the frame with headroom for panning."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    scale = max(W / w, H / h) * 1.18
    return np.asarray(im.resize((int(w * scale), int(h * scale)), Image.NEAREST), float)


def load_bg_frames(path):
    """Decode an animated background (already pixelized) into W×H uint8 frames.

    Used by --bg-video: the moving pixel-art clip plays under the wishes instead
    of a still. Forced to the frame size by ffmpeg's scaler. Returns a list the
    renderer ping-pong loops to fill the (longer) wish duration."""
    dec = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-"],
        stdout=subprocess.PIPE)
    fsz, frames = W * H * 3, []
    while True:
        raw = dec.stdout.read(fsz)
        if len(raw) < fsz:
            break
        frames.append(np.frombuffer(raw, np.uint8).reshape(H, W, 3).copy())
    dec.stdout.close(); dec.wait()
    return frames


def pingpong(f, n):
    """Seamless loop index: 0..n-1..1..(repeat) — no hard cut at the loop seam."""
    if n <= 1:
        return 0
    period = 2 * n - 2
    k = f % period
    return k if k < n else period - k


def add_glow(img, cx, cy, color, a):
    x0, y0 = cx - _R, cy - _R
    x1, y1 = cx + _R + 1, cy + _R + 1
    ix0, iy0, ix1, iy1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    if ix0 >= ix1 or iy0 >= iy1:
        return
    sx0, sy0 = ix0 - x0, iy0 - y0
    stamp = GLOW[sy0:sy0 + (iy1 - iy0), sx0:sx0 + (ix1 - ix0)]
    img[iy0:iy1, ix0:ix1] = np.minimum(255, img[iy0:iy1, ix0:ix1] + stamp * color * a)


def ease(u):
    return u * u * (3 - 2 * u)


# ── text (top-aligned) ─────────────────────────────────────────────────────────
def _wrap(d, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if d.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_text(pil, text, alpha, name=None):
    """Retro pixel text, top-aligned, with a hard offset shadow for legibility.

    If ``name`` is a non-empty string (the wisher chose not to stay anonymous),
    an attribution line ``— name`` is drawn just below the wish in a smaller,
    warmer pixel type."""
    d = ImageDraw.Draw(pil)
    font = ImageFont.truetype(FONT, 44)        # multiple of 11 → crisp Galmuri
    lines = _wrap(d, text, font, int(W * 0.86))
    a = int(255 * alpha)
    y = int(H * 0.075)
    for ln in lines:
        w = d.textlength(ln, font=font)
        x = round((W - w) / 2)
        d.text((x + 4, y + 4), ln, font=font, fill=(0, 0, 0, int(a * 0.7)))   # hard shadow
        d.text((x, y), ln, font=font, fill=(247, 244, 236, a))
        y += 62
    if name:                                   # named wish → show the wisher
        nf = ImageFont.truetype(FONT, 33)      # multiple of 11, a touch smaller
        attribution = f"— {name}"
        nw = d.textlength(attribution, font=nf)
        nx = round((W - nw) / 2)
        ny = y + 8
        d.text((nx + 3, ny + 3), attribution, font=nf, fill=(0, 0, 0, int(a * 0.7)))
        d.text((nx, ny), attribution, font=nf, fill=(236, 214, 170, a))   # warm gold
    hf = ImageFont.truetype(FONT, 22)
    hw = d.textlength("tree-of-wishes.fyi", font=hf)
    d.text((round((W - hw) / 2) + 3, H - 92 + 3), "tree-of-wishes.fyi", font=hf,
           fill=(0, 0, 0, int(160 * min(1, alpha + 0.3))))
    d.text((round((W - hw) / 2), H - 92), "tree-of-wishes.fyi", font=hf,
           fill=(232, 228, 220, int(210 * min(1, alpha + 0.3))))


def text_alpha(t, start, hold, fade=0.7):
    if t < start or t > start + fade * 2 + hold:
        return 0.0
    lo = t - start
    if lo < fade:
        return lo / fade
    if lo < fade + hold:
        return 1.0
    return max(0.0, 1 - (lo - fade - hold) / fade)


# Shared secret for the private reel endpoint — must match the server's
# REEL_API_TOKEN. Set it in your environment; only you can then pull wishes.
REEL_TOKEN = os.getenv("REEL_API_TOKEN", "")


def _get_json(url):
    headers = {"User-Agent": "Mozilla/5.0 (wish-reel)"}  # Cloudflare 403s default UA
    if REEL_TOKEN:
        headers["X-Reel-Token"] = REEL_TOKEN
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def _fetch_hint(e):
    if isinstance(e, urllib.error.HTTPError) and e.code == 404:
        print("  ⚠ private reel endpoint refused (404). Set REEL_API_TOKEN to the same "
              "value as the server's, and make sure the server is deployed with it.")
    else:
        print(f"  ⚠ fetch failed: {e}")


def fetch_wishes(ids, base_url):
    """Fetch wishes by id from the private reel endpoint (preserves order)."""
    try:
        data = _get_json(f"{base_url}/api/reel/wishes?ids={','.join(map(str, ids))}")
    except Exception as e:                            # noqa: BLE001
        _fetch_hint(e)
        return []
    by_id = {w["id"]: w for w in data.get("wishes", [])}
    return [by_id[i] for i in ids if i in by_id]


def fetch_board_wishes(board, base_url, n):
    """Fallback when no ids are given — take the first n wishes of a board."""
    try:
        return _get_json(f"{base_url}/api/reel/wishes?board={board}&limit={n}").get("wishes", [])
    except Exception as e:                            # noqa: BLE001
        _fetch_hint(e)
        return []


# ── ambient effects ─────────────────────────────────────────────────────────
# Each effect is a closure apply(img, t) composited onto the 1080xH frame.
# Coordinates in the --fx spec are fractions 0..1 of the frame (so they survive
# any image size). In the wish-reel skill, Claude looks at the image and places
# these on the right spots (train on a track line, shimmer on water, wiggle on a
# cat tail / foliage, flicker/twinkle on windows or neon, rain/snow full-frame).

def _f(p, k, d):
    try:
        return float(p[k])
    except (KeyError, ValueError, TypeError):
        return d


def _region(p, dx, dy, dw, dh):
    x0 = int(_f(p, "x", dx) * W); y0 = int(_f(p, "y", dy) * H)
    x1 = x0 + int(_f(p, "w", dw) * W); y1 = y0 + int(_f(p, "h", dh) * H)
    return max(0, x0), max(0, y0), min(W, x1), min(H, y1)


def fx_rain(p):
    n = int(_f(p, "intensity", 0.5) * 240) + 50
    dxr = math.tan(math.radians(_f(p, "angle", 12)))
    xs = rng.uniform(0, W, n); ys = rng.uniform(0, H, n)
    ln = rng.integers(10, 26, n); spd = rng.uniform(1.0, 1.7, n)
    a = _f(p, "alpha", 0.20); col = np.array([205, 214, 235.])

    def ap(img, t):
        yy = (ys + t * spd * H * 1.25) % (H + 40)
        for i in range(n):
            x = xs[i]; y = int(yy[i]); L = int(ln[i])
            for k in range(L):
                py = y - k; px = int(x - k * dxr)
                if 0 <= py < H and 0 <= px < W:
                    img[py, px] = np.minimum(255, img[py, px] + col * a * (1 - k / L))
    return ap


def fx_snow(p):
    n = int(_f(p, "intensity", 0.5) * 180) + 40
    xs = rng.uniform(0, W, n); ys = rng.uniform(0, H, n)
    spd = rng.uniform(0.18, 0.5, n); sway = rng.uniform(8, 26, n)
    ph = rng.uniform(0, 6.28, n); sz = rng.integers(2, 5, n)

    def ap(img, t):
        for i in range(n):
            y = (ys[i] + t * spd[i] * H) % (H + 20)
            x = xs[i] + sway[i] * math.sin(0.5 * t + ph[i])
            xi, yi, s = int(x), int(y), int(sz[i])
            if 0 <= xi < W - s and 0 <= yi < H - s:
                img[yi:yi + s, xi:xi + s] = np.minimum(
                    255, img[yi:yi + s, xi:xi + s] + np.array([235, 240, 250.]) * 0.85)
    return ap


def fx_train(p):
    yc = _f(p, "y", 0.5) * H; h = max(6, int(_f(p, "h", 0.05) * H))
    period = _f(p, "period", 16); dur = _f(p, "dur", 3.5)
    right = p.get("dir", "right") != "left"; L = int(_f(p, "len", 0.55) * W)
    y0 = max(0, int(yc - h / 2)); y1 = min(H, y0 + h)
    body = np.array([20, 18, 28.]); roof = np.array([46, 42, 60.]); win = np.array([255, 206, 120.])

    def ap(img, t):
        ph = t % period
        if ph > dur:
            return
        prog = ph / dur
        hx = int(-L + prog * (W + L)) if right else int(W - prog * (W + L))
        x0, x1 = max(0, hx), min(W, hx + L)
        if x0 >= x1:
            return
        img[y0:y1, x0:x1] = body
        img[y0:y0 + max(1, int(h * 0.16)), x0:x1] = roof
        ww = max(3, int(h * 0.30)); gap = max(4, int(h * 0.55)); wy = y0 + int(h * 0.32)
        wx = hx + gap
        while wx < hx + L - ww:
            ax0, ax1 = max(0, wx), min(W, wx + ww)
            if ax0 < ax1:
                img[wy:wy + ww, ax0:ax1] = win
            wx += gap + ww
    return ap


def fx_flicker(p):
    x0, y0, x1, y1 = _region(p, 0.6, 0.4, 0.06, 0.08)
    period = _f(p, "period", 3); amp = _f(p, "amp", 0.22)

    def ap(img, t):
        fac = 1 + amp * (0.5 * math.sin(2 * math.pi * t / period) + 0.5 * math.sin(11.0 * t + 1.3))
        img[y0:y1, x0:x1] = np.clip(img[y0:y1, x0:x1] * fac, 0, 255)
    return ap


def fx_twinkle(p):
    x0, y0, x1, y1 = _region(p, 0.1, 0.2, 0.8, 0.3)
    rw, rh = max(1, x1 - x0), max(1, y1 - y0)
    n = int(_f(p, "density", 0.4) * 40) + 6
    px = rng.integers(0, rw, n); py = rng.integers(0, rh, n)
    ph = rng.uniform(0, 6.28, n); fr = rng.uniform(0.3, 1.2, n)
    col = np.array([255, 225, 150.])

    def ap(img, t):
        for i in range(n):
            b = 0.5 + 0.5 * math.sin(2 * math.pi * fr[i] * t + ph[i])
            if b > 0.55:
                img[y0 + int(py[i]), x0 + int(px[i])] = np.minimum(
                    255, img[y0 + int(py[i]), x0 + int(px[i])] + col * (b - 0.5) * 2 * 0.85)
    return ap


def fx_shimmer(p):
    yc = _f(p, "y", 0.82); hh = _f(p, "h", 0.16)
    y0 = max(0, int((yc - hh / 2) * H)); y1 = min(H, int((yc + hh / 2) * H))
    amp = _f(p, "amp", 2.0); speed = _f(p, "speed", 0.3)
    rows = max(1, y1 - y0); rf = np.arange(rows); cols = np.arange(W)

    def ap(img, t):
        s = amp * np.sin(2 * math.pi * speed * t + rf * 0.35)
        idx = ((cols[None, :] - s[:, None]).round().astype(int)) % W
        img[y0:y1] = img[y0:y1][np.arange(rows)[:, None], idx]
    return ap


def fx_wiggle(p):
    x0, y0, x1, y1 = _region(p, 0.2, 0.7, 0.06, 0.06)
    period = _f(p, "period", 5); dur = _f(p, "dur", 1.6); amp = _f(p, "amp", 2.5)
    rows = max(1, y1 - y0); rf = np.linspace(0, 1, rows)

    def ap(img, t):
        ph = t % period
        if ph > dur:
            return
        env = math.sin(math.pi * ph / dur)
        s = (amp * env * math.sin(2 * math.pi * 2 * ph / dur)) * rf
        reg = img[y0:y1, x0:x1]; w = reg.shape[1]
        if w == 0:
            return
        idx = ((np.arange(w)[None, :] - s[:, None]).round().astype(int)) % w
        img[y0:y1, x0:x1] = reg[np.arange(rows)[:, None], idx]
    return ap


def fx_drift(p):
    yc = _f(p, "y", 0.22); hh = _f(p, "h", 0.28)
    y0 = max(0, int((yc - hh / 2) * H)); y1 = min(H, int((yc + hh / 2) * H))
    speed = _f(p, "speed", 5.0)   # px/sec; best on a fairly uniform sky/cloud band

    def ap(img, t):
        img[y0:y1] = np.roll(img[y0:y1], int(t * speed) % W, axis=1)
    return ap


def fx_string(p):
    # String/fairy lights that flicker in ALTERNATING fashion: the actual bright
    # bulbs in the region are found once, split into spatial bands, and adjacent
    # bands pulse in antiphase (band A up while band B down). Only real bulb
    # pixels are modulated, so the glow stays on the lights — not the glass/wall.
    x0, y0, x1, y1 = _region(p, 0.30, 0.0, 0.65, 0.10)
    period = _f(p, "period", 1.4); amp = _f(p, "amp", 0.55)
    thr = _f(p, "thr", 210); band = max(2, int(_f(p, "band", 0.02) * W))
    st = {}

    def ap(img, t):
        reg = img[y0:y1, x0:x1]
        if "grp" not in st:                       # detect bulbs on the base frame
            ys, xs = np.where(reg.mean(axis=2) > thr)
            st["ys"], st["xs"] = ys, xs
            st["grp"] = ((xs // band) % 2).astype(bool)
        ys, xs, grp = st["ys"], st["xs"], st["grp"]
        if len(xs) == 0:
            return
        ph = math.sin(2 * math.pi * t / period)
        fac = np.where(grp, 1 + amp * ph, 1 - amp * ph)   # antiphase bands
        reg[ys, xs] = np.clip(reg[ys, xs] * fac[:, None], 0, 255)
    return ap


def fx_steam(p):
    # Steam rising from a hot cup. Physics: wisps travel UP from the rim, spread
    # laterally and grow as they rise (diffusion), and fade to nothing near the
    # top (dissipation). `speed` controls how fast they rise. The region's BOTTOM
    # edge (y+h) is the rim; steam never moves downward.
    x0, y0, x1, y1 = _region(p, 0.59, 0.55, 0.10, 0.17)
    rw, rh = max(1, x1 - x0), max(1, y1 - y0)
    n = int(_f(p, "intensity", 0.5) * 22) + 8
    speed = _f(p, "speed", 1.2)          # higher = rises faster
    a = _f(p, "alpha", 0.12); sway = _f(p, "sway", 0.6)
    base = rng.uniform(0.30, 0.70, n)    # emit near the cup centre
    ph = rng.uniform(0, 6.28, n); spd = rng.uniform(0.85, 1.25, n)
    col = np.array([248, 244, 238.])

    def ap(img, t):
        for i in range(n):
            prog = (t * speed * spd[i] + ph[i]) % 1.0      # 0 at rim → 1 at top
            yy = int(y1 - prog * rh)                        # rise upward
            spread = sway * rw * 0.5 * prog                 # widen with height
            xx = int(x0 + base[i] * rw + spread * math.sin(3.0 * t + ph[i] * 4))
            fade = math.sin(math.pi * prog) ** 1.2          # fade in/out
            s = 2 + int(prog * 3)                           # wisp grows as it rises
            if 0 <= xx < W - s and 0 <= yy < H - s:
                img[yy:yy + s, xx:xx + s] = np.minimum(
                    255, img[yy:yy + s, xx:xx + s] + col * a * fade)
    return ap


def fx_swing(p):
    # Continuous pendulum swing for a hanging/draped tail. Unlike `wiggle` (a
    # brief occasional sway), this never stops. The pivot end is fixed and the
    # free end sweeps most. For a roughly horizontal tail the sweep is vertical
    # (tip rises/falls); `pivot=left|right` sets which end is anchored.
    x0, y0, x1, y1 = _region(p, 0.02, 0.635, 0.15, 0.04)
    period = _f(p, "period", 2.2); amp = _f(p, "amp", 5.0)
    cols = max(1, x1 - x0); rows = max(1, y1 - y0)
    cf = np.linspace(0, 1, cols)
    amt = cf if p.get("pivot", "left") == "left" else cf[::-1]

    def ap(img, t):
        s = amp * math.sin(2 * math.pi * t / period) * amt   # vertical shift/col
        reg = img[y0:y1, x0:x1]; h = reg.shape[0]
        if h == 0:
            return
        idx = ((np.arange(h)[:, None] - s[None, :]).round().astype(int)) % h
        img[y0:y1, x0:x1] = reg[idx, np.arange(cols)[None, :]]
    return ap


_FX = {"rain": fx_rain, "snow": fx_snow, "train": fx_train, "flicker": fx_flicker,
       "twinkle": fx_twinkle, "shimmer": fx_shimmer, "wiggle": fx_wiggle, "drift": fx_drift,
       "string": fx_string, "steam": fx_steam, "swing": fx_swing}


def compile_fx(spec):
    typ, _, rest = spec.partition(":")
    p = dict(kv.split("=", 1) for kv in rest.split(",") if "=" in kv) if rest else {}
    if typ not in _FX:
        print(f"  ⚠ unknown effect '{typ}' (have: {', '.join(_FX)})")
        return None
    return _FX[typ](p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="still pixel-art background")
    ap.add_argument("--bg-video", dest="bg_video",
                    help="animated (already pixelized) background clip; ping-pong "
                         "looped under the wishes instead of a still --image")
    ap.add_argument("--ids", nargs="*", type=int)
    ap.add_argument("--board", default="auto", choices=["auto", "tree", "columbarium"],
                    help="mood; 'auto' infers it from the wishes' board")
    ap.add_argument("--focus", type=float, default=0.5,
                    help="0..1 anchor along the pan axis — aim the crop at the subject")
    ap.add_argument("--seconds", type=float, default=None,
                    help="total length. Default: dynamic — the sum of each wish's "
                         "reading time (longer messages stay up longer). If set, "
                         "that fixed budget is split across wishes in proportion "
                         "to their length.")
    ap.add_argument("--cps", type=float, default=6.0,
                    help="reading speed (chars/sec) driving per-wish on-screen time")
    ap.add_argument("--min-hold", type=float, default=2.2,
                    help="floor for how long a wish stays fully visible (s)")
    ap.add_argument("--max-hold", type=float, default=10.0,
                    help="cap for how long a wish stays fully visible (s)")
    ap.add_argument("--no-pan", action="store_true",
                    help="static centered crop — disable the Ken-Burns pan")
    ap.add_argument("--out", default=str(ROOT / "instagram_videos" / "anim.mp4"))
    ap.add_argument("--base-url", default=os.getenv("TOW_BASE_URL", "https://tree-of-wishes.fyi"),
                    help="Tree of Wishes API base (default tree-of-wishes.fyi or $TOW_BASE_URL)")
    ap.add_argument("--fx", action="append", default=[],
                    help="ambient effect (repeatable), e.g. rain:intensity=0.5 | "
                         "train:y=0.62,dir=left,period=12 | shimmer:y=0.85 | "
                         "wiggle:x=0.2,y=0.7,w=0.05,h=0.05 | flicker:x=0.7,y=0.4")
    args = ap.parse_args()
    base_url = args.base_url.rstrip("/")
    if not (args.image or args.bg_video):
        ap.error("pass --image (still) or --bg-video (animated clip)")

    # wishes from the live API — no local DB needed
    if args.ids:
        wishes = fetch_wishes(args.ids, base_url)
    else:
        wishes = fetch_board_wishes(args.board if args.board != "auto" else "tree", base_url, 2)
    if not wishes:
        print("No wishes found.")
        return

    # resolve mood
    mood = args.board
    if mood == "auto":
        boards = {w.get("board", "tree") for w in wishes}
        if len(boards) == 1:
            mood = boards.pop()
        else:
            print(f"Wishes span multiple boards {boards} — pass --board tree|columbarium.")
            return
    tint = TINT[mood]
    if mood == "columbarium":   # slow cool motes drifting down — lonelier, wistful
        particles = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0.010, 0.028),
                      rng.uniform(0, 6.28), rng.uniform(0.4, 0.9)) for _ in range(12)]
    else:                       # warm wish-lights rising — heart-warming
        particles = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0.012, 0.04),
                      rng.uniform(0, 6.28), rng.uniform(0.5, 1.0)) for _ in range(9)]

    # Background: an animated pixel-art clip (--bg-video, ping-pong looped) or a
    # still (--image, optional Ken-Burns pan). The clip already carries the motion,
    # so it ignores pan/focus.
    bg_frames = big = None
    if args.bg_video:
        bg_frames = load_bg_frames(args.bg_video)
        if not bg_frames:
            print("No frames decoded from --bg-video.")
            return
    else:
        big = load_cover(args.image)
        BH, BW = big.shape[:2]
        px, py = BW - W, BH - H
        horizontal = px >= py                   # pan along the longer axis
        avail = px if horizontal else py
        pan_span = 0 if args.no_pan else min(avail, int(PAN_FRAC * (W if horizontal else H)))
        pan_start = max(0, min(avail - pan_span, int(args.focus * avail) - pan_span // 2))

    # Per-wish on-screen time scales with message length so long wishes stay
    # readable. Default total = sum of these reading times; with --seconds, a
    # fixed budget is split across wishes in proportion to their length.
    FADE, LEAD = 0.6, 0.6
    texts = [" ".join((w.get("text") or "").split()) for w in wishes]
    names = [(w.get("name") or "").strip() for w in wishes]   # "" = anonymous
    raw = [min(args.max_hold, max(args.min_hold, len(tx) / args.cps)) for tx in texts]
    if args.seconds:
        budget = max(0.5, args.seconds - len(wishes) * (LEAD + 2 * FADE))
        ssum = sum(raw) or 1.0
        holds = [budget * r / ssum for r in raw]
    else:
        holds = raw
    starts, cur = [], 0.0
    for h in holds:
        cur += LEAD
        starts.append(cur)
        cur += FADE + h + FADE
    total = cur
    n = int(total * FPS)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    effects = [f for f in (compile_fx(s) for s in args.fx) if f]
    src_name = Path(args.bg_video).name if bg_frames is not None else Path(args.image).name
    bg_note = f" (bg {len(bg_frames)} frames, ping-pong)" if bg_frames is not None else ""
    print(f"Rendering {total:.1f}s [{mood}] from {src_name}{bg_note} "
          f"({len(wishes)} wishes @ {args.cps:g} cps, holds "
          f"{', '.join(f'{h:.1f}' for h in holds)}s)…")
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         str(out)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for f in range(n):
        t = f / FPS
        if bg_frames is not None:              # animated clip, ping-pong looped
            img = bg_frames[pingpong(f, len(bg_frames))].astype(float)
        else:                                  # still + optional Ken-Burns pan
            u = ease(f / max(1, n - 1))
            off = pan_start + int(pan_span * u)
            ox, oy = (off, py // 2) if horizontal else (px // 2, off)
            img = big[oy:oy + H, ox:ox + W].copy()
        for fx in effects:                     # scene ambient animations
            fx(img, t)
        if mood == "columbarium":              # cool motes drifting slowly down
            for x0, y0, spd, ph, amp in particles:
                yy = (y0 + t * spd * H) % (H + 60) - 30
                xx = x0 + 22 * math.sin(0.4 * t + ph)
                g = 0.4 + 0.5 * (0.5 + 0.5 * math.sin(1.4 * t + ph))
                add_glow(img, int(xx), int(yy), tint, 0.34 * amp * g)
        else:                                  # rising warm wish-lights
            for x0, y0, spd, ph, amp in particles:
                yy = (y0 - t * spd * H) % (H + 60) - 30
                xx = x0 + 26 * math.sin(0.5 * t + ph)
                g = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(1.8 * t + ph))
                add_glow(img, int(xx), int(yy), tint, 0.5 * amp * g)
        img = img * VIGNETTE * (1 + 0.02 * math.sin(0.6 * t))   # vignette + breath
        img = img + rng.normal(0, 4.0, (H, W, 1))               # film grain
        scene = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
        for i in range(len(wishes)):
            a = text_alpha(t, start=starts[i], hold=holds[i], fade=FADE)
            if a > 0:
                draw_text(scene, texts[i], a, names[i])
        proc.stdin.write(np.ascontiguousarray(
            np.asarray(scene.convert("RGB"), dtype=np.uint8)).tobytes())
    proc.stdin.close()
    proc.wait()
    print(f"→ {out}  ({total:.1f}s)")


if __name__ == "__main__":
    main()
