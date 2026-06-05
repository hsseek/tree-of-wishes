---
name: wish-reel
description: Generate an Instagram Reel (vertical 1080x1920 lofi pixel-art video) for Tree of Wishes from a still pixel-art image + a list of wish IDs, generate original lo-fi background music, and write its Korean caption. Use when the user wants to turn wishes into an Instagram video/reel, or says things like "make a reel / 영상 만들어 / 인스타 영상" with wish IDs and an image.
---

# Wish Reel — Instagram video generator

Turn a beautiful **still** pixel-art illustration + some wishes into a relaxing
vertical Reel: a static (no-pan) frame with the wishes fading in at the top in a
retro Hangul pixel font, **the only motion being the warm wish-lights drifting
upward** (cool motes for columbarium), film grain + vignette — plus a sweep of
**original lo-fi music** to choose from, and a ready-to-paste caption.

**Task 3 of a 3-stage pipeline:** Task 1 = generate the original scene with an
external image tool (Nano Banana / Midjourney; Claude only supplies prompts).
Task 2 = `wish-pixelize` (image → pixel-art candidates, pick one). Task 3 (this) =
animate the chosen pixel image + wishes into a Reel. Input `--image` is normally
the picked `wish-pixelize` output.

**Division of labor (important):** the *still art* carries the beauty — the user
supplies it (AI-gen + pixelized). The code adds the wish-lights + text + music.
Do **not** try to draw the art procedurally — that was tried and rejected as not
attractive. See `memory/project_instagram_reel_tool.md`.

## Inputs
- **image** — path to a clean (no watermark), commercially-licensed lofi pixel-art
  still. Vertical art is ideal; landscape works (a vertical crop is taken).
- **wish IDs** — the numbers from `/wish/{id}` URLs (e.g. `123` from
  `tree-of-wishes.fyi/wish/123`). `Wish.id` is the indexed primary key.
- optional: mood (`tree` warm / `columbarium` wistful) — **default: infer from the
  wishes' board**; `--focus 0..1` to aim the crop at an off-centre subject.

## Duration scales with message length (deliberate)
Each wish's on-screen time is **set dynamically from its text length** so viewers
can actually read long messages — a short wish gets ~2–3s, a long one stays up
much longer (reading speed ≈ `--cps` chars/sec, default 6). The **total video
length is therefore dynamic** (the sum of per-wish reading times) and is printed
by the renderer. Tune with `--cps` (lower = slower/longer), `--min-hold`,
`--max-hold`. Only pass `--seconds` if you need a *fixed* total — it then splits
that budget across wishes still **in proportion to their length**. Because the
length varies, **generate the music to match the rendered video's duration**
(see Step 3).

## Motion policy (deliberate — keep it minimal)
The reel has **no ambient effects and no Ken-Burns pan**. The *only* animation is
the built-in mood particles:
- **tree** → warm wish-lights drifting **upward** (fireflies).
- **columbarium** → cool motes drifting **down**.

These come for free from the renderer — there is nothing to place or tune. Do
**not** add `--fx` effects (rain/train/steam/twinkle/swing/…); they still exist in
`scripts/video_anim.py` but are intentionally **off** for this look. Always pass
`--no-pan`. (If the user explicitly asks for a pan or a specific effect back, you
can, but the default is just the wish-lights + music.)

## Steps
1. **Mood is auto-inferred** from the wishes' board — the engine fetches each wish
   from the live API, so just leave `--board auto` (default). Only pass
   `--board tree|columbarium` if the engine reports the wishes span both boards
   (then split into two reels, or pick one).
2. **Render the (silent) video** — wish-lights only, no pan; per-wish duration is
   auto-scaled to message length (needs `pip install -r requirements-tools.txt`
   once; `ffmpeg` present):
   ```bash
   .venv/bin/python scripts/video_anim.py \
     --image "PATH" --ids ID1 ID2 ID3 --no-pan [--focus 0.5] [--cps 6] \
     --out instagram_videos/reel_NAME.mp4
   ```
   ~40–60s to render. **Don't hardcode `--seconds`** — the length is dynamic; the
   renderer prints the total. Output is **silent** (music is added next). Wishes
   come from the API (token-gated; needs `REEL_API_TOKEN`) — **no local DB**.
3. **Always generate 3 lo-fi music candidates and let the USER pick.** Every time
   you make a video, produce all three and present them by name/blurb — **never
   auto-select, never skip this, and never decide for the user.** The user picks
   the one they find most appealing themselves. Match `--mood` to the reel's mood
   and `--seconds` to the **rendered video's actual duration** (read it back,
   don't guess):
   ```bash
   DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 \
         instagram_videos/reel_NAME.mp4)
   .venv/bin/python scripts/lofi.py --mood tree --seconds "$DUR" \
     --out-prefix instagram_videos/reel_NAME.track
   # -> reel_NAME.track_c1.wav (Warm Keys) / _c2.wav (Chill Beat) / _c3.wav (Dreamy Pad)
   ```
   The three presets are fixed (it's fine to re-offer the same tunes across
   reels). The audio is **original** (synthesized, no samples) → safe for
   commercial use. To re-render a single one at a tweaked length, add
   `--candidate c2`. **Then stop and wait for the user's choice** before muxing.
4. **Mux the chosen track into the mp4** (auto, with ffmpeg) — only after the
   user has named one (e.g. `c2`):
   ```bash
   ffmpeg -y -i instagram_videos/reel_NAME.mp4 \
     -i instagram_videos/reel_NAME.track_c2.wav \
     -c:v copy -c:a aac -b:a 192k -shortest \
     instagram_videos/reel_NAME.final.mp4
   ```
   `-shortest` trims audio to the video length (the track is already generated to
   `--seconds`, so they match). `reel_NAME.final.mp4` is the ready-to-post video.
5. **Caption — you (Claude) write it**, no API call. Save to
   `instagram_videos/reel_NAME.caption.txt` and show it. Follow the rules below.
6. **Report**: the `.final.mp4` path + the caption. Confirm the art is licensed for
   commercial use (the music is original, so it's already cleared).

## Caption rules (Korean)
- Structure: a short re-cite/echo of one wish → one understated empathetic line
  (no preaching) → CTA with the site link (`🌳 https://tree-of-wishes.fyi 🌳`)
  → blank line → 8–12 hashtags, always including `#소원 #소원의나무`, mixed with
  emotional/글귀/위로 tags and any that fit the wish.
- Tone by mood: **tree** = hopeful, heart-warming; **columbarium** = gentle
  consolation for a wish that didn't come true.
- **Use emoji generously** (≈6–12): sprinkle them inline and at line ends across
  the echo line, the empathetic line, and the CTA, matched to the wish's mood —
  e.g. tree `🌳✨🙏🍀💪📖🕯️☕🌙`, columbarium `🤍🕊️🌙💫🌷`. Keep them tasteful
  (don't wall-of-emoji or break the reading flow).
- Never invent facts not in the wish; never include personal info (names, contacts).
  ≤ ~600 chars.

## Attribution (named vs anonymous wishes)
Each wish from the API carries a `name` field: a string when the wisher signed it,
`null`/empty when they posted **anonymously**. The renderer draws an attribution
line `— {name}` just under the wish (smaller, warm-gold Galmuri) **only when the
name is non-empty** — anonymous wishes show the text alone, no placeholder. This
is automatic; there is nothing to pass. It is **not** a contradiction of the "no
personal info" caption rule: that rule governs *the caption you write*; the
on-screen name is the public, wisher-chosen signature already shown on the site.

## Identity (keep consistent across reels)
1080×1920 · retro **Galmuri11** Hangul pixel text, top-aligned, hard shadow ·
named wishes get a warm-gold `— 이름` attribution line (anonymous show none) ·
**static frame** (no pan) · film grain + vignette · brand handle `tree-of-wishes.fyi` ·
**tree** = warm wish-lights rising · **columbarium** = cool motes drifting down ·
original lo-fi soundtrack.

## Notes / caveats
- Reference look the user likes: lofi pixel landscapes/cities/interiors at dusk
  (see their `~/Downloads`). Match that *aesthetic* when choosing art.
- Font `static/fonts/Galmuri11.ttf` is OFL (commercial-OK), bundled with a NOTICE.
- Music: `scripts/lofi.py` synthesizes original Rhodes/bass/beat/pad + vinyl hiss
  (no samples, no licensing). 3 candidates per run; `--candidate cN` re-renders one.
- The renderer fetches wishes over HTTP from a **private, token-gated** endpoint
  (`/api/reel/wishes`) — **no DB, runs on any machine** with the repo + `ffmpeg`
  + `pillow`/`numpy`. Requires `REEL_API_TOKEN` in the environment, matching the
  value the server is deployed with; without it the endpoint returns 404. The
  wish text is public on the site — this just keeps the tool's bulk lookup private.
- Outputs go to `instagram_videos/` which is git-ignored (they contain user wishes).
