# Garmin BaseCamp routes: findings & implementation notes

Status: **implemented** (see [`gpx.py`](../src/gpxsheet/gpx.py),
[`tests/test_gpx.py`](../tests/test_gpx.py)). Sample fixture:
[`gpxsamples/basecamp-route.gpx`](../gpxsamples/basecamp-route.gpx) — "Fort Ross Run",
a real Bay Area moto route exported from BaseCamp (`creator="Garmin Desktop App"`).

## Why this matters

A BaseCamp **Trip Planner** route stores its real, road-snapped geometry *inside
Garmin extension elements*, not in the standard `<rtept>` list. gpxsheet's loader
([`gpx.py`](../src/gpxsheet/gpx.py)) only reads `route.points` (the `<rtept>`), so for
this file it sees **23 sparse points instead of the 5197 that describe the actual
roads**. With only 23 points the route is `looks_sparse` → it skips real OSM
enrichment and draws near-straight lines between widely spaced stops — a badly wrong
sheet. The correct geometry is already in the file; we just don't harvest it.

## Findings: the structure of a BaseCamp route

The file is GPX 1.1 with ~15 declared Garmin namespaces. Only two carry content here:

- `gpxx` — **GpxExtensionsv3** (`.../GpxExtensions/v3`)
- `trp` — **TripExtensions v1** (`.../TripExtensions/v1`)

### Route level (`<rte>/<extensions>`)

| Element | Meaning |
|---|---|
| `gpxx:RouteExtension > IsAutoNamed` | whether the route name was auto-generated |
| `gpxx:RouteExtension > DisplayColor` | one of 17 enum colors (here `Magenta`) |
| `trp:Trip > TransportationMode` | `Motorcycling` / `Automotive` / … (routing profile) |

### Route point hierarchy — three kinds of point

Each `<rtept>` is a **user point** (a stop the rider placed). Two flavours, told
apart by the extension it carries:

- **Via point** — `trp:ViaPoint` present → an *announced stop* (Garmin's term).
  May carry `DepartureTime`, `ArrivalTime`, `StopDuration`, `CalculationMode`
  (`FasterTime`/`ShorterDistance`/`Direct`/`LessFuel`/`ScenicRoads`), `ElevationMode`.
- **Shaping point** — `trp:ShapingPoint` (or no `trp:` element) → bends the
  calculated path but is *not* announced. Its `<name>` is usually a reverse-geocoded
  street address (e.g. `"1716 Las Gallinas Ave"`), not a meaningful rider label.

Beneath each `<rtept>` sits the **calculated geometry**:

- `gpxx:RoutePointExtension > gpxx:rpt` — a list of road-snapped lat/lon points.
  **Each rtept's `rpt` list is the path leading from that rtept toward the *next*
  one** (the final rtept has zero). Concatenated in document order, the rtepts +
  their `rpt` children reconstruct the full driven track.
- `gpxx:Subclass` — an 18-byte hex blob from Garmin's proprietary GDB router.
  **Undocumented; ignore it.**

### What the sample actually contains

```
23  <rtept>      → 8 via (announced stops) + 15 shaping points
5197 <gpxx:rpt>  → the real road-snapped geometry, distributed under the rtepts
```

Verified per-point (rpt count = path from this rtept to the next):

```
 0 VIA     rpt= 58  "Peet's Coffee Northgate Mall"   dep=…  arr=…
 1 shaping rpt=258  "1716 Las Gallinas Ave"
 3 VIA     rpt=288  "Nicasio Square"
 …
22 VIA     rpt=  0  "Starbucks Strawberry Village"   (destination)
```

**Times are sparse and unreliable.** Only the first via carried `Departure/ArrivalTime`
in the sample, and per the Garmin schema the **first via's `ArrivalTime` and the last
via's `DepartureTime` are semantically invalid** (BaseCamp writes placeholders there
regardless). So treat arrival/departure as **optional, best-effort metadata** — never
a required field, and never an input to distance/ETA math.

## How gpxpy exposes this (confirmed)

gpxpy parses the `<rtept>` into `route.points` and leaves every extension as a raw
`lxml`/ElementTree node on `point.extensions` (and `route.extensions`). So harvesting
needs no new XML parser — walk the existing nodes by namespaced tag:

```python
GPXX = "{http://www.garmin.com/xmlschemas/GpxExtensions/v3}"
TRP  = "{http://www.garmin.com/xmlschemas/TripExtensions/v1}"
for ext in point.extensions:
    if ext.tag == GPXX + "RoutePointExtension":
        rpts = [c for c in ext if c.tag == GPXX + "rpt"]   # → GeoPoints
    if ext.tag == TRP + "ViaPoint":
        ...  # DepartureTime / ArrivalTime / CalculationMode
```

## What was implemented

When a `<rte>` carries Garmin `RoutePointExtension` geometry, [`load_route`](../src/gpxsheet/gpx.py)
loads it as a **dense track** (like trackpoints) and promotes its **via points** to
waypoints — reusing the existing geometry/enrichment/POI pipeline unchanged.

### 1. `gpx.py` — reconstruct the dense track from a Garmin route

In [`load_route`](../src/gpxsheet/gpx.py), after the track loop finds no `<trk>`
points, the route fallback now first calls `_garmin_route_dense_points(route)`: if any
rtept carries a `RoutePointExtension`, it builds the point list as, **in document
order, for each rtept**, the rtept's own `(lat, lon, ele)` followed by each `rpt`
child's `(lat, lon)` (malformed `rpt` children are skipped defensively). For the
sample this yields **5220** ordered `GeoPoint`s — geometrically equivalent to a
recorded track, so everything downstream (`cumulative_distances`, decision detection,
OSM enrichment) works as-is and `looks_sparse`
([`analysis.py:78`](../src/gpxsheet/analysis.py#L78)) returns False. The helper returns
`None` for a plain route, falling through to the unchanged sparse `<rtept>` path.

### 2. Promote via points to waypoints (not shaping points)

`_garmin_route_via_waypoints(route)` collects each `<rtept>` whose extensions contain
`trp:ViaPoint` as a `Waypoint(lat, lon, name, symbol, …)`, appended to the file's
`<wpt>` waypoints. These flow through the existing
[`detect_pois`](../src/gpxsheet/analysis.py#L352) / fuel / food path — the `<sym>`
values (`Restaurant`, `Gas Station`, …) already drive food/fuel detection, and "rider
waypoints win over OSM" already applies. **Shaping points are excluded**: their
address-string names are noise (the sample has 15 of them).

### 3. Optional arrival/departure times

`Waypoint` ([`models.py`](../src/gpxsheet/models.py)) gained
`arrival_time: datetime | None = None` and `departure_time: datetime | None = None`
(frozen dataclass; new defaulted fields are backward-compatible). Times are parsed
with `_parse_garmin_time` (tolerates a trailing `Z`) and cleaned with two rules:
the **first via's arrival** and the **last via's departure** are dropped (schema-invalid
placeholders), and any **departure-before-arrival** pair is dropped entirely. They are
**display-only metadata** and feed no distance/ETA math. (The `table` command's ETA
logic stays independent; it reads GPX directly.)

> Deliberately deferred: these times are retained on the model but not yet surfaced on
> the strip/POI rendering — add that when there's a concrete rendering need.

### 4. Edge cases

- **Plain `<rte>` with no `rpt`** → existing fallback, unchanged.
- **Mixed `<trk>` + `<rte>`** → tracks still win (current precedence); a file with
  real trackpoints doesn't need the route reconstruction.
- **Malformed/missing coords on an `rpt`** → skip that child defensively (best-effort,
  matching the "topology error degrades, never aborts" house style).
- **Security** — no new XML surface: still goes through `_reject_unsafe_xml` and
  gpxpy's already-parsed tree.

## Verification

- **New unit tests** (offline; the fixture is committed) in `tests/`:
  - dense-track count: `load_route("gpxsamples/basecamp-route.gpx")` yields
    `len(points) == 23 + 5197 == 5220` and is monotonic in cumulative distance.
  - `looks_sparse(route)` is `False` for the harvested route.
  - exactly the 8 via points become waypoints; no shaping points do.
  - the first via's `arrival_time` is dropped (schema-invalid) while its
    `departure_time` parses; a synthetic departure-before-arrival pair drops both.
- **End-to-end**: `.venv/bin/gpxsheet generate gpxsamples/basecamp-route.gpx -o
  /tmp/fortross.pdf` should now follow Hwy 1 / Fort Ross Rd road geometry rather than
  straight chords between stops. (Live OSM; or `GPXSHEET_DISABLE_OSM=1` for geometry-only.)
- **Gates**: `.venv/bin/ruff check .`, `.venv/bin/mypy src tests docs`,
  `.venv/bin/pytest -q` all clean.

## Files touched

- [`src/gpxsheet/gpx.py`](../src/gpxsheet/gpx.py) — Garmin route detection + dense-track
  reconstruction (`_garmin_route_dense_points`) + via-waypoint harvesting
  (`_garmin_route_via_waypoints`) + time parsing (`_parse_garmin_time`).
- [`src/gpxsheet/models.py`](../src/gpxsheet/models.py) — optional `arrival_time` /
  `departure_time` on `Waypoint`.
- [`tests/test_gpx.py`](../tests/test_gpx.py) — a deterministic synthetic Garmin route
  plus a `gpxsamples` sample test guarded by `skipif` when the submodule is absent.
