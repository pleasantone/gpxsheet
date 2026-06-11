#!/usr/bin/env python3
"""Generate the brand glyph: the PWA / home-screen app icons (PNG) plus the
in-app vector logo (SVG), all in frontend/public/.

The glyph is a placeholder: brand-orange background with a stylized white route
polyline and two waypoint dots. This is the single source for the mark — the SPA
references the generated icon.svg for its header logo, favicon, and idle hero, so
don't re-encode the geometry by hand elsewhere. Tweak the glyph here and re-run:

    .venv/bin/python scripts/gen_app_icons.py

The glyph is kept inside the central ~60% so the "maskable" manifest icons crop
safely on Android adaptive-icon launchers. iOS rounds the apple-touch-icon
itself, so all icons are full-bleed (no transparent corners). matplotlib writes
SVG from a .svg path extension, so the same drawing code yields the vector logo.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

BRAND = "#e85d04"
PUBLIC = Path(__file__).resolve().parent.parent / "frontend" / "public"


def make_icon(path: Path, px: int) -> None:
    fig = plt.figure(figsize=(px / 100, px / 100), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.add_patch(plt.Rectangle((0, 0), 1, 1, color=BRAND, zorder=0))

    xs = [0.27, 0.40, 0.46, 0.58, 0.66, 0.74]
    ys = [0.30, 0.40, 0.58, 0.50, 0.66, 0.74]
    ax.plot(
        xs, ys, color="white", lw=px * 0.045,
        solid_capstyle="round", solid_joinstyle="round", zorder=1,
    )
    ax.scatter([xs[0], xs[-1]], [ys[0], ys[-1]], s=(px * 0.13) ** 2, color="white", zorder=2)
    ax.scatter([xs[0], xs[-1]], [ys[0], ys[-1]], s=(px * 0.07) ** 2, color=BRAND, zorder=3)

    fig.savefig(path, dpi=100)
    plt.close(fig)
    print(f"wrote {path}")


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    make_icon(PUBLIC / "icon-192.png", 192)
    make_icon(PUBLIC / "icon-512.png", 512)
    make_icon(PUBLIC / "apple-touch-icon.png", 180)
    # Vector logo for the SPA (header, favicon, idle hero). px sets the geometry
    # reference only; SVG output is resolution-independent.
    make_icon(PUBLIC / "icon.svg", 512)


if __name__ == "__main__":
    main()
