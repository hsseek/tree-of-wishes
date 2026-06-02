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
Downscale → palette-quantize (optional dither) → color-grade → crisp nearest
upscale (1080px wide). Emits a **sweep of candidates** so the user picks the best.

## Steps
1. **Generate candidates** (needs `pip install -r requirements-tools.txt` once):
   ```bash
   .venv/bin/python scripts/pixelize.py --image "SOURCE.png" --out-dir instagram_videos/pixelized
   ```
   Default = a 5-candidate sweep: `c1 fine-neutral`, `c2 med-neutral`,
   `c3 chunky-muted` (dither), `c4 med-warm`, `c5 med-cool`.
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

## Notes
- Works best on clean source art with good contrast and a clear focal scene.
- Output is 1080px wide, crisp nearest-neighbour pixels, aspect preserved.
- Outputs go to `instagram_videos/pixelized/` (git-ignored — regenerate freely).
