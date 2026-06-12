# Native Route Table — implementation plan

> **Status (branch `feat/native-route-table`): COMPLETE — 11 commits, not pushed.**
> All of Commits 1–5 done plus two follow-ups Paul approved mid-stream:
> - **Done:** classifier (`waypoints.py`), timing engine (`timing.py`), renderer
>   (`routetable.py`), named-rtept lift (`gpx.py`), CLI + `/v1/table` wired
>   (OSM default-on, `--no-osm` offline), docs.
> - **Done (decisions):** keep corrected distance (not gpxtable's lag bug); drop
>   gpxtable-style `--format` (infer from `-o` ext, like `generate`); remove the
>   `ignore_times` no-op end-to-end (web model + SPA + openapi); **gpxtable
>   runtime dependency fully removed** — `astral`/`markdown2`/`python-dateutil`
>   are now direct deps; `table.py` + `test_table.py` deleted.
> - **Deferred (follow-up branches):** per-segment OSM speed for variable ETA;
>   Road column from `route.segments`; turn-by-turn cue-sheet mode; multi-day
>   `day_breaks`; an OSM toggle in the SPA Table tab.
>
> Gate green every commit: `ruff` clean, `mypy` clean, `pytest` 251 passed / 2
> skipped. **Not pushed / no PR** pending Paul's go-ahead.
>
> **Key finding (now also in `GPXtable-improvements.md`):** GPXtable's route path
> lags distance by one point (each row shows the distance to the *previous* point
> and the final leg vanishes — total 32 vs the correct 45.5 mi on the test
> route). So gpxtable was only ever a *format* oracle; we keep true cumulative
> distance.

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

## Build sequence (one commit each) — ✅ all done

### Commit 1 ✅ — `src/gpxsheet/waypoints.py`: the classifier
Port `GPXTABLE_DEFAULT_WAYPOINT_CLASSIFIER` + `_classify` semantics into a
standalone, typed module. **Fix the `\D` regex bug** (`\bDinner\b`). API:
`classify(name, symbol) -> Classification(symbol, delay, marker, fuel_reset)`,
first-match-wins, name-regex sets the symbol. Unit tests cover each default rule
+ the Dinner/"winner" regression. Standalone — no rewiring of `analysis.py` yet.

### Commit 2 ✅ — `src/gpxsheet/timing.py`: ETA engine + sun
Pure functions over ordered stops: `travel_time(meters, speed_kph)`, cumulative
arrival with layover accumulation, `since_gas`/`total` distance pairing, and
`sun_times(start, end)` via `astral`. Mirrors gpxtable's math (flat speed for
now; per-segment OSM speed is a later enhancement). Unit tests with fixed
departure/speed assert exact HH:MM and since/total values.

### Commit 3 ✅ — `src/gpxsheet/routetable.py`: native renderer
(plus a `feat(gpx)` commit lifting named plain `<rtept>`s to waypoints.)
Assemble rows from an analyzed `Route` (Commit 1 + 2), render markdown in
gpxtable's exact column format (`OUT_HDR`/`OUT_SEP`/`OUT_FMT` equivalents), and
reuse `markdown2` for HTML (same `gpxtable` table class). Header block (creator,
departure, total distance, default speed) + trailing sun line. Tests run on the
analyzed synthetic `table_route.gpx` (sparse → offline geometry-only) and assert
structure + a column-format parity check against gpxtable on the same file.

### Commit 4 ✅ — wire CLI + service to the native renderer
`cli table` and `service/render._table_result` call the native path; `osm` flag
threaded through `analyze`/`analyze_route`/`_osm_enrich_pass`. (gpxtable shim was
kept initially, then removed — see below.)

### Commit 5 ✅ — docs + OSM-on tests
`CLAUDE.md` / `docs/product.md` updated; deterministic OSM-discovered-fuel and
`--no-osm` tests added against the committed cache.

### Follow-ups completed on this branch (Paul-approved mid-stream)
- ✅ `refactor(table)`: dropped `--format`, removed `ignore_times` no-op (web
  model + SPA + openapi), renamed `depart_at`→`departure`.
- ✅ `refactor(table)`: **removed the gpxtable runtime dependency** entirely —
  relocated `parse_departure`/`markdown_to_html` into `routetable.py`, deleted
  `table.py` + `test_table.py`, made `astral`/`markdown2`/`python-dateutil`
  direct deps.

## Explicitly deferred (follow-up work, NOT on this branch)
- Per-segment speed from OSM `maxspeed`/`highway` → variable ETA.
- A real Road/Notes column from `route.segments` road names.
- Turn-by-turn rows from `decision_points` (cue-sheet mode).
- Multi-day `day_breaks` on `Route` + `load_route`.
- An OSM on/off toggle in the SPA Table tab (API already supports `osm`).
- ✅ ~~Dropping the `gpxtable` runtime dependency~~ — done on this branch.
- Dropping the `gpxtable` runtime dependency.

## Verification
- `ruff check .`, `mypy src tests docs`, `pytest -q` green after every commit.
- Parity: native `--no-osm` table vs. `gpxtable` on `table_route.gpx` /
  `basecamp-route.gpx` — same columns, markers, ETAs, sun line.
- OSM-on deltas (fuel rows, distance) verified against the committed OSM cache.
