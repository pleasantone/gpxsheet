# GPXtable improvement suggestions

Review of `~/gpxtable` against GPXsheet's mature OSM pipeline (`enrich.py`/
`analysis.py`). GPXsheet already implements every OSM idea below, so it is a
proven reference. **Suggestions only.**

Guiding constraint (mirror GPXsheet's own design): GPXtable today is fully
offline, fast, deterministic. Any OSM use must stay strictly **opt-in behind a
flag with graceful fallback** — exactly how `analysis._osm_enrich_pass` degrades
on `looks_sparse`/Overpass failure.

## A. Plain code/correctness bugs (no OSM needed)

1. **Regex bug — `\D` in the Restaurant classifier** (`gpxtable.py:52`):
   `\b\Dinner\b`. `\D` is "any non-digit", so it matches `winner`/`sinner` as
   lunch stops. Should be `\bDinner\b`. *(Already fixed in GPXsheet's ported
   classifier, `waypoints.py`.)*

2. **Route distance lags by one point** (`print_routes`, `gpxtable.py:614-655`):
   `dist` is updated *after* the row is printed, so each route point shows the
   distance to the **previous** point and the final leg is dropped entirely
   (e.g. a 45.5 mi route's last row reads 32). Move the `dist +=` so the printed
   distance is cumulative-through-this-point. High-impact: it skews every route
   ETA and the fuel since/total column. *(Found while building GPXsheet's native
   table; GPXsheet computes correct cumulative distance.)*

3. **`get_points_data()` recomputed per waypoint — O(W·N)** (`print_waypoints`,
   `gpxtable.py:488-500`): each waypoint rebuilds the full cumulative-distance
   pass over all N track points. Compute once per track and reuse.

4. **Waypoint ordering uses `point_no`, ignoring `segment_no`**
   (`gpxtable.py:501-504`): on a multi-segment track, `point_no` restarts per
   segment so cross-segment order can scramble. Sort by `distance_from_start`
   (already carried in `NearestLocationDataExt`).

5. **first/last waypoint detected with `==` value-equality**
   (`gpxtable.py:514-515`): two value-identical waypoints misclassify first/last
   (affecting marker suppression + layover). Use index or `is`.

6. **Dead `track_no` field** (`gpxtable.py:128`): hardcoded `-1`, carried but
   never set. Populate or drop.

7. **`_populate_times` mutates the caller's GPX in place**
   (`gpxtable.py:420-439`): `remove_time()/adjust_time()` rewrite the passed-in
   object. Document loudly or operate on a copy.

8. **`(G)`/`(L)`/`(R)`/`(P)` shorthands are effectively dead**: `\b\(G\)\b` only
   matches when the token is glued to word chars (`(` is not a word char, so the
   leading `\b` rarely fires). Drop the surrounding `\b` to make the shorthand
   actually work. *(GPXsheet preserved the quirk verbatim to keep GPXtable an
   exact oracle; worth fixing in GPXtable proper.)*

## B. OSM augmentation opportunities (GPXsheet implements each)

Ranked by payoff vs. GPXtable's mission ("When is lunch? Do I have enough gas?").

- **B1. Auto-discover fuel (`amenity=fuel`) — highest value.** GPXtable only
  knows gas the rider pre-marked. `enrich._add_fuel` queries along a buffer,
  names by `name`/`brand`, dedups, and suppresses a station near a rider
  waypoint (rider wins). Gives fuel-gap math even with no gas pins.
- **B2. Per-segment speed from `maxspeed`/`highway` class — biggest ETA win.**
  GPXtable uses one flat speed; interstate + backroad ETAs are systematically
  off. GPXsheet already samples per-edge tags; map class → cruising speed for a
  variable travel-time model.
- **B3. True road distance vs. straight-line** (`_calculate_distance`): snap to
  the OSM drive graph (`enrich._chunk_graph` + nearest-edge) instead of
  great-circle between sparse points.
- **B4. OSM-assisted classification fallback:** when a waypoint coincides with an
  OSM `amenity=fuel`/`restaurant`/`fast_food`/`cafe` or `tourism=viewpoint`,
  supply the G/L marker even if the name doesn't match a regex (regex still wins).
- **B5. Hazard/surface annotations:** GPXsheet computes unpaved spans (free) and
  ferry crossings (`enrich._detect_ferries`). Add a Notes flag ("3.2 mi unpaved")
  or a ferry row with crossing time.
- **B6. Fuel-range warning:** GPXtable shows since/total but never warns;
  `analyze_fuel` yields `longest_gap_miles` + `exceeds_range`.
- **B7. Locality/road-name context in Notes:** reverse-geocode the town or the
  road name a point sits on (GPXsheet's durable road-name runs).

## C. Architecture recommendation

- Do **not** reimplement OSM inside GPXtable — GPXsheet owns a battle-tested
  layer (chunking, `drive`→`drive_service` fallback, cache wiring, dedup,
  sparse/failure fallback, offline test replay).
- Cleanest seam: factor GPXsheet's enrichment primitives into a small optional
  helper GPXtable consumes behind a `gpxtable[osm]` extra, or have GPXtable
  expose a pluggable "enricher" hook GPXsheet implements — keeping a hard
  osmnx/shapely/geopandas dep out of GPXtable's offline core.
- Preserve the contract: OSM strictly opt-in (`--osm`), identical output when
  off, graceful degrade with a warning. Carry over two hard-won rules: rider
  waypoints win over OSM; skip sparse waypoint-only routes (`looks_sparse`).

> Note: the reverse direction — pulling GPXtable's temporal/classifier logic
> *into* GPXsheet and rendering the table natively on the analysis graph — has
> been implemented; see `NEW_TABLE_PLAN.md`.
