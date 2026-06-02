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
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

OUT_W = 1080   # crisp upscale width fed to the reel renderer


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


def pixelize(img: Image.Image, pixels: int, colors: int, dither: bool, grade_mode: str) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size
    sw = max(8, pixels)
    sh = max(8, round(h * sw / w))
    small = img.resize((sw, sh), Image.Resampling.BOX)          # area-average downsample
    dmode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    quant = small.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=dmode).convert("RGB")
    quant = grade(quant, grade_mode)
    out_h = round(sh * OUT_W / sw)
    return quant.resize((OUT_W, out_h), Image.Resampling.NEAREST)  # crisp pixels


# name, pixels, colors, dither, grade
SWEEP = [
    ("fine-neutral",  256, 64, False, "none"),
    ("med-neutral",   192, 48, False, "none"),
    ("chunky-muted",  144, 32, True,  "muted"),
    ("med-warm",      192, 48, False, "warm"),
    ("med-cool",      192, 48, False, "cool"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--out-dir", default="instagram_videos/pixelized")
    # single-look overrides (if any given, skip the sweep)
    ap.add_argument("--pixels", type=int)
    ap.add_argument("--colors", type=int, default=48)
    ap.add_argument("--dither", action="store_true")
    ap.add_argument("--grade", choices=["none", "warm", "cool", "muted"], default="none")
    args = ap.parse_args()

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
        pixelize(src, px, cols, dith, gr).save(out)
        print(f"  c{i}: {out.name}  ({px}px, {cols} colors, dither={dith}, grade={gr})")
    print(f"\n{len(jobs)} candidate(s) → {out_dir}")


if __name__ == "__main__":
    main()
