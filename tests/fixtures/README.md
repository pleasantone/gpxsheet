# Test fixtures

The test suite must stay deterministic and offline. We do that by replaying
**committed Overpass responses** instead of hitting the live API.

## Files

- `enrich_route.gpx` — a real onshore route (a ~15 mi clip of a Bay Area GaiaGPS
  track) that exercises the full OSM enrichment path: durable road-name
  decisions, named segments, and OSM fuel. Used by
  `tests/test_enrich.py::test_enrich_route_against_cached_osm`.
- `osm_cache/` — osmnx's HTTP response cache (`*.json`, one file per Overpass
  query, named by SHA-1 of the request URL). Committed so CI/offline runs never
  touch the network.
- `live_cache/` — the day-card **live provider** response cache (Open-Meteo
  weather/air/elevation, NIFC wildfire). Same idea as `osm_cache/`: one `*.json`
  per request, named by a hash of `(provider, url, params)`. Empty by default —
  `tests/test_live.py` seeds canned payloads in-process (no network), so a
  committed corpus is only needed if you record real responses.

## How replay works

`tests/conftest.py` (the session-autouse `_osm_cache` fixture) points osmnx at
`osm_cache/` (`ox.settings.cache_folder`, `use_cache=True`) and — unless
recording — replaces `osmnx._overpass._overpass_request` with a cache-only
stand-in. A cache **miss raises** (`OSM Overpass cache miss in offline test
mode`) rather than silently going to the network, so a missing/stale fixture
fails loudly.

The offshore synthetic `l_route` fixture (built in `conftest.py`) deliberately
has no OSM coverage: its query returns no drivable graph, so enrichment falls
back to geometry-only. That empty/again-cached response lives in `osm_cache/`
too.

## Re-recording

When you change a fixture route, the enrichment queries, or the osmnx version,
re-record the cache (this is the only step that needs network):

```bash
GPXSHEET_RECORD_OSM=1 .venv/bin/pytest          # record every query the suite makes
# or just the enrichment test:
GPXSHEET_RECORD_OSM=1 .venv/bin/pytest tests/test_enrich.py
```

In record mode the offline guard is disabled, osmnx's rate-limit pauses are
skipped, and responses are written into `osm_cache/`. Commit the updated `*.json`
files. Then confirm the suite still passes offline:

```bash
.venv/bin/pytest -q
```

## Re-recording live providers

The day-card live providers use the same record/replay split, gated by
`GPXSHEET_RECORD_LIVE`. The autouse `_live_cache` fixture points the
live-provider cache at `live_cache/` and, unless recording, stubs the single
network seam (`gpxsheet.live.base._http_get_json`) to a cache-only stand-in
(a miss returns `None`, so the section is simply omitted). To capture real
responses (needs network + the Open-Meteo / NIFC hosts on the allowlist):

```bash
GPXSHEET_RECORD_LIVE=1 .venv/bin/pytest tests/test_live.py
```

Set `GPXSHEET_DISABLE_LIVE=1` to force fully static cards (no network at all).
