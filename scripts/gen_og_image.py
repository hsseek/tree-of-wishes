"""Generate the Open Graph share images (static/og-{season}.png).

A zoomed-in, worm's-eye view of a tree's foliage — as if standing on the
ground looking up through the leaves — on a dusk sky, with fireflies in the
current season's colors. One image per season is produced so the server can
serve the one matching the current season; the share text lives in the page's
description, so the image carries no text. Rendered via headless Chrome. Run
once and commit the PNGs; nothing imports this at runtime.

Usage:
    .venv/bin/python scripts/gen_og_image.py
"""
import math
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

W, H = 1200, 630
CELL = 18                                  # pixel size of one art "pixel"
COLS = math.ceil(W / CELL)
ROWS = math.ceil(H / CELL)
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

# Green ramp, darkest shadow → brightest sunlit leaf.
GREENS = ["#0e3a28", "#15583a", "#1f7a4c", "#2a9560", "#39b06e", "#54cf84"]
TRUNK = "#7a4a20"
TRUNK_DK = "#543114"
TRUNK_HI = "#9a6230"

# Firefly colors mirror the Tree page's CSS variables. Per season: mostly the
# active color, some "new" lime, a few "fulfilled" white. Dying colors omitted.
SEASON_ACTIVE = {
    "spring": "#f090b8",
    "summer": "#ffa830",
    "autumn": "#c85c10",
    "winter": "#88c8f0",
}
FF_NEW = "#8fd14a"
FF_FULFILLED = "#ffffff"


def _smooth(field):
    out = {}
    for (c, r) in field:
        acc = n = 0
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                p = (c + dc, r + dr)
                if p in field:
                    acc += field[p]
                    n += 1
        out[(c, r)] = acc / n
    return out


def build_foliage():
    """Return (leaf_cells, leaf_mask). leaf_cells is a list of (c, r, color);
    sky gaps are simply left unfilled so the dusk background shows through."""
    random.seed(20)
    noise = {(c, r): random.random() for c in range(COLS) for r in range(ROWS)}
    for _ in range(3):
        noise = _smooth(noise)
    lo, hi = min(noise.values()), max(noise.values())
    noise = {k: (v - lo) / (hi - lo) for k, v in noise.items()}

    # No sky: foliage fills the whole frame. Depth comes from shaded greens and
    # dark recesses between leaf clumps (never bright gaps that read as sky).
    idx_map = {}
    for r in range(ROWS):
        for c in range(COLS):
            nx, ny = c / (COLS - 1), r / (ROWS - 1)
            dx, dy = nx - 0.5, ny - 0.05
            light = 1 - min(1.0, math.hypot(dx, dy * 1.15) * 1.3)
            # Lit from above: brightest toward the top, shaded toward the bottom.
            shade = light * 0.45 + noise[(c, r)] * 0.35 + (1 - ny) * 0.25
            idx = max(1, min(len(GREENS) - 1, 1 + round(shade * (len(GREENS) - 2))))
            # Shadowed recesses sit in the lower/inner canopy — kept dark *green*
            # for depth, and kept away from the lit top edge.
            recess = noise[(c, r)] * 0.7 + ny * 0.45
            if recess > 0.92:
                idx = 0
            elif recess > 0.84:
                idx = min(idx, 1)
            idx_map[(c, r)] = idx

    cells = [(c, r, GREENS[idx]) for (c, r), idx in idx_map.items()]
    return cells, idx_map


def _bark(cells, c, r, left, right):
    col = TRUNK_HI if c == left else (TRUNK_DK if c >= right - 1 else TRUNK)
    cells.append((c, r, col))


def _branch(cells, c0, r0, angle, length, width, curl, rnd, depth=0):
    """Walk a tapering, gently curving limb (angle in radians; -pi/2 = up). A
    round brush is stamped each step so the limb stays solid (no detached
    pixels); the long limb sprouts one sub-branch for an organic, varied look."""
    c, r, a = float(c0), float(r0), angle
    for step in range(length):
        a += curl + rnd.uniform(-0.03, 0.03)           # gradual bend + slight wobble
        c += math.cos(a)
        r += math.sin(a)
        w = max(0, round(width * (1 - step / length)))  # taper to a tip
        px, py = -math.sin(a), math.cos(a)              # perpendicular (for shading)
        for dx in range(-w, w + 1):
            for dy in range(-w, w + 1):
                if dx * dx + dy * dy > w * w + 1:
                    continue                            # round brush
                side = dx * px + dy * py                # which face of the limb
                col = TRUNK_HI if side < -0.4 else (TRUNK_DK if side > 0.4 else TRUNK)
                cells.append((round(c) + dx, round(r) + dy, col))
        if depth == 0 and length >= 12 and step == int(length * 0.5):
            _branch(cells, c, r, a - 0.85, length // 2,
                    max(1, width - 1), curl * 2.2, rnd, depth + 1)


def build_trunk():
    """A near trunk rising from the bottom-center, forking near the vertical
    middle into natural, differing branches."""
    cells = []
    rnd = random.Random(5)
    cx = COLS // 2
    fork = round(ROWS * 0.70)                     # fork sits 20% below center
    prev = 99
    for r in range(ROWS - 1, fork - 1, -1):
        frac = (ROWS - 1 - r) / (ROWS - 1 - fork)
        half = max(3, round(9 - 3.5 * frac + rnd.uniform(-0.4, 0.4)))
        half = min(half, prev)                    # only narrow upward (no nubs)
        prev = half
        for c in range(cx - half, cx + half + 1):
            _bark(cells, c, r, cx - half, cx + half)

    # Three thick limbs that differ in reach, lean, and curvature.
    _branch(cells, cx - 2, fork, angle=-2.35, length=16, width=4, curl=-0.030, rnd=rnd)
    _branch(cells, cx + 2, fork, angle=-1.05, length=12, width=4, curl=+0.060, rnd=rnd)
    _branch(cells, cx, fork - 1, angle=-1.55, length=14, width=4, curl=-0.020, rnd=rnd)
    return cells


def build_fireflies(idx_map, trunk_set, season):
    """Scatter fireflies on lit foliage (not on the trunk or in dark recesses):
    mostly the season's active color, some lime (new), a few white (fulfilled)."""
    rnd = random.Random(99)
    candidates = [(c, r) for (c, r), idx in idx_map.items()
                  if idx >= 2 and (c, r) not in trunk_set and 1 <= r <= ROWS - 4]
    rnd.shuffle(candidates)
    chosen, taken = [], set()
    for (c, r) in candidates:
        if len(chosen) >= 16:
            break
        if any((c + dc, r + dr) in taken for dc in (-1, 0, 1) for dr in (-1, 0, 1)):
            continue
        chosen.append((c, r))
        taken.add((c, r))

    active = SEASON_ACTIVE[season]
    palette = ([active] * 10) + ([FF_NEW] * 4) + ([FF_FULFILLED] * 2)
    rnd.shuffle(palette)
    return [(c, r, palette[i % len(palette)]) for i, (c, r) in enumerate(chosen)]


def rects(cells, glow=False):
    g = ' filter="url(#g)"' if glow else ""
    return "\n".join(
        f'<rect x="{c * CELL}" y="{r * CELL}" width="{CELL}" height="{CELL}" '
        f'fill="{color}"{g}/>'
        for c, r, color in cells
    )


def html(static_rects, fireflies):
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; }}
  html,body {{ width:{W}px; height:{H}px; overflow:hidden; }}
  /* Foliage fills the frame — no sky. Background matches the deepest leaf
     shade so any sub-pixel edge blends instead of flashing through. */
  body {{ background:{GREENS[0]}; }}
  svg {{ display:block; }}
  svg rect {{ shape-rendering:crispEdges; }}
</style></head><body>
  <svg width="{W}" height="{H}" viewBox="0 0 {W} {H}">
    <defs><filter id="g" x="-160%" y="-160%" width="420%" height="420%">
      <feGaussianBlur stdDeviation="7" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter></defs>
    {static_rects}
    {rects(fireflies, glow=True)}
  </svg>
</body></html>"""


def render(html_str, out_path):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     encoding="utf-8") as f:
        f.write(html_str)
        src = f.name
    subprocess.run([
        "google-chrome", "--headless=new", "--disable-gpu", "--hide-scrollbars",
        f"--screenshot={out_path}", f"--window-size={W},{H}", f"file://{src}",
    ], check=True)


def main():
    STATIC.mkdir(parents=True, exist_ok=True)
    foliage, idx_map = build_foliage()
    trunk = build_trunk()
    trunk_set = {(c, r) for c, r, _ in trunk}
    static_rects = rects(foliage) + "\n" + rects(trunk)   # season-independent

    for season in SEASON_ACTIVE:
        fireflies = build_fireflies(idx_map, trunk_set, season)
        out = STATIC / f"og-{season}.png"
        render(html(static_rects, fireflies), out)
        print(f"wrote {out}")

    # Generic fallback used when no season is known.
    shutil.copyfile(STATIC / "og-summer.png", STATIC / "og-default.png")
    print(f"wrote {STATIC / 'og-default.png'} (copy of og-summer.png)")


if __name__ == "__main__":
    main()
