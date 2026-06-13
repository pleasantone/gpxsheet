# Library API

The public Python API mirrors the [web API](web-api.md): the entry points —
`render`, `analyze`, `validate` — take the same names and arguments (but run
synchronously, returning values directly instead of a job). Import them from the
top-level `gpxsheet` package. The route **table** lives in `gpxsheet.routetable`
(see [Route table](#route-table) below).

```python
import gpxsheet

# render a map (portrait PDF is the default; layouts and formats below)
gpxsheet.render("route.gpx", "route.pdf")
gpxsheet.render("route.gpx", "overview.png", layout="preview", format="png")

# structured analysis
route = gpxsheet.analyze("route.gpx", fuel_range=180)

# validation report (route + findings)
report = gpxsheet.validate("route.gpx", fuel_range=180)
for f in report.findings:
    print(f.level, f.code, f.message)
```

OSM enrichment runs as part of analysis, falling back to the geometry baseline
when a route is too sparse to sample or the Overpass query fails.

## What each entry point returns

| function | returns | notes |
|----------|---------|-------|
| `render(gpx, out, …)` | `str` | path to the written file (the `out` you gave, or `route.<format>`); the artifact itself is a PDF/PNG on disk |
| `analyze(gpx, …)` | [`Route`](#route) | the fully analyzed route graph — decisions, segments, fuel, hazards |
| `validate(gpx, …)` | [`ValidationReport`](#validate) | the analyzed `Route` plus a list of [`Finding`](#validate)s |
| `load_route(gpx)` | [`Route`](#route) | geometry only — `points`/`distances_m`/`waypoints` populated, all analysis lists empty |
| `analyze_route(route, …)` | [`Route`](#route) | analyzes an already-loaded `Route` in place of `analyze`'s load step |
| `routetable.render_table(gpx, out, …)` | `pathlib.Path` | path to the written `.html`/`.md`/`.json` table |
| `routetable.build_table_markdown(route, …)` | `str` | the table markdown for an already-analyzed `Route` |
| `routetable.build_table_json(route, …)` | `str` | the structured table as a JSON string |
| `routetable.build_table_data(route, …)` | [`TableDocument`](#tabledocument) | the structured table as typed dataclasses |

Everything analytical hangs off the [`Route`](#route) object, so that section is
the bulk of this reference.

## Render

`layout` (`portrait` · `landscape` · `preview` · `strip`) and `format` (`pdf` ·
`png`) are independent; portrait PDF is the default. `format=None` (the default)
infers the format from the output filename extension (`.png` → `"png"`, anything
else → `"pdf"`). **Returns** the path to the written file (a `str`); the map is
written to disk as a side effect.

::: gpxsheet.render

## Analyze

**Returns** a populated [`Route`](#route) (see the full structure below). With
`osm=True` (the default) the decisions, road segments and fuel come from
OpenStreetMap; `osm=False` forces a fast, fully offline geometry-only analysis
(coarser, no auto-fuel). `include_hazards=True` additionally populates the
hazard fields (`unpaved_miles`, `ferry_crossings`, `spans`) — `validate` sets
this for you. `profile` and `fuel_range` gate the per-profile products
(decision threshold, fuel report) but do not change the OSM core.

::: gpxsheet.analyze

## Validate

**Returns** a [`ValidationReport`](#validationreport-and-finding): the analyzed
`Route` plus a `list[Finding]`. A `Finding` has `level` (`"warning"` | `"info"`),
`code` (`"fuel"` | `"unpaved"` | `"ferry"` | `"seasonal"`) and a human-readable
`message`. Warnings never raise — a route with warnings is still a valid result;
read the findings. See [`ValidationReport` and `Finding`](#validationreport-and-finding).

::: gpxsheet.validate

::: gpxsheet.ValidationReport

::: gpxsheet.Finding

## Route table

A markdown/HTML/JSON route table (waypoints, distances, fuel/lunch markers, ETAs,
sunrise/sunset) rendered from the same analysis graph, so it inherits OSM
enrichment (auto-discovered fuel, road names, road-snapped distance) and adds a
timing layer. It lives in `gpxsheet.routetable` (not the top-level namespace):

```python
from gpxsheet.routetable import render_table, parse_departure

depart, tz = parse_departure("9:00 AM", "US/Pacific")  # natural-language or ISO
render_table("route.gpx", "route.md", fmt="markdown", departure=depart, tz=tz)
# OSM is on by default; pass osm=False for a fast, fully offline table.
# ETAs need a departure; show_cue=True appends a turn-by-turn cue sheet.

# Structured data (always imperial; lat/lon + cue always present):
from gpxsheet.routetable import build_table_data, build_table_json
from gpxsheet import analyze

route = analyze("route.gpx")
doc = build_table_data(route, departure=depart, tz=tz)   # typed TableDocument
print(doc.sections[0].rows[0].mile, doc.sections[0].rows[0].eta)
json_str = build_table_json(route, departure=depart, tz=tz)  # JSON string
```

Return values:

- `render_table(gpx_source, output_path, …)` → `pathlib.Path` — analyzes
  `gpx_source` and writes an `html`, `markdown` or `json` file, returning its path.
- `build_table_markdown(route, …)` → `str` — renders an already-analyzed
  [`Route`](#route) to the table markdown (multi-track routes get one section per
  day). This is the string `render_table` writes (and wraps for HTML).
- `build_table_data(route, …)` → [`TableDocument`](#tabledocument) — the structured
  table for an already-analyzed `Route`: route `name`/`units` plus a `sections`
  list (one per day), each with `rows`, `cue`, `speed` and `sun`. **Always
  imperial** (miles/mph, 1-decimal); `lat`/`lon` and the cue are always included.
- `build_table_json(route, …)` → `str` — `build_table_data` serialized to a JSON
  string (datetimes as ISO 8601 with offset; `null` for absent optionals).
- `markdown_to_html(md)` → `str` — wraps table markdown in the `gpxtable` CSS
  class for styling.
- `parse_departure(departure, timezone)` → `tuple[datetime | None, tzinfo | None]`
  — parses a natural-language/ISO time string and an IANA zone for the ETA
  column; raises `ValueError` on unparseable input. Both elements are `None` when
  `departure` is `None` (no ETA column).

::: gpxsheet.routetable.render_table

### `TableDocument`

The structured route table returned by `build_table_data`. All numbers are
imperial (miles / mph), rounded to one decimal; datetimes are `datetime` objects
in the display timezone (serialized to ISO 8601 with offset by `to_dict()` /
`build_table_json`).

- **`TableDocument`** — `name: str`, `units: str` (always `"imperial"`),
  `sections: list[TableSection]`. `to_dict()` returns the JSON-ready mapping.
- **`TableSection`** — one day (or the whole route): `day: int` (1-based),
  `title: str`, `departure: datetime | None`, `distance_mi: float`,
  `speed: TableSpeed`, `sun: TableSun | None`, `rows: list[TableRow]`,
  `cue: list[CueEntry]`.
- **`TableRow`** — `name`, `mile` (section-local), `since_gas_mi`, `marker`
  (`""`/`"G"`/`"L"`/`"GL"`), `gas`/`lunch`/`fuel_reset` (bool), `layover_min`,
  `eta: datetime | None`, `road: str | None`, `symbol: str | None`, `lat`, `lon`.
- **`CueEntry`** — `mile`, `eta: datetime | None`, `instruction`, `skip: list[str]`
  (named roads not taken).
- **`TableSpeed`** — `mode: str` (`"osm"` variable limits / `"flat"`), `avg_mph`.
- **`TableSun`** — `sunrise: datetime | None`, `sunset: datetime | None`.

::: gpxsheet.routetable.build_table_data

## Day cards

A per-day, read-ahead briefing (distance, climb, sunset / riding-after-dark,
passes, scenic stops, and cautions) — distinct from the tank-bag table/sheet. Lives
in `gpxsheet.daycard` (not the top-level namespace):

```python
from gpxsheet.daycard import render_day_cards, build_day_cards
from gpxsheet.routetable import parse_departure

depart, tz = parse_departure("Sat 8am", "US/Pacific")
render_day_cards("route.gpx", "cards.md", fmt="markdown", departure=depart, tz=tz)
# fmt is "markdown" | "html" | "json"; the sun/after-dark and weather/air sections
# need a departure. Pass live=False (or set GPXSHEET_DISABLE_LIVE=1, or the umbrella
# GPXSHEET_OFFLINE=1) for a fully offline card with no network lookups.
```

Return values:

- `render_day_cards(gpx_source, output_path, …)` → `pathlib.Path` — analyzes and
  writes md/HTML/JSON cards.
- `build_day_cards(route, …)` → `list[DayCard]` — builds the cards from an already
  analyzed [`Route`](#route). Each `DayCard` has `index`, `name`, `date`, `miles`,
  `moving_time`, `arrive`, `elevation_gain_ft`, `passes`, `scenic`, `gravel`,
  `no_services`, a `sun` summary, the live `weather` / `air` / `fire` /
  `elevation_profile` (when `live=True` and a source is reachable), and a
  `warnings` list of [`Finding`](#validationreport-and-finding) (`.to_dict()`
  gives the JSON view).

The live data comes from keyless, cached, **graceful** providers
(`gpxsheet.live`): Open-Meteo (`weather` with per-sample **crosswind**,
`air` quality / smoke, an `elevation_profile` DEM fallback when the GPX lacks
elevation) and NIFC (`fire` perimeters near the corridor). Any source that's
unavailable is omitted — the rest of the card still builds. Gate everything with
`live=` (and `GPXSHEET_DISABLE_LIVE=1`); weather/air also need a `departure` for
ETAs. The nested live types:

- **`WeatherInfo`** (`weather`) — `source`, `as_of`, `note` (e.g. beyond the
  ~16-day forecast horizon), and `samples: list[WeatherSample]`. Each
  **`WeatherSample`** is `mile`, `time`, `temp_f`, `feels_f`, `wind_mph`,
  `gust_mph`, `wind_dir_deg`, `crosswind_mph`, `precip_prob`, `precip_in`,
  `visibility_mi`, `code` (WMO). Values are imperial; metric is a render-time
  conversion.
- **`AirInfo`** (`air`) — `max_aqi`, `max_pm25`, `smoke` (bool), `source`, `as_of`.
- **`Fire`** (`fire: list[Fire]`) — `name`, `dist_mi`, `status`, `url`.
- **`ElevationProfile`** (`elevation_profile`) — `min_ft`, `max_ft`, `gain_ft`,
  `source` (`"gpx"` or the DEM fallback); only set when the DEM filled in for a
  GPX with no usable elevation.

New warning `code`s alongside the Phase-1 ones: `heat`, `cold`, `wind` (sustained,
gust, or crosswind), `precip`, `smoke`, and `fire`. See
[day-cards-design.md](day-cards-design.md) for the roadmap (key-gated AirNow/
OpenWeather and cell-coverage dead zones are Phase 3).

## Lower-level helpers

`load_route` returns an un-analyzed [`Route`](#route) (geometry + raw waypoints
only); `analyze_route` runs the analysis engine on a `Route` you already loaded
and returns the same object enriched. Use these to load once and analyze with
several profiles, or to inspect raw geometry.

::: gpxsheet.load_route

::: gpxsheet.analyze_route

## Route model

`analyze()` returns a `Route` — the analyzed route graph. It is a mutable
dataclass (`gpxsheet.models.Route`); the analysis lists default to empty and
fill in as the engine runs. Miles are statute miles; `mile`/`start_mile`/
`end_mile` are distances *along the route from its start*.

### `Route`

| field | type | meaning |
|-------|------|---------|
| `name` | `str` | route name (from the GPX `<trk>`/`<rte>`, else a fallback) |
| `points` | `list[GeoPoint]` | the route vertices, in order |
| `distances_m` | `list[float]` | cumulative meters at each point, parallel to `points` |
| `waypoints` | `list[Waypoint]` | named points from the GPX (`<wpt>`) or OSM |
| `decision_points` | `list[DecisionPoint]` | where the rider must act (turns, forks, roundabouts) |
| `reassurance_markers` | `list[ReassuranceMarker]` | "you're still on route" confidence markers between decisions |
| `fuel_stops` | `list[FuelStop]` | fuel opportunities on/near the route, in order |
| `pois` | `list[POI]` | named GPX waypoints projected onto the route for the strip |
| `segments` | `list[Segment]` | named road stretches, contiguous and in order |
| `spans` | `list[RouteSpan]` | unpaved/ferry stretches to draw as styled ribbon |
| `fuel_report` | `FuelReport \| None` | fuel-gap analysis; `None` when not computed for the profile |
| `unpaved_miles` | `float \| None` | total unpaved/track miles; **`None` = not assessed** (no OSM/hazard run) |
| `ferry_crossings` | `list[str] \| None` | ferry names crossed; **`None` = not assessed** |
| `seasonal_closures` | `list[str] \| None` | seasonal-closure risks (curated passes + OSM seasonal/conditional tags), each a label with its typical window; **`None` = not assessed** |
| `speed_samples_mph` | `list[tuple[float, float]] \| None` | OSM speed-limit profile as `(start_mile, mph)` breakpoints; drives variable ETAs; `None` = not assessed |
| `day_breaks` | `list[int]` | point indices where a new `<trk>` (≈ a new day) begins, excluding 0; empty for single-track / plain `<rte>` |
| `day_names` | `list[str]` | one name per day (`len(day_breaks) + 1` entries); an entry may be `""` if its track was unnamed; empty when there are no breaks |

Two computed properties: `route.length_m` (`float`, meters) and
`route.length_miles` (`float`). The `None`-vs-empty distinction on the hazard
fields matters: `None` means OSM/hazard data was never gathered (e.g.
`osm=False`, or `analyze` without `include_hazards`), whereas an empty list means
"assessed, none found."

### Nested types

**`GeoPoint`** — a single route vertex. `lat: float`, `lon: float`,
`ele: float | None` (elevation, often absent).

**`Waypoint`** — a named GPX `<wpt>` (or OSM-sourced point). `lat`, `lon`,
`name: str | None`, `symbol: str | None`, plus best-effort, display-only
`arrival_time` / `departure_time: datetime | None` (from Garmin BaseCamp via
points; never feed distance/ETA math).

**`DecisionPoint`** — a navigation decision.

| field | type | meaning |
|-------|------|---------|
| `mile` | `float` | position from route start |
| `instruction` | `str` | the cue, e.g. `"Continue onto …"`, `"Right onto …"`, `"Left at the fork"`, `"Take the 2nd exit onto …"` |
| `significance` | `int` | 0–80; profiles keep decisions at/above their threshold (minimalist 55, sport-touring 40, rally 30) |
| `lat`, `lon` | `float` | location |
| `kind` | `str` | `"critical_turn"` (default), `"fuel"`, or `"roundabout"` (see `DecisionKind`) |
| `turn_angle` | `float \| None` | signed degrees, `+right` / `-left` |
| `branches` | `tuple[Branch, …]` | roads *not* taken at the junction (for ghosted stubs); empty by default |
| `roundabout_exit` | `int \| None` | the Nth exit, when `kind == "roundabout"` |

**`Branch`** — a road at a junction the route does *not* take.
`direction: str` (`"left"`/`"right"`/`"straight"`/`"back"`, relative to the
rider), `relative_angle: float` (signed degrees off the route heading),
`name: str | None`.

**`ReassuranceMarker`** — a confidence marker between decisions. `mile`, `label:
str`, `lat`, `lon`, `reason: str` (`"interval"` default, or `"town"`/`"feature"`/
`"landmark"`).

**`FuelStop`** — a fuel opportunity. `mile: float`, `name: str`, `lat`, `lon`.

**`POI`** — a named GPX waypoint projected onto the route for the strip. `mile`,
`name: str`, `lat`, `lon`, `kind: str` (`"waypoint"` default or `"food"`, see
`POIKind`), `symbol: str | None`.

**`Segment`** — a named road stretch. `name: str`, `start_mile: float`,
`end_mile: float`, plus a `length_miles` property.

**`RouteSpan`** — an unpaved or ferry stretch drawn as a styled ribbon.
`start_mile`, `end_mile`, `kind: str` (`"unpaved"` or `"ferry"`, see `SpanKind`),
`name: str | None` (ferry/road name), plus a `length_miles` property.

**`FuelReport`** — the fuel-gap analysis on `route.fuel_report`. `longest_gap_miles:
float` (the longest distance between fuel opportunities), `recommended: list[str]`,
`exceeds_range: bool` (does the longest gap exceed the rider's range?),
`fuel_range_miles: float | None` (the range used).

### `ValidationReport` and `Finding`

`validate()` returns a `ValidationReport` (`gpxsheet.ValidationReport`):

- `report.route` → the analyzed [`Route`](#route)
- `report.findings` → `list[Finding]`
- `report.name` / `report.length_miles` → convenience properties delegating to
  the route

Each `Finding` (`gpxsheet.Finding`) is `level: str` (`"warning"` | `"info"`),
`code: str` (`"fuel"` | `"unpaved"` | `"ferry"` | `"seasonal"`), `message: str`.
A clean route within range yields only `info` notes; gaps, unpaved miles, a
ferry, or a seasonal pass surface `warning`s. The `unpaved`/`ferry`/`seasonal`
checks need OSM hazard data — when it's unavailable they emit an `info` "skipped
(no OSM data)" note instead of a verdict. The `seasonal` check is a hybrid of a
curated seasonal-road list and OSM `seasonal`/`*:conditional` tags
(`gpxsheet.seasonal`).
