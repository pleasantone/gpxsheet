# GPXSheet

> Motorcycle sport-touring route awareness generator.

GPXSheet converts GPX routes into glanceable, map-centric motorcycle navigation
aids optimized for tank-bag use. Route *structure* — which turns are real
decisions versus mere curves, road names, and fuel — comes from OpenStreetMap
rather than raw geometry, so the output reflects the road network instead of
flooding twisty roads with false turns. See the [design notes](product.md) for
the goals and the engineering behind it.

Three ways to use it:

- **CLI** — `gpxsheet generate route.gpx -o route.pdf` (also `table`, `analyze`,
  `strip`, `preview`, `validate`).
- **Python library** — see the [Library API](library-api.md).
- **Web service** — a FastAPI app exposing the engine over REST; see the
  [Web API guide](web-api.md) and the [API reference](web-api-reference.md).

## Install

```bash
pip install gpxsheet              # library + CLI
pip install "gpxsheet[service]"   # + the web service
```

## Quick links

- [Library API](library-api.md) — `render`, `analyze`, `validate`, and the route model.
- [Web API guide](web-api.md) — the submit → poll → fetch job model, with
  browser `fetch` examples.
- [Web API reference](web-api-reference.md) — interactive OpenAPI for every
  endpoint.
- [Deployment](deploy.md) — hosting and hardening for public exposure.
- [Design notes](product.md) — the full product/engineering specification.
