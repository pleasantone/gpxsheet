# 02 — Geo Infrastructure (Overpass · Valhalla · Tiles)

Self-hosted geospatial backbone, all in docker-compose. No runtime third-party
keys. Parent: [`../SPEC.md`](../SPEC.md). Consumers: analysis engine (01), group
math (10), frontend map (06).

## Services

| Service | Image (suggested) | Role |
|---|---|---|
| `overpass` | `wiktorn/overpass-api` | Corridor POI / tag queries (fuel, viewpoints, junction tags). Seeded from a regional `.osm.pbf`. The repo's existing `osm/` subproject is prior art. |
| `valhalla` | `ghcr.io/valhalla/valhalla` (or `gis-ops/docker-valhalla`) | **Map-matching** (`/trace_attributes`), **routing** (`/route`) for bail-outs, optional isochrones. Tiles built from the same extract. |
| `tileserver` | `maptiler/tileserver-gl` | Vector tiles + a style for MapLibre. Serve an OpenMapTiles regional `.mbtiles`. |
| `seed` (one-shot) | custom | Downloads/uses the configured `.osm.pbf`, loads Overpass, builds Valhalla tiles, places the `.mbtiles`. Idempotent; guarded by a marker volume. |

### Default region

A single configured **regional extract** (`REGION_PBF`, e.g. Geofabrik
`norcal`/`california`) feeds all three. Document disk/RAM per region and the
swap procedure. Owner picks the shipped default (open question in SPEC §8).

## Client interfaces (Python, in `convoy/geo/`)

All clients are **providers** (conventions §Providers): timeout + bounded retry,
then raise a typed **`GeoUnavailable`** on a *hard down* — and the caller **does
not degrade**; it surfaces a clean error (these are hard deps). Each client
**normalizes** its response to typed JSON (no raw OSM geometry leaks out) and
**caches on disk** keyed by request hash (record/replay for tests). The Overpass
client in particular returns *filtered, normalized, de-duplicated* features, so
the rest of the system treats OSM exactly like any other provider's data.

```python
class ValhallaClient:
    def trace_attributes(self, coords: list[LatLon]) -> MatchResult:
        """Map-match a GPX polyline. Returns matched shape + per-edge
        {names, road_class, surface, speed_limit, length}. Powers analysis
        geometry + most enrichment in one call."""
    def route(self, frm: LatLon, to: LatLon, *, costing="motorcycle",
              exclude=("unpaved",)) -> RouteResult:
        """Fastest paved route. Used for bail-outs (frm=exit, to=nearest
        major-highway node) and 'fastest way to major highway' targets."""

class OverpassClient:
    def corridor_features(self, polyline: list[LatLon], buffer_m: float,
                          tags: dict[str,str]) -> list[Feature]:
        """LineString → buffer polygon → features (amenity=fuel, tourism=
        viewpoint, junction tags, mountain_pass, surface). Mirrors the old
        enrich corridor query."""
```

`motorcycle` costing in Valhalla supports avoiding unpaved (`use_tracks` low,
`exclude` surfaces) — important for "fastest **paved** path to a major highway".

## Bail-out routing (used by Group Math §10)

Given a leader-marked exit `point`:
1. Find the nearest OSM node of class `motorway|trunk|primary` (PostGIS nearest
   on a `highways` table seeded from the extract, or Valhalla `locate`).
2. `valhalla.route(point, that_node, costing="motorcycle", avoid unpaved)`.
3. Return road names traversed + total miles for the leader packet.

"Major" highway class is configurable (SPEC §8 open question — likely
`motorway,trunk,primary`).

## Tiles / MapLibre

- `tileserver-gl` serves `/styles/<style>/style.json` + `/data/<region>/{z}/{x}/{y}.pbf`.
- Frontend points MapLibre at the tileserver style URL (same origin via the API
  reverse-proxy, so the PWA can cache tiles offline for a plan's bbox).
- Provide a **clean, legible touring style** (muted, high road-name contrast).

## Seeding & ops

- `make geo-seed` (or compose `seed` service) runs once; subsequent boots skip
  if the marker volume exists.
- Document: extract source/license (ODbL attribution required on the map),
  rebuild after a region change, and approximate build time/disk.
- Health: `/readyz` checks Overpass `/api/status`, Valhalla `/status`, tileserver
  `/health`.

## Acceptance criteria

- `valhalla.trace_attributes` returns matched geometry + edge names/surface/speed
  for a sample GPX; analysis consumes it.
- `valhalla.route` returns a paved bail-out route avoiding gravel.
- `overpass.corridor_features` returns fuel stations for a known corridor
  (committed fixture for tests).
- All three reachable via `/readyz`; **Overpass or Valhalla stopped ⇒ analyze
  jobs fail with a clear typed error** (hard deps) and `/readyz` goes red — they
  do **not** emit degraded output. (Tileserver down only affects the map view.)
- Overpass client returns normalized, clustered, de-duplicated fuel features
  (raw OSM messiness handled in the client, not leaked downstream).
- Compose `up` from clean → `seed` populates everything → analysis works offline.
