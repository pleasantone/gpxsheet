#!/usr/bin/env python3
"""Generate the PWA / home-screen app icons in frontend/public/.

These are placeholders: brand-orange background with a stylized white route
polyline and two waypoint dots. Swap in real artwork by replacing the PNGs (keep
the same filenames/sizes) — or tweak the glyph here and re-run:

    .venv/bin/python scripts/gen_app_icons.py

The glyph is kept inside the central ~60% so the "maskable" manifest icons crop
safely on Android adaptive-icon launchers. iOS rounds the apple-touch-icon
itself, so all icons are full-bleed (no transparent corners).
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


if __name__ == "__main__":
    main()
