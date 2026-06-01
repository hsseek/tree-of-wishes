---
name: wish-reel
description: Generate an Instagram Reel (vertical 1080x1920 lofi pixel-art video) for Tree of Wishes from a still pixel-art image + a list of wish IDs, and write its Korean caption. Use when the user wants to turn wishes into an Instagram video/reel, or says things like "make a reel / 영상 만들어 / 인스타 영상" with wish IDs and an image.
---

# Wish Reel — Instagram video generator

Turn a beautiful **still** pixel-art illustration + some wishes into a relaxing
vertical Reel: a slow Ken-Burns pan, drifting lights, film grain, and the wishes
fading in at the top in a retro Hangul pixel font — plus a ready-to-paste caption.

**Division of labor (important):** the *still art* carries the beauty — the user
supplies it (a licensed pack / commission / rights-owned AI-gen image). The code
(`scripts/video_anim.py`) adds the motion + text. Do **not** try to draw the art
procedurally — that was tried and rejected as not attractive. See
`memory/project_instagram_reel_tool.md`.

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
2. **Render** (needs `pip install -r requirements-tools.txt` once; `ffmpeg` present):
   ```bash
   .venv/bin/python scripts/video_anim.py \
     --image "PATH" --ids ID1 ID2 ID3 [--board tree|columbarium] [--focus 0.5] [--seconds 12] \
     --out instagram_videos/reel_NAME.mp4
   ```
   ~40s to render. Output is **silent** (the user adds music in Instagram).
   Wishes come from the API (default `tree-of-wishes.fyi`; override with
   `--base-url` or `$TOW_BASE_URL`) — **no local database needed**.
3. **Caption — you (Claude) write it**, no API call. Save to
   `instagram_videos/reel_NAME.caption.txt` and show it. Follow the rules below.
4. **Report**: the `.mp4` path + the caption. Remind: add music in-app, and confirm
   the art is licensed for commercial use.

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
