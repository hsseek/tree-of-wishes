---
name: wish-pixelize
description: Task 2 of the Tree of Wishes reel pipeline. Turn a source image (e.g. an AI-generated lofi scene) into pixel-art candidates — varying pixel size, palette, and color tone — so the user can pick one to feed into wish-reel. Use when the user wants to "pixelize / 픽셀화 / make pixel art" from an image, or asks for pixel-art candidates.
---

# Wish Pixelize — Task 2 (image → pixel-art candidates)

Stage 2 of three: **Task 1** (generate the original image) is done by an external
image tool (e.g. Nano Banana / Midjourney) — Claude only supplies prompts.
**This skill** turns that image into pixel art. **Task 3** is `wish-reel` (animate
the chosen pixel image + wishes into a Reel). See `memory/project_instagram_reel_tool.md`.

## What it does
(Auto watermark-suppression) → downscale → palette-quantize (optional dither) →
color-grade → crisp nearest upscale (1080px wide). Emits a **sweep of candidates**
so the user picks the best.

## Steps
1. **Generate candidates** (needs `pip install -r requirements-tools.txt` once):
   ```bash
   .venv/bin/python scripts/pixelize.py --image "SOURCE.png" --out-dir instagram_videos/pixelized
   ```
   Default = a 5-candidate sweep: `c1 chunky-warm`, `c2 med-neutral`,
   `c3 chunky-muted` (dither), `c4 med-warm`, `c5 med-cool`.
   Watermark suppression is **on by default** (`--no-dewatermark` to skip on
   already-clean art) — see the watermark note below.
2. **Show the candidates** to the user and let them pick one (or ask for another
   sweep with tweaked settings).
3. **Iterate** a specific look if asked:
   ```bash
   .venv/bin/python scripts/pixelize.py --image "SOURCE.png" \
     --pixels 192 --colors 48 [--dither] --grade warm|cool|muted|none --out-dir ...
   ```
   - `--pixels` lower = chunkier/retro, higher = finer.
   - `--colors` smaller = more stylized/limited palette.
   - `--grade warm` (heart-warming / tree) · `cool` (wistful / columbarium) ·
     `muted` (dusty lofi) · `none`.
4. **Hand off** the chosen file to `wish-reel` (Task 3).

## Pixelize a video (animated background for wish-reel)
When the user supplies a **clip** (e.g. a Kling/Runway image-to-video animation of
the scene — candle flicker, fire, page-turn), pixelize it frame-by-frame into a
1080×1920 pixel-art mp4 to feed `wish-reel --bg-video`:
```bash
.venv/bin/python scripts/pixelize.py --video "CLIP.mp4" \
  --out instagram_videos/pixelized/px_NAME.mp4
# same look knobs as stills: --pixels (default 192) --colors (48) --grade --dither
```
- Uses **one shared palette** computed from sampled frames, so colors don't shimmer
  frame-to-frame (per-frame quantization would flicker). Default look = the
  `med-neutral` still preset (192px, 48 colors, no dither/grade); pass overrides to
  match a still the user already picked.
- Cover-crops to 9:16 and emits a **silent** mp4 (wish-reel adds the soundtrack).
- Free image-to-video tools often **burn in a watermark** (e.g. Kling's corner
  mark) that survives downscaling as a faint smudge — warn the user; it is not a
  license, and they may want it cropped/covered before posting.

## Watermark removal (on by default)
A pre-pass (`dewatermark()` in `scripts/pixelize.py`) suppresses faint, tiled or
translucent **stock-preview watermarks** (e.g. `dreamstime.com` text): a
size-scaled median filter breaks up the thin strokes, then the heavy downscale
blends the rest into the background, so by pixel-art resolution the mark is gone.
- It will **not** cleanly erase a large opaque logo, and it lightly softens fine
  detail (harmless here — the output is downsampled pixel art anyway).
- **It is NOT a license.** Removing a watermark does not grant rights to use the
  image. For a commercial post, license the art (or use art you own). Always warn
  the user when the source looks like a watermarked stock preview.

## Notes
- Works best on clean source art with good contrast and a clear focal scene.
- Output is 1080px wide, crisp nearest-neighbour pixels, aspect preserved.
- Outputs go to `instagram_videos/pixelized/` (git-ignored — regenerate freely).
