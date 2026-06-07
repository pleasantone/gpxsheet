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
- `layout.py` — Schematic Layout Engine (Milestone 2, pure): `build_strip_layout`
  turns the route graph into a stylized jogging ribbon + placed markers.
- `strip.py` — matplotlib renderer: `render_route_strip` / `generate_strip`
  → `route_strip.png`. matplotlib imported lazily; uses Agg backend.
- `report.py` — `analyze` text output. `cli.py` — typer CLI
  (generate/analyze/strip/validate).

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

## Status & next steps (M1 done; M2 first iteration done)

**M1 validation done (full real tracks, not just clips):** geometry-only sweep
over all ~18 samples runs without crashes (bad-xml.gpx correctly rejected). Full
`--osm` runs verified on gaia (75mi→22 decisions, 39s), inroute (93mi→16, 121s),
ich-dual-gas (172mi→32, 31s, 0.19/mi). Twisty roads collapse correctly — Mines
Road becomes ONE 27.8mi segment. Timing scales with length + urban density.

**M2 first iteration:** schematic strip renders cleanly on synthetic routes.
Stylized turns (default) + faithful option; outward-normal label placement with
repulsion off other labels / the route line / all marker dots; dashed leaders;
2-line wrapped road names. Tuned: `MIN_SEGMENT_LEN=2.6`, `DIST_SCALE=1.0`,
stylized angles 10/30/55°. NOTE: only reviewed on synthetic routes + the earlier
Mt-Hamilton OSM clip — NOT yet stress-tested on dense real routes.

### Strip / Milestone 2 TODO (resume here)
- **Stress-test the strip on dense real routes** (10+ decisions, e.g. full
  scenic/ich/basecamp via `--osm`, and a geometry-only flood case) to see where
  label placement breaks; then harden. Highest priority for the strip.
- **Label de-collision** is a heuristic repulsion pass (`_place_labels_with_leaders`
  in strip.py). May still bunch on very dense routes. Possible improvements:
  leader routing, smarter side selection, capping labels shown per page.
- **Reassurance town labels** (Stewarts Point/Yorkville) render small/gray —
  decide on prominence; generic "N mi" markers are ticks only (intentional).
- **Ribbon vs inline labels redundancy** — the bottom `A › B › C` ribbon repeats
  the inline road names; consider restyling or dropping one.
- **Tuning knobs** to revisit with real data: stylized angles
  (`CONTINUE/NORMAL/SHARP_TURN_DEG`), compression (`MIN_SEGMENT_LEN`,
  `DIST_SCALE`), and placement constants (`_OFFSET/_REPEL/_LINE_REPEL/...`) in
  strip.py. Compare `--turns stylized` vs `--turns faithful`.
- **Heading drift on long routes** — stylized bends accumulate; a route with many
  same-direction turns may curl. Watch for it in stress-testing; may need gentle
  relaxation toward horizontal.

### Analysis / OSM TODO
- **Possible OSM nondeterminism near the durability threshold.** Same 40mi Mt
  Hamilton clip gave 6 decisions one run, 5 the next (San Antonio Valley Road,
  a ~0.3mi run right at `MIN_ROAD_RUN_MILES`, flipped). Investigate determinism /
  add hysteresis. (Could not finish checking — live OSM was hanging.)
- **Live Overpass hangs intermittently in this sandbox.** For strip/analysis
  iteration prefer deterministic synthetic Routes or cached results; don't block
  on `--osm`.
- **Down-weight straight "Continue onto" road-name changes** (residential
  stretches emit many; lower nav value than turns). Needs a ground-truth set.
- **Junction-degree detection** — catch nameless forks (OSM node topology).

### Then
- **Milestone 3** — PDF generation (`generate_pdf` is a stub): compose the strip
  + cue blocks + road ribbon + progress indicator per page, route-aware pagination
  (which also relieves strip label crowding by showing fewer features per page).
- Wire a vault project note via `/project-init` (Obsidian MCP was hanging).

## Conventions

- Commit messages end with the Co-Authored-By trailer; commit/push when asked.
- Keep ruff clean and tests green before committing. Typer needs `B008` ignored
  (already in pyproject). Use `zip(..., strict=...)` explicitly.
