"""Generate the default Open Graph share image (static/og-default.png).

Pixel-art tree in the favicon's palette on a calm dusk sky with fireflies,
rendered to a 1200x630 PNG via headless Chrome. Run once and commit the PNG;
nothing imports this at runtime.

Usage:
    .venv/bin/python scripts/gen_og_image.py
"""
import math
import random
import subprocess
import tempfile
from pathlib import Path

W, H = 1200, 630
CELL = 18                       # pixel size of one art "pixel"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "og-default.png"

# Palette lifted from static/favicon.svg.
GREENS = ["#1a6a40", "#268a56", "#2a9060", "#33a86a", "#3ec070"]
TRUNK = "#8c5522"
TRUNK_DARK = "#7a4820"
GLOW = "#ffe9a8"

random.seed(7)


def build_cells():
    """Return list of (col, row, color) art pixels for the tree + fireflies."""
    cells = []
    cols, canopy_rows = 30, 19
    # Canopy = union of a main ellipse and a few offset bumps for an organic edge.
    blobs = [(14.5, 8.0, 14.0, 8.5), (8.0, 9.0, 6.0, 6.0),
             (21.0, 9.0, 6.5, 6.0), (14.5, 4.5, 9.0, 5.5)]

    def inside(c, r):
        return any(((c - bx) / rx) ** 2 + ((r - by) / ry) ** 2 <= 1.0
                   for bx, by, rx, ry in blobs)

    for r in range(canopy_rows):
        for c in range(cols):
            if not inside(c, r):
                continue
            edge = not (inside(c - 1, r) and inside(c + 1, r)
                        and inside(c, r - 1) and inside(c, r + 1))
            # Light from the top-left: pick a greener shade higher/left, plus noise.
            t = (c + r) / (cols + canopy_rows)
            idx = int((1 - t) * (len(GREENS) - 1) + random.uniform(-0.8, 0.8))
            idx = max(0, min(len(GREENS) - 1, idx))
            if edge:
                idx = max(0, idx - 1)   # darker outline
            cells.append((c, r, GREENS[idx]))

    # Trunk: a tapering bar below the canopy, darker on the right edge.
    trunk_top = canopy_rows - 1
    for i, r in enumerate(range(trunk_top, trunk_top + 7)):
        half = 1 if i < 4 else 2          # flare out near the base
        for c in range(14 - half, 15 + half + 1):
            color = TRUNK_DARK if c >= 15 + half else TRUNK
            cells.append((c, r, color))

    # Fireflies (wishes) glowing in and above the canopy.
    for c, r in [(6, 4), (22, 6), (12, 2), (18, 11), (10, 13), (25, 12), (3, 8)]:
        cells.append((c, r, GLOW))

    return cells


def svg_rects():
    parts = []
    for c, r, color in build_cells():
        x, y = c * CELL, r * CELL
        glow = ' filter="url(#g)"' if color == GLOW else ""
        parts.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                     f'fill="{color}"{glow}/>')
    return "\n".join(parts)


def html():
    tree_w = 30 * CELL
    tree_h = 26 * CELL
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{W}px; height:{H}px; overflow:hidden; }}
  body {{
    display:flex; align-items:center; gap:30px; padding:0 60px;
    font-family:'Pretendard','Apple SD Gothic Neo',sans-serif;
    background:radial-gradient(120% 140% at 75% 10%, #2a5d6e 0%, #1c3a52 45%, #14233b 100%);
    color:#f3f7f4;
  }}
  .art {{ flex:0 0 auto; }}
  svg rect {{ shape-rendering:crispEdges; }}
  .copy {{ flex:1 1 auto; }}
  .ko {{ font-size:88px; font-weight:800; letter-spacing:-2px; line-height:1.05;
         white-space:nowrap; text-shadow:0 2px 18px rgba(0,0,0,.35); }}
  .en {{ font-size:40px; font-weight:600; opacity:.85; margin-top:14px; letter-spacing:.5px; }}
  .tag {{ font-size:30px; opacity:.7; margin-top:26px; }}
</style></head><body>
  <div class="art">
    <svg width="{tree_w}" height="{tree_h}" viewBox="0 0 {tree_w} {tree_h}">
      <defs><filter id="g" x="-120%" y="-120%" width="340%" height="340%">
        <feGaussianBlur stdDeviation="7" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter></defs>
      {svg_rects()}
    </svg>
  </div>
  <div class="copy">
    <div class="ko">소원의 나무</div>
    <div class="en">Tree of Wishes</div>
    <div class="tag">나무에 소원을 달아보세요</div>
  </div>
</body></html>"""


def main():
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     encoding="utf-8") as f:
        f.write(html())
        src = f.name
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "google-chrome", "--headless=new", "--disable-gpu", "--hide-scrollbars",
        f"--screenshot={OUT}", f"--window-size={W},{H}", f"file://{src}",
    ], check=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
