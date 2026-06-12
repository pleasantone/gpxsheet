# Library API

The public Python API mirrors the [web API](web-api.md): the entry points —
`render`, `analyze`, `validate` — take the same names and arguments (but run
synchronously). Import them from the top-level `gpxsheet` package. The route
**table** lives in `gpxsheet.routetable` (see [Route table](#route-table) below).

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

## Render

`layout` (`portrait` · `landscape` · `preview` · `strip`) and `format` (`pdf` ·
`png`) are independent; portrait PDF is the default. `format=None` (the default)
infers the format from the output filename extension (`.png` → `"png"`, anything
else → `"pdf"`).

::: gpxsheet.render

## Analyze

::: gpxsheet.analyze

## Validate

::: gpxsheet.validate

::: gpxsheet.ValidationReport

::: gpxsheet.Finding

## Route table

A markdown/HTML route table (waypoints, distances, fuel/lunch markers, ETAs,
sunrise/sunset) rendered from the same analysis graph, so it inherits OSM
enrichment (auto-discovered fuel, road names, road-snapped distance) and adds a
timing layer. It lives in `gpxsheet.routetable` (not the top-level namespace):

```python
from gpxsheet.routetable import render_table, parse_departure

depart, tz = parse_departure("9:00 AM", "US/Pacific")  # natural-language or ISO
render_table("route.gpx", "route.md", fmt="markdown", departure=depart, tz=tz)
# OSM is on by default; pass osm=False for a fast, fully offline table.
# ETAs need a departure; show_cue=True appends a turn-by-turn cue sheet.
```

`render_table` analyzes `gpx_source` and writes `html` or `markdown`;
`build_table_markdown(route, …)` renders an already-analyzed `Route`.

::: gpxsheet.routetable.render_table

## Lower-level helpers

::: gpxsheet.load_route

::: gpxsheet.analyze_route

## Route model

The analysis returns a populated `Route`. These are the dataclasses you'll read
off it.

::: gpxsheet.models.Route

::: gpxsheet.models.DecisionPoint

::: gpxsheet.models.Segment

::: gpxsheet.models.FuelStop

::: gpxsheet.models.GeoPoint
