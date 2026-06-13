# 01 — Analysis Engine (rewritten from scratch)

Turns an uploaded GPX into the analyzed **Route** (geometry + decisions +
segments + fuel + timing). Pure Python, in-process, **no dependency on the old
`gpxsheet` package** — but it must reproduce its behavior on real tracks. Parent:
[`../SPEC.md`](../SPEC.md). Read §6 (lessons) first.

## Inputs / outputs

- **In:** GPX bytes; options `{ profile, fuel_range_mi?, osm: bool, speed_mph? }`.
- **Out:** a `Route` dataclass → serialized to the DB/API:
  ```python
  Route(
    name, length_mi, points: list[RoutePoint],   # matched dense polyline
    decision_points: list[DecisionPoint],
    segments: list[Segment],                      # named road stretches
    waypoints: list[Waypoint],                    # named GPX points (POIs)
    fuel_stops: list[FuelStop],                   # OSM + GPX, deduped
    day_breaks: list[int], day_names: list[str],
    speed_samples_mph: list[tuple[float,float]],  # (mile, mph) from OSM maxspeed
    spans: list[RouteSpan],                       # unpaved/ferry stretches
    findings: list[Finding],
  )
  DecisionPoint(mile, instruction, significance:int, lat, lon,
                branches: list[Branch])           # roads-not-taken (name, angle)
  ```

## Pipeline (the cacheable `analyze_core`)

```
GPX bytes
 → parse (track / route / waypoints; Garmin BaseCamp + plain <rte>)
 → map-match to road geometry (Valhalla /trace_attributes)   [geo-infra]
 → RDP cleanup (tolerance ~ a few meters)
 → geometry baseline pass (heading-change turns)              [fallback signal]
 → OSM enrich pass (Overpass): road names, classes, junctions, fuel, surface
 → decision detection (two-tier, see below)
 → segmentation (named stretches between decisions)
 → fuel analysis (OSM amenity=fuel + GPX fuel waypoints, deduped)
 → timing prep (speed_samples from maxspeed/road-class)
 → day splitting (multi-<trk>)
 → Route
```

Group-dependent products (profile gating, fuel report vs a *specific* range,
POI selection) are **not** here — they live in Group Math (§10) and run per-Plan,
cheap. Keep this `analyze_core` cacheable by `(gpx_hash, ENGINE_VERSION, osm)`.

## Decision detection — the heart (carry forward, do not regress)

Two-tier, because **pure geometry floods twisty roads** (Mt-Hamilton → 100+
false turns). See `docs/product.md` "Decision Point Engine — as built" + the
"Significance Scoring" / "Rule Set 1/2/3" sections for the full design.

- **Geometry baseline (no OSM):** group same-direction heading deltas confined to
  a short arc into one turn (`TURN_ANGLE_THRESHOLD_DEG=35`, `MAX_TURN_ARC_M=90`).
  Honest but over-detects; used as **fallback** (sparse routes / Overpass down)
  and to supply turn **direction**.
- **OSM mode (primary):** a decision is a **durable road-name change**, a
  **major-road crossing** (state/county highway, arterial), or a **junction
  ambiguity** (Y / T / fork / roundabout) where a rider could go wrong. Suppress
  curves-within-the-same-road. Constants: `MIN_ROAD_RUN_MILES=0.3`,
  `MERGE_MIN_SEPARATION_MILES=0.2`, `CONTINUE_MAX_ANGLE_DEG=25`.
- **Significance** scores the decision (drives profile gating + map prominence).
  Reintroduce the `SCORE_*` table from product.md (county-road / Y / T /
  town-center) — note the old code had only road-name/highway/sharp-turn wired;
  Y/T junction-geometry scoring is a **TODO carried over** (`product.md` scoring
  table). Implement it here if feasible.
- **`branches`**: the named roads *not* taken at a junction (for the cue/briefing
  "continue on X, skip Y").
- **Fallback:** if the route `looks_sparse` (waypoint-only `<rte>`) or Overpass
  fails → geometry-only with a `Finding(info, "geometry_only", …)`.

## Other passes

- **Segments:** contiguous stretches under one OSM road name between decisions;
  geometry-only segments named `Leg N` (not real names — exclude from "Road"
  displays).
- **Fuel:** OSM `amenity=fuel` discovered along a corridor buffer + GPX fuel
  waypoints; **dedupe** an OSM station within `FUEL_BUFFER_M` of a named
  waypoint (rider waypoints win). Produces `fuel_stops` (mile, name, lat/lon).
- **Surface spans:** `surface=unpaved|gravel|…` and ferry stretches → `RouteSpan`
  (unpaved/ferry) with labeled ends (for map styling + cautions).
- **Timing prep:** `speed_samples_mph = [(mile, mph)]` from OSM `maxspeed`
  (fallback to highway-class default). A flat user `speed_mph` overrides.
- **Days:** each `<trk>` is a day; `day_breaks` are point indices; per-day miles
  rebase to 0; +24h/day for schedule.

## Map-matching (replaces osmnx snapping)

Use Valhalla `trace_attributes` to snap the GPX to road geometry and fetch
per-edge `road name`, `road class`, `surface`, `speed`/`maxspeed`. This gives
clean geometry **and** much of the enrichment in one call, reducing Overpass
load to corridor POI queries (fuel, viewpoints later). See
[`02-geo-infra.md`](02-geo-infra.md) for the Valhalla call shapes. If
map-matching fails, fall back to the raw GPX polyline + Overpass-only enrichment.

## Acceptance criteria

- On `gpxsamples/` real tracks (copy fixtures into `app/backend/tests/data/`),
  Mt-Hamilton-style twisty tracks produce **no curve-as-turn floods**
  (sanity: decisions ≪ geometry-only count).
- Plain `<rte>`, Garmin BaseCamp, and multi-`<trk>` inputs all analyze; via
  points lift to waypoints, shaping points excluded.
- OSM-discovered fuel appears; a GPX fuel waypoint near an OSM station dedupes.
- Overpass/Valhalla unavailable ⇒ geometry-only output + a `Finding`, no crash.
- Deterministic offline test run via committed Overpass/Valhalla fixtures.
- `ENGINE_VERSION` bumped whenever detection output changes (cache key).
