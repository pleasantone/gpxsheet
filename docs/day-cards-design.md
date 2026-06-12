# Day Cards — design

A **per-day, read-ahead briefing** for a touring rider — distinct from the
tank-bag **sheet** (`render`) and **table**, which stay untouched. A day card is a
*planning-time snapshot* (it can pull richer, even live data), one card per day
(`Route.day_breaks`/`day_names`), surfaced as a new `daycard` output (md / HTML /
JSON) alongside `render`/`table`/`analyze`/`validate`.

## Locked decisions

- **Live data:** live-by-default but **graceful** — keyless sources (Open-Meteo
  weather/air/elevation, NIFC fire) run; **key-gated** sources (AirNow,
  OpenWeather, OpenCelliD) are **skipped when no key is configured**. **Cache**
  every response so duplicate/adjacent queries don't hammer servers.
  `GPXSHEET_DISABLE_LIVE=1` (or the umbrella `GPXSHEET_OFFLINE=1`) forces
  static-only (used by the offline sandbox/CI). See the shared external-data-source
  env convention in `gpxsheet.sources` / [deploy.md](deploy.md).
- **Trip timing:** reuse the table's `--departure` (+24h per day). **No departure
  → static-only** (skip weather / golden-hour / after-dark).
- **Output:** new `daycard` op → **md / HTML + structured JSON**; also a
  `day_cards` field in the `analyze` JSON for the SPA.
- **Weather provider default:** **Open-Meteo** (free, global, no key, batchable,
  easy to record for tests) — also covers air-quality + elevation, keyless.

## Module layout

- `src/gpxsheet/daycard.py` — builds `list[DayCard]` from an analyzed `Route`;
  renders md/HTML/JSON (mirrors `routetable.py`).
- `src/gpxsheet/live/` — `base.py` (provider interface + on-disk cache),
  `weather.py`, `air.py`, `fire.py`, `elevation.py`, `cell.py`; OSM-backed bits
  extend `enrich` (`passes`, `viewpoints`, `construction`, `wildlife`).
- Reuse: `timing.sun_times`/`SpeedProfile` (ETAs/sun), `enrich.features_from_polygon`
  (OSM features), `validate.Finding` (warnings), `routetable.markdown_to_html`.

## Provider interface

```python
class Provider:
    name: str
    requires_key: str | None      # env var; if set & missing -> skip w/ note
    base_url_env: str | None       # overridable, like GPXSHEET_OVERPASS_BASE_URL
    def fetch(self, route, day_window) -> Result | None   # None = unavailable
```

- Live-by-default; key-gated providers skip silently without their key.
- **Cache** keyed on `(provider, rounded lat/lon, date/hour)` in
  `GPXSHEET_LIVE_CACHE_DIR`.
- **Graceful degradation:** any failure (no key, network down, past forecast
  horizon) omits that section with an "unavailable" note; the card still renders
  — same idiom as the OSM geometry-only fallback.

## `DayCard` data model (JSON-serializable)

`index, name, date?, start/end_mile, miles, moving_time, arrive/depart`;
`sun` (rise/set / **golden hours** / **after-dark** flag + "dark after mile X");
`elevation` (min/max/gain + `passes:[{name,mile,ele}]`); `weather`
(`samples:[{mile,time,temp,feels,wind,gust,crosswind,precip_prob,vis,code}]` +
`source`/`as_of`); `air` (max AQI/PM2.5 + smoke flag); `fire:[{name,dist_mi,status,url}]`;
`scenic:[{mile,name,kind}]`; `gravel/construction/wildlife` spans;
`dead_zones:{no_services:[…], cell:[…]}`; `warnings:[Finding…]`; `attributions`,
`generated_at`. Warnings reuse `Finding(level, code, message)` with new codes
(`weather/wind/heat/cold/precip/smoke/fire/dark/wildlife/construction/services/cell`).

## Feature source & gating

| Feature | Source | Gating | Hard part |
|---|---|---|---|
| Day stats, sun, golden-hour/after-dark | `astral` + ETAs | always (needs date) | none |
| Passes / scenic / viewpoints | OSM (`mountain_pass`, `tourism=viewpoint`, `natural=peak`) | always (offline-cacheable) | byway tags sparse |
| Gravel | already computed (`unpaved_miles`/spans) | always | — |
| No-services dead zones | reuse fuel-gap + POI gaps | always | defining "service" |
| Construction / wildlife | OSM (`highway=construction`, `hazard=animal_crossing`) | always | stale/sparse in OSM |
| Elevation profile | GPX `ele` if sane, else Open-Meteo Elevation | keyless live | noisy GPX ele; many points |
| Weather (+crosswind) | Open-Meteo (crosswind from route bearings) | keyless live | forecast horizon; sampling |
| Smoke / AQI | Open-Meteo Air-Quality (keyless); AirNow if key | live; AirNow key-gated | smoke forecast short |
| Wildfire perimeters | NIFC/IRWIN ArcGIS | keyless live | polygon intersect; volatile |
| Cell dead zones | OpenCelliD (key) / FCC | key-gated; Phase 3 | per-carrier, contested |

## Date/time

`parse_departure` → start dt+tz; day *d* date = departure + *d*×24h, ETAs from
`SpeedProfile`. Weather/elevation sampled ~every 25–30 mi at the interpolated
coord + that point's ETA. Past Open-Meteo's ~16-day horizon → weather skipped with
a note. No `--departure` → static-only.

## CLI / library / web

- **CLI:** `gpxsheet daycard <gpx> --departure "Sat 8am" --timezone US/Pacific
  --units imperial --format md|html|json -o cards.md`.
- **Library:** `gpxsheet.daycard(gpx, departure=…, …)` → `list[DayCard]`;
  `daycard.render_day_cards(route, …)`.
- **Web:** `"daycard": DayCardParams` in `_PARAMS_BY_OP` (`service/jobs.py`),
  `DayCardParams` (`service/models.py`), `_daycard_result` (`service/render.py`),
  `POST /v1/daycard` (`service/app.py`); result `text/markdown` / `text/html` /
  `application/json`. Server-side keys via env. Also a `day_cards` field in the
  `analyze` JSON.

## Determinism & tests

An autouse fixture wires providers to a committed `tests/fixtures/live_cache`
and runs **cache-only** (miss → skip), mirroring the OSM harness in `conftest.py`;
record with `GPXSHEET_RECORD_LIVE=1`. CI/sandbox set `GPXSHEET_DISABLE_LIVE=1`
so the suite is fully offline. Pure logic (crosswind/sun/gaps) unit-tested directly.

## Env vars (GPXSHEET_*)

`GPXSHEET_AIRNOW_API_KEY`, `GPXSHEET_OPENWEATHER_API_KEY`,
`GPXSHEET_OPENCELLID_API_KEY` (optional; gate keyed providers);
`GPXSHEET_LIVE_CACHE_DIR`; `GPXSHEET_DISABLE_LIVE` (or umbrella `GPXSHEET_OFFLINE`);
`GPXSHEET_RECORD_LIVE`; per-provider `*_BASE_URL` overrides (self-host/proxy/
testing), like `GPXSHEET_OVERPASS_BASE_URL`. These follow the shared external-data-
source convention in `gpxsheet.sources` (see [deploy.md](deploy.md)).

## Phased build

- **Phase 1 — offline/computable (no new network):** the `daycard` op end-to-end
  (CLI/lib/web, md/HTML/JSON) with day stats, sun + golden-hour + after-dark,
  passes/scenic/construction/wildlife from OSM (best-effort), gravel, no-services
  dead zones, warnings aggregation. Fully testable offline.
- **Phase 2 — keyless live:** Open-Meteo weather (+crosswind), air/smoke,
  elevation; NIFC wildfire. Provider + cache + record/replay harness.
- **Phase 3 — key-gated / hardest:** AirNow, OpenWeather, and cell-coverage
  (OpenCelliD/FCC, flagged approximate).

## Decisions taken (small)

- **Elevation:** prefer GPX `ele` when present & plausible, else Open-Meteo
  Elevation (Phase 2).
- **Cell:** deferred to Phase 3 (key-gated); no fake "remoteness" heuristic
  labelled as coverage.

## Phase 2 — DONE

Phase 2 is built: `src/gpxsheet/live/` (`base` cache + graceful HTTP seam,
`weather`, `air`, `elevation`, `fire`) wired into `daycard.build_day_cards` behind
a `live=` flag (plus `--live/--no-live`, the `live` web field, and
`GPXSHEET_DISABLE_LIVE`). Weather carries per-sample **crosswind** (route bearing
vs `wind_direction_10m`); warnings gained `heat`/`cold`/`wind`/`precip`/`smoke`/
`fire`. Determinism mirrors the OSM harness — autouse `_live_cache` in
`conftest.py` replays a committed `tests/fixtures/live_cache` cache-only
(record with `GPXSHEET_RECORD_LIVE=1`); pure bits (crosswind, nearest-hour,
horizon, fire intersect, cache/gating) are unit-tested in `tests/test_live.py`.
**Remaining: Phase 3** (key-gated AirNow/OpenWeather, cell coverage). The original
kickoff plan, kept for reference:

### Phase 2 — kickoff (original plan)

Phase 1 (offline) is merged: `gpxsheet.daycard` + `daycard` CLI + `/v1/daycard`,
with the `DayCard` model already carrying slots for weather/air/fire/elevation.
Phase 2 adds the **keyless live providers** behind a cached, graceful interface.

**0. Verify network (new session).** The env allowlist should now include
`api.open-meteo.com`, `air-quality-api.open-meteo.com`, `services3/9.arcgis.com`,
`overpass-api.de`, `download.geofabrik.de`. Sanity-check: `curl -s
'https://api.open-meteo.com/v1/forecast?latitude=37&longitude=-122&hourly=temperature_2m'`
and `curl -s https://overpass-api.de/api/status`. Re-run a real day card so
**passes + scenic** populate live (the Phase-1 POI query was degrading offline).

**1. Provider layer** — `src/gpxsheet/live/`:
- `base.py`: `Provider` (name, `requires_key: str|None`, `base_url_env`, `fetch`),
  an on-disk response cache keyed on `(provider, round(lat,2), round(lon,2),
  date/hour)` under `GPXSHEET_LIVE_CACHE_DIR`, and a `GPXSHEET_DISABLE_LIVE`
  short-circuit (→ skip, return None). Key-gated providers return None (with a
  card note) when their key env is unset. Wrap all I/O so any failure degrades.
- `weather.py` (Open-Meteo `/v1/forecast`, keyless): hourly `temperature_2m,
  apparent_temperature, wind_speed_10m, wind_gusts_10m, wind_direction_10m,
  precipitation_probability, precipitation, visibility, weather_code`. Sample
  every ~25–30 mi at each point's ETA; pick the nearest hour. Batch points via
  comma-separated `latitude`/`longitude`. Past ~16-day horizon → skip with a note.
- `air.py` (Open-Meteo Air-Quality, keyless): `us_aqi, pm2_5` → smoke flag.
- `elevation.py` (Open-Meteo Elevation, keyless): only when GPX `ele` is missing.
- `fire.py` (NIFC current perimeters, ArcGIS feature service on
  `services3.arcgis.com`): query the route bbox envelope, intersect polygons with
  the route corridor (shapely), report name/distance/status.

**2. Crosswind (the differentiator).** At each weather sample, route heading =
`geo.bearing` between bracketing points; wind blows *from* `wind_direction_10m`.
`crosswind = wind_speed * sin(Δ)` where `Δ` = angle between the route heading and
the wind-from bearing. Warn on high gusts/crosswind (thresholds in `daycard.py`).

**3. Wire into `daycard.build_day_cards`.** Add params (e.g. `live: bool = True`,
provider toggles); populate `DayCard.weather/air/fire/elevation_profile`; extend
`_warnings` with `weather`/`wind`/`smoke`/`fire` codes; render the new sections in
`build_day_cards_markdown` + `to_dict`. `DayCardParams` (service) gains the knobs.

**4. Determinism/tests.** Mirror the OSM harness in `tests/conftest.py`: an
autouse fixture points providers at a committed `tests/fixtures/live_cache`
and runs **cache-only** (miss → skip); record with `GPXSHEET_RECORD_LIVE=1`.
CI/sandbox set `GPXSHEET_DISABLE_LIVE=1`. Unit-test the pure bits directly
(crosswind, nearest-hour, horizon skip, fire-polygon intersect).

**5. Env vars (all `GPXSHEET_*`):** `LIVE_CACHE_DIR`, `DISABLE_LIVE`,
`RECORD_LIVE`, per-provider `*_BASE_URL` overrides; Phase-3 keys
`AIRNOW_API_KEY`, `OPENWEATHER_API_KEY`, `OPENCELLID_API_KEY`.

**Docs to update on completion:** `web-api.md` (new daycard fields), `library-api.md`
(`DayCard` fields), `product.md`, `CLAUDE.md`, `TODO.md` (tick Phase 2).
