# Build Spec: "Tree of Wishes" web service

Build a web service called **Tree of Wishes** — an anonymous, public wish bulletin board with a whimsical retro-pixel-art aesthetic. This document is the complete specification. Where it leaves a choice to you, make a sensible decision and note it in the README.

---

## 0. Your decisions to make

- **Backend language/framework**: your choice (e.g. Node.js, Python/FastAPI, Go). Pick something well-suited to a small full-stack app with a responsive frontend and easy local dev.
- **Database**: your choice. It must handle two separate stores of up to 10,000 records each with frequent reads, counters (likes/views), and ordering queries.
- **Frontend**: your choice of approach, but the grid must be a **single reusable component** (see §4).
- Document every choice and the reasoning in the README.

The app is in a **test phase**. Optimize for a clean, runnable local setup and a deploy that can later go to a temporary URL. Do not over-engineer infrastructure.

---

## 1. Pages & routes

1. **Tree of Wishes** (`/tree`, also the home page) — the active board. Light theme. Editable.
2. **Columbarium** (`/columbarium`) — view-only memorial board for "dead" wishes. Dark theme.
3. **Settings** (`/settings`) — at minimum a language switcher (see §9).
4. **About** (`/about`) — a placeholder page explaining the concept.
5. **My Wishes** (`/my-wishes`) — see §8; build the route as a stub gated behind the (not-yet-implemented) auth.

The Tree and Columbarium **share one reusable grid component** rendered on two routes, parameterized by a theme prop and a data-source prop. This is the intended way to satisfy the "reuse the same table" goal — same component, two routes, different theme + dataset. Do **not** build a single page that toggles state. Aim for fast, seamless loads (lightweight assets, efficient queries, lazy-loaded art).

---

## 2. Data model — the Wish

A wish has:

- `id`
- `text` — **required**. The wish content.
- `name` — optional. Display name of the author.
- `attachment` — optional. A single uploaded file with a **size limit** (you choose a sensible cap, e.g. 5 MB, and enforce server-side). Validate type sensibly.
- `password_hash` — required for anonymous authors; **hashed** with bcrypt or argon2, never stored in plain text. Used only to verify edit/delete rights — it can never be recovered or displayed. (Registered users won't need a password — see §8.)
- `due_date` — **required**.
- `status` — `active` | `fulfilled` (on the Tree) or `dead` (in the Columbarium).
- `created_at` — upload timestamp.
- `fulfilled_at` — timestamp when marked fulfilled (null otherwise).
- `likes` — integer counter.
- `views` — integer counter.
- `owner_id` — nullable foreign key for a future registered user (see §8). Null for all wishes now.

**Forgotten passwords are unrecoverable by design. This is acceptable and intended.**

---

## 3. Two separate stores, each capped at 10,000

There are **two independent capacities of 10,000**: one for the Tree (active + fulfilled wishes), one for the Columbarium (dead wishes). They do not share a budget.

### Ordering key
Both boards display **oldest first** (oldest at the top, scrolling down to newer).

The ordering key for a Tree wish is:
- `fulfilled_at` if the wish is fulfilled,
- otherwise `created_at`.

So marking a wish fulfilled makes it "younger": its position moves later and it drifts away from the deletion edge. (Implement this as an effective-age key used for both display ordering and replacement selection.)

The Columbarium orders by `created_at` (the original upload date is preserved when a wish moves there — see §6).

### Replacement rules when a store is full
- **Tree full (10,000):** a new wish removes the single **oldest** wish by the effective-age key. That removed wish is **permanently deleted** — it does **not** go to the Columbarium. (Only expiry sends wishes to the Columbarium; see §6.)
- **Columbarium full (10,000):** a new dead wish removes the **least popular** entry, where popularity = **fewest likes**. **Ties break by oldest `created_at`.**

> Note for the future: once registration exists, registered users' wishes should be protected from age-based deletion. Leave a clear extension point (e.g. a check on `owner_id`) but do not implement protection now, since there are no registered users yet.

---

## 4. The grid component

The grid is implemented as two distinct layouts — one per board — exposed through a shared `WishGrid` JS class that delegates to the appropriate implementation.

### Tree of Wishes — Firefly Canvas

Wishes are scattered across a tall absolutely-positioned canvas (not a CSS grid). Each wish is an animated ✦ glyph floating via a **Lissajous path** (two nested divs each animating `translateX`/`translateY` at independently randomised periods, producing elliptical or figure-8 drifts). Each glyph also flickers with a randomised opacity animation.

- **Active wishes**: warm amber-orange ✦, small glow.
- **Fulfilled wishes**: pure white ✦, larger (32 px vs 20 px), radiant multi-layer golden halo.
- **Keyword bubble**: each wish displays a small label below the glyph containing the first meaningful non-stop-word extracted from the wish text, followed by the uploader's first name if available (e.g. `peace · Mia`). Extraction runs entirely client-side.
- **Hover popover**: hovering any wish shows a floating card (no click required) with status, name, up to 180 chars of text, due date, likes, and views. The popover auto-flips below the anchor if the top would clip the viewport.
- **Scatter placement**: a Poisson-like algorithm distributes points across the canvas attempting a minimum inter-wish distance, falling back to the best available position after 40 attempts.
- **Pagination**: all pages are loaded upfront (cap 20 API pages) then rendered in one pass. A "Load more" button appears at the canvas bottom if more pages exist.
- **No decorative gaps**: wishes are scattered organically; visual breathing room comes from the scatter algorithm and the canvas height, not placeholder cells.

### Columbarium — Stone Niche Wall

Dead wishes are rendered as a dense **flex-wrap** layout of stone-carved niches:

- Each niche shows: ember glyph (◈, pulsing animation), uploader name (or `—` for anonymous), extracted keyword, and likes counter.
- Sequential fill — no empty placeholder cells; the flex layout naturally avoids trailing grid gaps.
- Niches are sized to fit a single keyword line, making the wall dense.
- Niches are filled in order (oldest first, matching the Columbarium's display ordering).
- Pagination: each "Load more" action appends new niches in-place without re-rendering existing ones.

### Shared hover popover

Both boards share a single `WishPopover` instance (one DOM element repositioned per hover). `pointer-events: none` ensures it never blocks interaction.

### Clicking a wish → modal
Opening a wish shows a modal with:
- the full wish `text`,
- the `name` if present,
- the `attachment` if present — images display as a thumbnail; other files show a download link,
- the `due_date`, `likes`, and `views` (view count is tracked and shown to users),
- a **Like** button (see §7),
- **(Tree only)** a **password input**. If the entered password verifies against `password_hash`, the user may then:
  - edit the `text`,
  - replace or remove the `attachment`,
  - toggle the **fulfilled** status,
  - delete the wish.
- **(Columbarium)** the modal is **view-only** except for liking (and view counting). No password field, no edits.

Opening a wish increments its `views` (deduped per IP per wish per 24 h — see §7).

---

## 5. Fulfilled wishes (Tree only)

- A logged-out user with the correct password (or, later, the owner) can mark a wish **fulfilled**.
- A fulfilled wish **stays on the Tree** as a brighter, larger white ✦ with a radiant golden halo. It **never** moves to the Columbarium.
- Its effective age is recounted from `fulfilled_at`, per §3.
- It is only ever removed when the Tree is full and it happens to be the oldest by effective age.
- **Attachments** can only be added at fulfillment time (not at initial creation), and only by anonymous users with the correct password. Registered users (future) may attach at any time.

---

## 6. Expiry → Columbarium

- A wish whose `due_date` has passed **and that is not fulfilled** becomes "dead" and moves to the Columbarium.
- **Trigger timing**: this transition happens **lazily, only when a page is next visited** (no background cron/scheduler). On page load, sweep for expired-and-unfulfilled wishes and migrate them. Keep this efficient.
- On migration, the wish **keeps all information**: text, name, attachment, likes, views, `created_at`, `password_hash`.
- In the Columbarium a dead wish is **view-only** but **still accumulates likes and views**. These likes determine survival under the Columbarium's replacement rule (§3).

---

## 7. Likes, views & abuse prevention

- A wish can be liked from **both** the Tree and the Columbarium.
- Views are tracked on both boards and shown to users.
- **Abuse prevention is IP-based rate limiting + deduplication only. No CAPTCHA.**
  - **Likes**: one like per IP per wish (dedup). Optionally a soft rate cap on like actions per IP per time window.
  - **Wish creation**: rate-limit creations per IP per time window (you choose sensible numbers; document them).
  - **Views**: dedup per IP per wish within a reasonable window so counts aren't trivially inflated.
- Enforce all rate limiting **server-side**.

---

## 8. Registration (architecture now, implementation later)

Registration is **not implemented in the initial commit**, but the architecture must support adding it cleanly later (option (a)):

- Include a `users` table / model and a nullable `owner_id` on wishes from the start.
- Plan for **OAuth (Google) sign-in** as the intended first method; structure auth so this can be dropped in without a schema migration headache.
- When registration eventually exists:
  - a registered user leaving a wish does **not** need a password,
  - they manage their wishes on **My Wishes** (`/my-wishes`),
  - their wishes will later be protected from age-based deletion.
- For now: build the `/my-wishes` route as a stub behind a disabled/placeholder auth gate. All wishes have `owner_id = null`. All anonymous wishes still require a password.

---

## 9. Internationalization

- **Bilingual from the start: English and Korean (en / ko).**
- All UI strings go through an i18n layer (no hardcoded user-facing text).
- Language switcher lives in **Settings** (and ideally a quick toggle in the header). Persist the choice (cookie/localStorage).
- Pick a sensible default (e.g. browser language, falling back to English).

---

## 10. Art & theming

**Tree of Wishes (light theme, `#e8f4ee` background):**
- Each wish is a ✦ glyph animated with a Lissajous floating path (two independent sine-wave translations at randomised periods: 28–72 s on X, 20–56 s on Y) and a slow opacity flicker (6–16 s period). All animation parameters are randomised per wish so no two fireflies move identically.
- Active: warm amber-orange (`#ffa830`) with a soft glow.
- Fulfilled: pure white (`#ffffff`), 32 px, with a 6-layer radiant golden halo.
- A small keyword label (9 px, 70% opacity) floats below the glyph.
- The background colour (`#e8f4ee`) extends the full scrollable height of the page (body uses `min-height: 100vh`).

**Columbarium (dark theme, `#08061a` background):**
- The niche wall is a flex-wrap block styled to look like a carved stone structure: dark mortar (`#060414`) between cells, bevelled borders on each niche (darker top-left / lighter bottom-right), deep inset shadow.
- Each niche has a pulsing ember glyph (◈) with randomised animation timing.
- Hover glows the niche with a warm amber outline.

Both boards share a hover popover (fixed-position, `pointer-events: none`, auto-flips near viewport edges).

Keep assets lightweight to preserve fast loads.

---

## 11. Search (both boards)

- A search feature on **both** pages.
- **All wishes are public and visible to everyone.** Search is **public search over all wishes** — not a private "find only mine" lookup.
- Search matches against **both** the wish `text` **and** the `name` field.
- Search **covers both stores together** (active/fulfilled Tree wishes **and** dead Columbarium wishes), so an anonymous author can find their own message regardless of which board it now lives on. Make clear in results which board each hit belongs to, and let the user jump to it.

---

## 12. Deliverables

- A runnable full-stack app with the two boards, shared grid component, modal, search, likes/views, expiry-on-visit migration, both replacement rules, file upload with size limit, hashed passwords, and IP-based rate limiting + dedup.
- en/ko i18n wired throughout.
- Placeholder retro pixel-art for both themes.
- A **README** covering: chosen stack and why, how to run locally, env/config, where the future registration + Google OAuth hooks live, all chosen numeric limits (file size, rate limits, dedup windows), and any assumptions you made.
- Seed script that generates sample wishes (active, fulfilled, and dead) so the boards and replacement logic can be exercised immediately.

---

## Summary of the trickiest rules (do not get these wrong)

1. **Two separate 10,000 caps** — Tree and Columbarium are independent.
2. **Effective age on the Tree** = `fulfilled_at` if fulfilled, else `created_at`; used for both ordering and "delete oldest."
3. **Tree-full deletion is permanent** — the evicted wish is **not** sent to the Columbarium.
4. **Only expiry-while-unfulfilled** sends a wish to the Columbarium, and only **on next page visit**.
5. **Columbarium-full eviction = fewest likes**, ties broken by oldest `created_at`.
6. **Fulfilled wishes never enter the Columbarium**; they stay on the Tree as brighter fruit.
7. **No decorative gap cells** — the Tree uses Poisson-like scatter placement for organic spacing; the Columbarium uses sequential dense fill with no placeholder cells.
8. **Passwords hashed and unrecoverable** by design.
