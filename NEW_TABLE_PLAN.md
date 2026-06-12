# Native Route Table — implementation plan

Re-implement GPXtable's route-table output **natively inside gpxsheet**, driven
by the analyzed `Route` graph instead of wrapping `GPXTableCalculator`. This lets
the table inherit gpxsheet's OSM enrichment (auto-discovered fuel, real road
names, road-snapped distance) and adds the temporal layer (ETA/layover/sun) that
gpxsheet's analysis currently lacks.

## Locked design decisions (from Paul)

1. **gpxtable dependency:** *absorb the logic, keep gpxtable as a test oracle.*
   Reimplement natively; keep `gpxtable` as a dep so its output can be diffed for
   parity during migration; drop the runtime dep only at the very end.
2. **Output format:** *match gpxtable's columns first.* Reproduce the
   `| Name | Dist. | GL | ETA | Notes` layout + header/separator/row formatting so
   gpxtable output is a usable regression oracle. New OSM-only columns come later,
   behind flags.
3. **OSM default:** *on.* The native table calls `analyze()` (OSM on, graceful
   geometry-only fallback on sparse/Overpass-failure — exactly like `generate`/
   `analyze`). A `--no-osm` opt-out (and `GPXSHEET_DISABLE_OSM`) keeps a fast
   offline path; **offline output is what we diff against gpxtable**.
4. **Multi-day (1 track = 1 day):** *deferred.* Single unified route first.
   gpxsheet already concatenates tracks into one `Route`; `day_breaks` on the
   model + `load_route` changes are a later phase.

### Reconciling (2) + (3)
The **column layout** matches gpxtable. With OSM on (default), the same columns
are populated with better data (real fuel rows, snapped distance, road names in
Notes), so byte-for-byte equality with gpxtable only holds in `--no-osm` mode on
the same geometry — that offline case is the regression oracle.

## Where the table data comes from (analysis graph → rows)

After `analyze()`:
- `route.pois` — every named GPX waypoint, projected to a mile, with `symbol`
  (`analysis.detect_pois`). These are the row backbone (gpxtable is waypoint-based).
- `route.fuel_stops` — rider fuel waypoints **plus OSM-discovered fuel** when OSM
  ran (`enrich._add_fuel`), already deduped and with rider waypoints winning.
- `route.segments` — OSM road names per leg (for a later Notes/Road enhancement).

Rows = `pois` ∪ (`fuel_stops` not coincident with a POI), sorted by mile. Each
row is classified (marker/delay/fuel-reset) and timed.

## Build sequence (one commit each)

### Commit 1 — `src/gpxsheet/waypoints.py`: the classifier
Port `GPXTABLE_DEFAULT_WAYPOINT_CLASSIFIER` + `_classify` semantics into a
standalone, typed module. **Fix the `\D` regex bug** (`\bDinner\b`). API:
`classify(name, symbol) -> Classification(symbol, delay, marker, fuel_reset)`,
first-match-wins, name-regex sets the symbol. Unit tests cover each default rule
+ the Dinner/"winner" regression. Standalone — no rewiring of `analysis.py` yet.

### Commit 2 — `src/gpxsheet/timing.py`: ETA engine + sun
Pure functions over ordered stops: `travel_time(meters, speed_kph)`, cumulative
arrival with layover accumulation, `since_gas`/`total` distance pairing, and
`sun_times(start, end)` via `astral`. Mirrors gpxtable's math (flat speed for
now; per-segment OSM speed is a later enhancement). Unit tests with fixed
departure/speed assert exact HH:MM and since/total values.

### Commit 3 — `src/gpxsheet/routetable.py`: native renderer
Assemble rows from an analyzed `Route` (Commit 1 + 2), render markdown in
gpxtable's exact column format (`OUT_HDR`/`OUT_SEP`/`OUT_FMT` equivalents), and
reuse `markdown2` for HTML (same `gpxtable` table class). Header block (creator,
departure, total distance, default speed) + trailing sun line. Tests run on the
analyzed synthetic `table_route.gpx` (sparse → offline geometry-only) and assert
structure + a column-format parity check against gpxtable on the same file.

### Commit 4 — wire CLI + service to the native renderer
`cli table` and `service/render._table_result` call the native path. Add
`--osm/--no-osm` (default on). Keep `src/gpxsheet/table.py` (the gpxtable shim)
importable as the parity oracle. Update `test_table.py` / `test_service.py`.

### Commit 5 — docs
Note the native table in `CLAUDE.md` (the `table` command no longer bypasses the
pipeline) and `docs/product.md`. List follow-ups: per-segment OSM speed, Road
column, turn-by-turn cue-sheet mode, multi-day `day_breaks`.

## Explicitly deferred (follow-up work, not this branch)
- Per-segment speed from OSM `maxspeed`/`highway` → variable ETA.
- A real Road/Notes column from `route.segments` road names.
- Turn-by-turn rows from `decision_points` (cue-sheet mode).
- Multi-day `day_breaks` on `Route` + `load_route`.
- Dropping the `gpxtable` runtime dependency.

## Verification
- `ruff check .`, `mypy src tests docs`, `pytest -q` green after every commit.
- Parity: native `--no-osm` table vs. `gpxtable` on `table_route.gpx` /
  `basecamp-route.gpx` — same columns, markers, ETAs, sun line.
- OSM-on deltas (fuel rows, distance) verified against the committed OSM cache.
