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
  `GPXSHEET_DISABLE_LIVE=1` forces static-only (used by the offline sandbox/CI).
- **Trip timing:** reuse the table's `--departure` (+24h per day). **No departure
  → static-only** (skip weather / golden-hour / after-dark).
- **Output:** new `daycard` op → **md / HTML + structured JSON**; also a
  `day_cards` field in the `analyze` JSON for the SPA.
- **Weather provider default:** **Open-Meteo** (free, global, no key, batchable,
  easy to record for tests) — also covers air-quality + elevation, keyless.

## Module layout

- `src/gpxsheet/daycard.py` — builds `list[DayCard]` from an analyzed `Route`;
  renders md/HTML/JSON (mirrors `routetable.py`).
- `src/gpxsheet/providers/` — `base.py` (provider interface + on-disk cache),
  `weather.py`, `air.py`, `fire.py`, `elevation.py`, `cell.py`; OSM-backed bits
  extend `enrich` (`passes`, `viewpoints`, `construction`, `wildlife`).
- Reuse: `timing.sun_times`/`SpeedProfile` (ETAs/sun), `enrich.features_from_polygon`
  (OSM features), `validate.Finding` (warnings), `routetable.markdown_to_html`.

## Provider interface

```python
class Provider:
    name: str
    requires_key: str | None      # env var; if set & missing -> skip w/ note
    base_url_env: str | None       # overridable, like GPXSHEET_OVERPASS_URL
    def fetch(self, route, day_window) -> Result | None   # None = unavailable
```

- Live-by-default; key-gated providers skip silently without their key.
- **Cache** keyed on `(provider, rounded lat/lon, date/hour)` in
  `GPXSHEET_PROVIDERS_CACHE_DIR`.
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

An autouse fixture wires providers to a committed `tests/fixtures/providers_cache`
and runs **cache-only** (miss → skip), mirroring the OSM harness in `conftest.py`;
record with `GPXSHEET_RECORD_PROVIDERS=1`. CI/sandbox set `GPXSHEET_DISABLE_LIVE=1`
so the suite is fully offline. Pure logic (crosswind/sun/gaps) unit-tested directly.

## Env vars (GPXSHEET_*)

`GPXSHEET_AIRNOW_API_KEY`, `GPXSHEET_OPENWEATHER_API_KEY`,
`GPXSHEET_OPENCELLID_API_KEY` (optional; gate keyed providers);
`GPXSHEET_PROVIDERS_CACHE_DIR`; `GPXSHEET_DISABLE_LIVE`; per-provider
`*_BASE_URL` overrides (self-host/proxy/testing), like `GPXSHEET_OVERPASS_URL`.

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
