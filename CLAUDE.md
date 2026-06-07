# GPXSheet — project context for Claude

GPXSheet converts GPX routes into glanceable, map-centric **motorcycle tank-bag
navigation PDFs** (sport-touring). Full design spec + as-built engineering notes
live in [PRODUCT.md](PRODUCT.md) — read its "Implementation Status & Engineering
Notes" section first when resuming.

- **Repo:** private GitHub `pleasantone/gpxsheet`, default branch `main`.
- **Owner:** Paul Traina.
- **Python:** 3.14, project-local `.venv` (NOT `~/.venv`, which is an unrelated
  scraping env). Activate: `source .venv/bin/activate`.

## Commands

```bash
.venv/bin/ruff check .          # lint (must pass; CI runs it)
.venv/bin/pytest -q             # 36 tests, all should pass
GPXSHEET_LIVE_OSM=1 .venv/bin/pytest tests/test_enrich.py::test_enrich_route_live_against_osm
.venv/bin/gpxsheet analyze examples/sample_route.gpx --fuel-range 6
.venv/bin/gpxsheet analyze <real>.gpx --osm    # OSM road names/fuel (needs [osm] extra, network)
```

Install: `pip install -e ".[dev]"` (core) and `pip install -e ".[osm]"` (OSM stack;
osmnx 2.1 + geopandas — installs fine on 3.14).

## Architecture (src/gpxsheet/)

- `geo.py` — haversine, bearings, cumulative distance (pure, 100% covered).
- `models.py` — Route graph dataclasses (Route, Segment, DecisionPoint, …).
- `gpx.py` — `load_route()` parses track/route/waypoints via gpxpy.
- `simplify.py` — Ramer–Douglas–Peucker geometry cleanup.
- `analysis.py` — the engine: `analyze_route()` orchestrates; geometry turn
  detection (`detect_decision_points`), `merge_close_decisions`,
  reassurance markers, fuel, `build_segments`. Shared helpers `coord_at_meters`
  (interpolates), `turn_angle_at_mile`. Tuning constants live at top of file.
- `enrich.py` — optional OSM (osmnx). Durable road-name-change decisions
  (`_durable_runs`, `_decisions_from_runs`), segments from named roads, fuel.
- `profiles.py` — minimalist / sport-touring / rally thresholds + score table.
- `report.py` — `analyze` text output. `cli.py` — typer CLI (generate/analyze/validate).

`analyze_route` flow: geometry detect → merge → build segments → **if --osm**
enrich (replaces decisions+segments with OSM-derived) → apply profile threshold
→ fuel report + reassurance.

## Key decisions (don't re-litigate without reason)

- **Decision detection is two-tier.** Pure geometry floods twisty roads (can't
  tell a curve from a junction — Mt Hamilton Rd gave 100+ false turns). OSM mode
  detects decisions from *durable* road-name changes (Rule Set 1). This was
  validated against real Bay Area tracks in `~/gpxtable/samples/`.
- Tuning constants tuned via threshold sweeps on real tracks: `MIN_ROAD_RUN_MILES
  =0.3`, `MERGE_MIN_SEPARATION_MILES=0.2`, `TURN_ANGLE_THRESHOLD_DEG=35`,
  `MAX_TURN_ARC_M=90`, `CONTINUE_MAX_ANGLE_DEG=25`.
- OSM = live Overpass; slow in dense urban (≈140s for 5mi SF) vs ≈3s rural.
  Integration test gated behind `GPXSHEET_LIVE_OSM=1` so CI stays offline.

## Test data

Real GPX samples: `/Users/pst/gpxtable/samples/*.gpx` (gaia, scenic,
ich-dual-gas=Mt Hamilton, basecamp-tracks, …). `bad-xml.gpx` is intentionally
malformed (loader rejects it). `examples/sample_route.gpx` is synthetic (offshore
— no OSM coverage, don't use with --osm).

## Status & next steps (Milestone 1 done)

Open work, roughly prioritized:
1. **Broaden validation** — run full real tracks (not just clips) through `--osm`,
   characterize results/timing. (in progress when this note was written)
2. **Junction-degree detection** — catch nameless forks (OSM node topology),
   the main known gap in decision detection.
3. **Milestone 2** — schematic map-strip renderer (`route_strip.png`).
4. **Milestone 3** — PDF generation (`generate_pdf` is currently a stub).
5. Wire a vault project note via `/project-init` (Obsidian MCP was hanging when
   this was written, so it was deferred).

## Conventions

- Commit messages end with the Co-Authored-By trailer; commit/push when asked.
- Keep ruff clean and tests green before committing. Typer needs `B008` ignored
  (already in pyproject). Use `zip(..., strict=...)` explicitly.
