# Library API

The public Python API mirrors the [web API](web-api.md): three entry points —
`render`, `analyze`, `validate` — that take the same names and arguments (but run
synchronously). Import everything from the top-level `gpxsheet` package.

**Breaking changes in v0.3.0:**

- `render()`: `decisions_per_lane` is now `int = 0` (was `int | None = None`); `None`
  is no longer a valid value — pass `0` for auto-fit.
- `analyze()`: the `reassurance_interval` parameter has been removed; the interval
  is now controlled entirely by the profile (`Profile.reassurance_interval_miles`).
  To use a custom interval, construct a `Profile` and pass it to `analyze_route()`.
- CLI: `gpxsheet analyze --reassurance-interval` flag is removed.

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
`png`) are independent; portrait PDF is the default.

::: gpxsheet.render

## Analyze

::: gpxsheet.analyze

## Validate

::: gpxsheet.validate

::: gpxsheet.ValidationReport

::: gpxsheet.Finding

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
