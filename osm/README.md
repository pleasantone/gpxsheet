# Self-hosted OSM Overpass — California

A standalone Docker Compose stack that self-hosts an [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API)
server populated with **all OpenStreetMap data for California**. It imports the
Geofabrik California extract, keeps it current from Geofabrik's per-region diffs,
and serves the standard Overpass QL/XML API on a local port.

This is a self-contained sub-project — it does **not** modify or depend on the
rest of GPXSheet. It exists so you can point OSM tooling at a fast, local,
rate-limit-free Overpass instead of the public `overpass-api.de`.

## What you get

- **Image:** [`wiktorn/overpass-api`](https://hub.docker.com/r/wiktorn/overpass-api) —
  the de-facto containerized Overpass distribution (bundles the import, the
  dispatcher, area generation, and the diff updater).
- **Data:** the full Geofabrik **California** extract (`california-latest.osm.pbf`).
- **Freshness:** the container polls Geofabrik's
  [`california-updates/`](https://download.geofabrik.de/north-america/us/california-updates/)
  diff feed **every 12 hours** by default and applies all changes published
  since the last run. Tune the cadence with `OVERPASS_UPDATE_SLEEP`.
- **History:** current data only (`OVERPASS_META=no`) — no attic/object history.
  Smaller and faster; sufficient for POI/road/geometry queries. (No augmented-diff
  `adiff` support in this mode.)
- **Persistence:** the imported DB lives in a named Docker volume
  (`gpxsheet-overpass-db`) mounted at `/db`, so it survives `docker compose down`
  and container upgrades. The expensive first-boot import is **not** repeated on
  restart.

## Requirements

- Docker Engine with the Compose v2 plugin (`docker compose`, not the legacy
  `docker-compose`).
- **Disk:** budget **~60–80 GB** of free space for the volume. The California PBF
  is ~1.3 GB compressed; the expanded Overpass database (current-data-only) plus
  working space lands in this range and grows slowly as diffs accumulate.
- **RAM:** ~2–4 GB is comfortable for a regional extract.
- **Network egress** to `download.geofabrik.de` for the initial import and for
  ongoing diffs.

> [!NOTE]
> If you're running this from a Claude Code web/sandbox session, outbound network
> is restricted by the environment's policy. Geofabrik must be reachable for the
> import to succeed — run the stack on a host (or in an environment) with network
> access to `download.geofabrik.de`.

## Quick start

```bash
cd osm
cp .env.example .env        # optional — tune ports / region / cadence
docker compose up -d        # first run downloads + imports California
docker compose logs -f      # watch the import progress
```

Or via the Makefile:

```bash
make up        # docker compose up -d
make logs      # follow logs
make status    # curl /api/status
make query     # run the sample query
make down      # stop (keeps the DB volume)
make nuke      # stop AND delete the DB volume (forces full re-import)
```

### First-boot import timeline

The **first** `up` is slow: it downloads ~1.3 GB, imports it into the Overpass
DB, and generates area objects. Expect **30–90+ minutes** depending on disk and
CPU. During this window `/api/status` is not yet answering and the container's
healthcheck reports `starting` (the `start_period` is set to 2h precisely so the
import doesn't get flagged unhealthy). Watch `docker compose logs -f` for
progress; the updater loop starts once the import completes.

Subsequent `up`s are near-instant — the entrypoint sees the populated `/db`
volume and skips straight to serving + updating.

## Using the API

Once `make status` returns a status payload, the endpoints are:

- Interpreter (queries): `http://localhost:12345/api/interpreter`
- Status: `http://localhost:12345/api/status`

(Port is `OVERPASS_PORT`, default `12345`.)

Example — fuel stations within 3 km of Mt Hamilton, via the bundled script:

```bash
make query
# or:
ENDPOINT=http://localhost:12345 ./scripts/query.sh
```

Equivalent raw call:

```bash
curl -G http://localhost:12345/api/interpreter \
  --data-urlencode 'data=[out:json][timeout:60];
    node(around:3000, 37.3414, -121.6429)["amenity"="fuel"];
    out body;'
```

## Configuration

All knobs live in `docker-compose.yml` with overridable defaults; copy
`.env.example` to `.env` to change them. The common ones:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OVERPASS_PORT` | `12345` | Host port the API is published on. |
| `OVERPASS_PLANET_URL` | California PBF | Region extract to import. |
| `OVERPASS_DIFF_URL` | California updates | Matching diff feed for auto-updates. |
| `OVERPASS_UPDATE_SLEEP` | `43200` | Seconds between diff polls (default every 12h). |
| `OVERPASS_SPACE` | `2147483648` | Dispatcher scratch space (bytes). |
| `OVERPASS_MAX_TIMEOUT` | `1000` | Max query runtime advertised to clients (s). |

### Serving a different region

Override **both** `OVERPASS_PLANET_URL` and `OVERPASS_DIFF_URL` with a matching
Geofabrik pair (the extract and its `*-updates/` feed must be the same region),
then re-import from a clean volume:

```bash
make nuke    # drop the old DB volume
# edit .env with the new region URLs
make up
```

## Operations

- **Logs / progress:** `docker compose logs -f`
- **Is it ready?** `make status` (or `curl localhost:12345/api/status`)
- **Re-import from scratch:** `make nuke && make up` (deletes the volume).
- **Stop without losing data:** `make down` (the named volume persists).
- **Inspect the volume:** `docker volume inspect gpxsheet-overpass-db`

### Troubleshooting

- **Import seems stuck / container "unhealthy":** the first import legitimately
  takes a long time; the healthcheck shows `starting` until `/api/status`
  answers. Check the logs for active download/import lines before assuming a
  failure.
- **`update` errors about replication state:** the diff feed must match the
  extract region. If you changed `OVERPASS_PLANET_URL` without `OVERPASS_DIFF_URL`
  (or vice versa), re-import with `make nuke && make up`.
- **Out of disk during import:** the expanded DB is much larger than the PBF —
  ensure the Docker volume's backing storage has the headroom noted in
  *Requirements*.

## Notes & references

- Upstream image docs: <https://github.com/wiktorn/Overpass-API>
- Geofabrik California: <https://download.geofabrik.de/north-america/us/california.html>
- Overpass QL language guide: <https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL>
