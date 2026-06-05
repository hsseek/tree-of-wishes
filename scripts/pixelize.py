"""Task 2 — turn any image into pixel-art candidates for the wish-reel pipeline.

Downscale to a small pixel grid, quantize to a limited palette (optionally
dithered), color-grade the tone, then nearest-upscale for crisp pixels. Emits a
small sweep of candidates (different pixel size / palette / tone) so you can pick
the best one to feed into the wish-reel renderer.

Needs: pip install -r requirements-tools.txt

Usage:
    .venv/bin/python scripts/pixelize.py --image ART.png          # 5-candidate sweep
    .venv/bin/python scripts/pixelize.py --image ART.png --pixels 192 --colors 48 \
        --grade warm --dither --out-dir out/   # one specific look
"""
import argparse
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

OUT_W = 1080   # crisp upscale width fed to the reel renderer


def dewatermark(img: Image.Image) -> Image.Image:
    """Suppress faint, tiled/translucent stock watermarks before downscaling.

    A median filter (sized to the image) breaks up the thin watermark strokes;
    the later area-average downscale then blends what's left into the background,
    so by pixel-art resolution the mark is gone. This handles the common 'stock
    preview' watermark (e.g. tiled 'dreamstime.com' text). It will NOT cleanly
    erase a large opaque logo — and it is NOT a usage license for the image.
    """
    img = img.convert("RGB")
    size = min(9, max(3, round(img.size[0] / 300) | 1))   # odd, grows with width
    return img.filter(ImageFilter.MedianFilter(size))


def grade(img: Image.Image, mode: str) -> Image.Image:
    if mode == "none":
        return img
    if mode == "muted":   # dusty lofi: desaturate a touch + gentle contrast
        img = ImageEnhance.Color(img).enhance(0.78)
        return ImageEnhance.Contrast(img).enhance(1.06)
    arr = np.asarray(img, float)
    if mode == "warm":    # sunset push
        arr[..., 0] *= 1.08
        arr[..., 1] *= 1.01
        arr[..., 2] *= 0.90
    elif mode == "cool":  # wistful dusk push
        arr[..., 0] *= 0.92
        arr[..., 2] *= 1.10
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))


def pixelize(img: Image.Image, pixels: int, colors: int, dither: bool, grade_mode: str,
             dewater: bool = True) -> Image.Image:
    img = img.convert("RGB")
    if dewater:                                                 # strip stock watermarks first
        img = dewatermark(img)
    w, h = img.size
    sw = max(8, pixels)
    sh = max(8, round(h * sw / w))
    small = img.resize((sw, sh), Image.Resampling.BOX)          # area-average downsample
    dmode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    quant = small.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=dmode).convert("RGB")
    quant = grade(quant, grade_mode)
    out_h = round(sh * OUT_W / sw)
    return quant.resize((OUT_W, out_h), Image.Resampling.NEAREST)  # crisp pixels


# ── video pixelization ──────────────────────────────────────────────────────
# Same look as the still pipeline, but applied per frame with ONE shared palette
# (computed from sampled frames) so colors don't shimmer frame-to-frame. Output
# is a 1080x1920 pixel-art mp4 ready to feed wish-reel's --bg-video.
VID_W, VID_H = 1080, 1920


def _cover_crop(im: Image.Image, w: int, h: int) -> Image.Image:
    """Scale to cover w×h and centre-crop (preserves aspect, fills the frame)."""
    iw, ih = im.size
    scale = max(w / iw, h / ih)
    im = im.resize((round(iw * scale), round(ih * scale)), Image.LANCZOS)
    iw, ih = im.size
    left, top = (iw - w) // 2, (ih - h) // 2
    return im.crop((left, top, left + w, top + h))


def _probe(path, entries):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", f"stream={entries}", "-of", "csv=p=0:s=x", str(path)],
        capture_output=True, text=True).stdout.strip()
    return out.split("x")


def pixelize_video(in_path, out_path, pixels, colors, dither, grade_mode, sample=14):
    w0, h0 = (int(v) for v in _probe(in_path, "width,height")[:2])
    num, den = (_probe(in_path, "r_frame_rate")[0].split("/") + ["1"])[:2]
    fps = (float(num) / float(den or 1)) or 24.0
    sw = max(8, pixels)
    sh = max(8, round(VID_H * sw / VID_W))      # grid keeps the 9:16 frame
    dmode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE

    # 1) decode every native frame, cover-crop to 9:16, downsample to the grid
    dec = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(in_path),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    fsz, smalls = w0 * h0 * 3, []
    while True:
        raw = dec.stdout.read(fsz)
        if len(raw) < fsz:
            break
        fr = Image.fromarray(np.frombuffer(raw, np.uint8).reshape(h0, w0, 3))
        smalls.append(_cover_crop(fr, VID_W, VID_H).resize((sw, sh), Image.Resampling.BOX))
    dec.stdout.close(); dec.wait()
    if not smalls:
        raise SystemExit("no frames decoded from video")

    # 2) one shared palette from sampled frames → temporal color stability
    idxs = np.linspace(0, len(smalls) - 1, min(sample, len(smalls))).round().astype(int)
    montage = Image.new("RGB", (sw, sh * len(idxs)))
    for j, k in enumerate(idxs):
        montage.paste(smalls[k], (0, j * sh))
    pal = montage.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)

    # 3) quantize each frame to that fixed palette, grade, crisp-upscale, encode
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{VID_W}x{VID_H}", "-r", f"{fps:g}", "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         str(out_path)], stdin=subprocess.PIPE)
    for sm in smalls:
        q = grade(sm.quantize(palette=pal, dither=dmode).convert("RGB"), grade_mode)
        big = q.resize((VID_W, VID_H), Image.Resampling.NEAREST)
        enc.stdin.write(np.asarray(big, np.uint8).tobytes())
    enc.stdin.close(); enc.wait()
    return out_path, len(smalls), fps


# name, pixels, colors, dither, grade
SWEEP = [
    ("chunky-warm",   144, 40, False, "warm"),
    ("med-neutral",   192, 48, False, "none"),
    ("chunky-muted",  144, 32, True,  "muted"),
    ("med-warm",      192, 48, False, "warm"),
    ("med-cool",      192, 48, False, "cool"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="still image → pixel-art candidate(s)")
    ap.add_argument("--video", help="video file → one pixel-art mp4 (shared palette, "
                                    "no frame-to-frame color shimmer). Use --out for the path.")
    ap.add_argument("--out", help="output mp4 path for --video mode")
    ap.add_argument("--out-dir", default="instagram_videos/pixelized")
    # single-look overrides (if any given, skip the sweep)
    ap.add_argument("--pixels", type=int)
    ap.add_argument("--colors", type=int, default=48)
    ap.add_argument("--dither", action="store_true")
    ap.add_argument("--grade", choices=["none", "warm", "cool", "muted"], default="none")
    ap.add_argument("--dewatermark", action=argparse.BooleanOptionalAction, default=True,
                    help="suppress faint stock watermarks before pixelizing (default on; "
                         "--no-dewatermark to skip on already-clean art)")
    args = ap.parse_args()
    if not (args.image or args.video):
        ap.error("pass --image (still) or --video (clip)")

    if args.video:                         # animated pixel-art for wish-reel --bg-video
        px = args.pixels or 192            # default = the 'med-neutral' look
        out = Path(args.out) if args.out else \
            Path(args.out_dir) / f"px_{Path(args.video).stem}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        p, nfr, fps = pixelize_video(args.video, out, px, args.colors, args.dither, args.grade)
        print(f"→ {p}  ({nfr} frames @ {fps:g}fps, {px}px, {args.colors} colors, "
              f"dither={args.dither}, grade={args.grade})")
        return

    src = Image.open(args.image)
    stem = Path(args.image).stem
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.pixels:                       # one specific look
        jobs = [("custom", args.pixels, args.colors, args.dither, args.grade)]
    else:                                  # candidate sweep
        jobs = SWEEP

    for i, (name, px, cols, dith, gr) in enumerate(jobs, 1):
        out = out_dir / f"px_{stem}_c{i}_{name}.png"
        pixelize(src, px, cols, dith, gr, dewater=args.dewatermark).save(out)
        print(f"  c{i}: {out.name}  ({px}px, {cols} colors, dither={dith}, grade={gr})")
    print(f"\n{len(jobs)} candidate(s) → {out_dir}  (dewatermark={args.dewatermark})")


if __name__ == "__main__":
    main()
