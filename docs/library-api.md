# Library API

The public Python API. Import everything from the top-level `gpxsheet` package:

```python
from gpxsheet import analyze, generate_pdf

route = analyze("route.gpx", fuel_range=180)
generate_pdf("route.gpx", "route.pdf", orientation="portrait")
```

OSM enrichment runs as part of analysis, falling back to the geometry baseline
when a route is too sparse to sample or the Overpass query fails.

## Generating output

::: gpxsheet.generate_pdf

::: gpxsheet.generate_strip

## Analysis

::: gpxsheet.analyze

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
