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


def draw_text(pil, text, alpha):
    """Retro pixel text, top-aligned, with a hard offset shadow for legibility."""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--ids", nargs="*", type=int)
    ap.add_argument("--board", default="auto", choices=["auto", "tree", "columbarium"],
                    help="mood; 'auto' infers it from the wishes' board")
    ap.add_argument("--focus", type=float, default=0.5,
                    help="0..1 anchor along the pan axis — aim the crop at the subject")
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--out", default=str(ROOT / "instagram_videos" / "anim.mp4"))
    ap.add_argument("--base-url", default=os.getenv("TOW_BASE_URL", "https://tree-of-wishes.fyi"),
                    help="Tree of Wishes API base (default tree-of-wishes.fyi or $TOW_BASE_URL)")
    args = ap.parse_args()
    base_url = args.base_url.rstrip("/")

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

    big = load_cover(args.image)
    BH, BW = big.shape[:2]
    px, py = BW - W, BH - H
    horizontal = px >= py                       # pan along the longer axis
    avail = px if horizontal else py
    pan_span = min(avail, int(PAN_FRAC * (W if horizontal else H)))
    pan_start = max(0, min(avail - pan_span, int(args.focus * avail) - pan_span // 2))

    per = args.seconds / len(wishes)
    n = int(args.seconds * FPS)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Rendering {args.seconds:.0f}s [{mood}] from {Path(args.image).name}…")
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         str(out)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for f in range(n):
        t = f / FPS
        u = ease(f / max(1, n - 1))
        off = pan_start + int(pan_span * u)
        ox, oy = (off, py // 2) if horizontal else (px // 2, off)
        img = big[oy:oy + H, ox:ox + W].copy()
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
        for i, wsh in enumerate(wishes):
            a = text_alpha(t, start=i * per + 0.7, hold=per - 2.2)
            if a > 0:
                draw_text(scene, " ".join((wsh.get("text") or "").split()), a)
        proc.stdin.write(np.ascontiguousarray(
            np.asarray(scene.convert("RGB"), dtype=np.uint8)).tobytes())
    proc.stdin.close()
    proc.wait()
    print(f"→ {out}")


if __name__ == "__main__":
    main()
