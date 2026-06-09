# GPXSheet

> Motorcycle sport-touring route awareness generator.

GPXSheet converts GPX routes into highly **glanceable, map-centric** motorcycle
navigation aids optimized for **tank-bag** use. It is *not* a rally roadbook and
*not* a GPS replacement — the goal is route **awareness**: a rider should be able
to glance at the sheet for under a second and immediately grasp what road they're
on, what the next navigation decision is, how far off it is, what comes after,
and where they are along the whole route.

Route *structure* — which turns are real decisions versus mere curves, road
names, and fuel — is derived from OpenStreetMap rather than raw geometry, so the
output reflects the road network instead of flooding twisty roads with false
turns.

## What you can do with it

- **Generate** a roadbook-style **PDF** (or PNG) of a route — schematic strips
  showing road shape, decision points, names, and fuel.
- **Analyze** a route into structured data (decision points, segments, fuel
  stops) for your own tooling.
- **Validate** a route for fuel-range gaps, unpaved stretches, and ferries.

Three ways to use it:

- **CLI** — `gpxsheet generate route.gpx -o route.pdf` (also `analyze`, `strip`,
  `preview`, `validate`).
- **Python library** — see the [Library API](library-api.md).
- **Web service** — a FastAPI app exposing the engine over REST; see the
  [Web API guide](web-api.md) and the [API reference](web-api-reference.md).

## Install

```bash
pip install gpxsheet              # library + CLI
pip install "gpxsheet[service]"   # + the web service
```

## Quick links

- [Library API](library-api.md) — `generate_pdf`, `analyze`, and the route model.
- [Web API guide](web-api.md) — the submit → poll → fetch job model, with
  browser `fetch` examples.
- [Web API reference](web-api-reference.md) — interactive OpenAPI for every
  endpoint.
- [Deployment & security](security-audit.md) — hardening for public exposure.
- [Design notes](design.md) — the full product/engineering specification.
