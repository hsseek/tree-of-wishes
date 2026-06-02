---
name: wish-reel
description: Generate an Instagram Reel (vertical 1080x1920 lofi pixel-art video) for Tree of Wishes from a still pixel-art image + a list of wish IDs, and write its Korean caption. Use when the user wants to turn wishes into an Instagram video/reel, or says things like "make a reel / 영상 만들어 / 인스타 영상" with wish IDs and an image.
---

# Wish Reel — Instagram video generator

Turn a beautiful **still** pixel-art illustration + some wishes into a relaxing
vertical Reel: a slow Ken-Burns pan, **small scene-specific ambient animations**
(a passing train, rain, snow, a twitching cat tail, twinkling windows, shimmering
water…), film grain, and the wishes fading in at the top in a retro Hangul pixel
font — plus a ready-to-paste caption.

**Task 3 of a 3-stage pipeline:** Task 1 = generate the original scene with an
external image tool (Nano Banana / Midjourney; Claude only supplies prompts).
Task 2 = `wish-pixelize` (image → pixel-art candidates, pick one). Task 3 (this) =
animate the chosen pixel image + wishes into a Reel. Input `--image` is normally
the picked `wish-pixelize` output.

**Division of labor (important):** the *still art* carries the beauty — the user
supplies it (AI-gen + pixelized). The code (`scripts/video_anim.py`) adds the
motion + text. Do **not** try to draw the art procedurally — that was tried and
rejected as not attractive. See `memory/project_instagram_reel_tool.md`.

## Inputs
- **image** — path to a clean (no watermark), commercially-licensed lofi pixel-art
  still. Vertical art is ideal; landscape works (the engine pans a vertical crop).
- **wish IDs** — the numbers from `/wish/{id}` URLs (e.g. `123` from
  `tree-of-wishes.fyi/wish/123`). `Wish.id` is the indexed primary key.
- optional: mood (`tree` warm / `columbarium` wistful) — **default: infer from the
  wishes' board**; `--focus 0..1` to aim the crop at an off-centre subject;
  `--seconds` (default 12).

## Steps
1. **Mood is auto-inferred** from the wishes' board — the engine fetches each wish
   from the live API, so just leave `--board auto` (default). Only pass
   `--board tree|columbarium` if the engine reports the wishes span both boards
   (then split into two reels, or pick one).
2. **Choose ambient effects — LOOK AT THE IMAGE FIRST.** Open/view the chosen
   pixel image and pick **1–3 small, subtle** animations that fit the scene, and
   *where* they go (coords are fractions 0..1 of the frame). Map scene → effect:
   - city skyline → `twinkle` on the window band; maybe a `train` on a track/bridge line
   - rainy / snowy mood → `rain` or `snow` (full-frame)
   - water / lake / reflection → `shimmer` on the water band
   - cat / hanging plants / foliage → `wiggle` on that small region (tail/leaves)
   - neon sign / single lit window → `flicker` on that spot
   - big calm sky → gentle `drift` on the sky band

   **Respect physics & scale (critical — this is the #1 failure mode).** Every
   effect must attach to a *real* surface/object in the image at the right size,
   depth, and place:
   - A `train` runs on an **actual track / bridge / ground line** — never floating
     in the sky. Size it to nearby real objects (cars, doors, windows), **not
     bigger than the buildings**; usually a **thin band low in the frame**. Read
     the `h` and `len` off the scene. **No track in the image → no train.**
   - `shimmer` only on water; `wiggle` only on the thing that actually sways;
     `twinkle`/`flicker` only on real lights/windows/signs; `drift` only on sky.
   - Match perspective: foreground = larger/faster, background = smaller/slower.
   - If a scene has no plausible spot for an effect, **omit it** — don't force it.
   Relaxing = **fewer, slower, subtler**. See the table + checklist below.
3. **Render** (needs `pip install -r requirements-tools.txt` once; `ffmpeg` present):
   ```bash
   .venv/bin/python scripts/video_anim.py \
     --image "PATH" --ids ID1 ID2 ID3 [--focus 0.5] [--seconds 12] \
     --fx "twinkle:x=0.05,y=0.4,w=0.9,h=0.25" \
     --fx "train:y=0.62,h=0.03,dir=left,period=12,dur=3" \
     --out instagram_videos/reel_NAME.mp4
   ```
   ~40–60s to render. Output is **silent** (the user adds music in Instagram).
   Wishes come from the API (token-gated; needs `REEL_API_TOKEN`) — **no local DB**.
4. **Caption — you (Claude) write it**, no API call. Save to
   `instagram_videos/reel_NAME.caption.txt` and show it. Follow the rules below.
5. **Report**: the `.mp4` path + the caption. Remind: add music in-app, and confirm
   the art is licensed for commercial use.

## Ambient effects (`--fx`, repeatable; coords are fractions 0..1 of the frame)
Place by **looking at the image**; keep them subtle and few. Existing mood
particles still apply (tree = warm rising lights, columbarium = cool motes).
- `rain:intensity=0.5,angle=12,alpha=0.2` — full-frame diagonal rain.
- `snow:intensity=0.5` — full-frame falling snow.
- `train:y=0.78,h=0.025,dir=left|right,period=14,dur=3.5,len=0.45` — a lit train
  passes along the band centred at `y`. **Put `y` on a real track/bridge/ground
  line** (usually low in the frame) and keep `h` small (≈ a car/door height — far
  less than a building). A too-high `y` or oversized `h` = "train flying in the sky".
- `twinkle:x=0.05,y=0.4,w=0.9,h=0.25,density=0.5` — lights blink in a region (city windows).
- `flicker:x=0.7,y=0.4,w=0.06,h=0.08,period=3,amp=0.22` — a neon sign / lit window pulses.
- `shimmer:y=0.85,h=0.16,amp=2,speed=0.3` — water reflection ripples in a band.
- `wiggle:x=0.2,y=0.7,w=0.05,h=0.05,period=5,dur=1.6,amp=2.5` — a small region sways
  occasionally (cat tail, hanging leaves); the lower edge moves more.
- `drift:y=0.22,h=0.28,speed=5` — slow horizontal drift of a sky band (clouds); best
  on a fairly uniform sky (it wraps, so a busy band can show a seam).

**After rendering, sanity-check placement (do not skip).** Grab a frame and look:
```bash
ffmpeg -ss 5 -i instagram_videos/reel_NAME.mp4 -frames:v 1 /tmp/check.png
```
Confirm each effect sits on its real surface at a believable size — no train
floating in the sky, no shimmer on dry ground, nothing oversized. If it's off,
adjust the coords/size and **re-render before** writing the caption.

## Caption rules (Korean)
- Structure: a short re-cite/echo of one wish → one understated empathetic line
  (no preaching) → CTA to the profile link (e.g. `🌳 당신의 소원도 — 프로필 링크에서.`)
  → blank line → 8–12 hashtags, always including `#소원 #소원의나무`, mixed with
  emotional/글귀/위로 tags and any that fit the wish.
- Tone by mood: **tree** = hopeful, heart-warming; **columbarium** = gentle
  consolation for a wish that didn't come true.
- Never invent facts not in the wish; never include personal info (names, contacts).
  ≤ ~600 chars, 1–3 emoji.

## Identity (keep consistent across reels)
1080×1920 · retro **Galmuri11** Hangul pixel text, top-aligned, hard shadow ·
slow relaxing pan · film grain + vignette · brand handle `tree-of-wishes.fyi` ·
**tree** = warm rising wish-lights · **columbarium** = cool motes drifting down.

## Notes / caveats
- Reference look the user likes: lofi pixel landscapes/cities/interiors at dusk
  (see their `~/Downloads`). Match that *aesthetic* when choosing art.
- Font `static/fonts/Galmuri11.ttf` is OFL (commercial-OK), bundled with a NOTICE.
- The renderer fetches wishes over HTTP from a **private, token-gated** endpoint
  (`/api/reel/wishes`) — **no DB, runs on any machine** with the repo + `ffmpeg`
  + `pillow`/`numpy`. Requires `REEL_API_TOKEN` in the environment, matching the
  value the server is deployed with; without it the endpoint returns 404. The
  wish text is public on the site — this just keeps the tool's bulk lookup private.
- Outputs go to `instagram_videos/` which is git-ignored (they contain user wishes).
