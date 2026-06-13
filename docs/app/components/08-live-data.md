# 08 — Live Data (weather + wildfire)

v1 conditions: **weather-at-ETA** and **wildfire perimeters**, both **keyless**,
**graceful**, and **cached**. Mirrors gpxsheet's `live/` providers (proven). Later
phases add 511 closures, events, air, reviews. Parent: [`../SPEC.md`](../SPEC.md).
Depends on engine (01, for sample points + ETAs) and group math (10, for group
ETAs).

## Provider contract

```python
class Provider(Protocol):
    name: str
    def fetch(self, request) -> Result | None   # None = unavailable → skip + Finding
```
- Every response cached on disk (record/replay for tests); per-provider TTL.
- A provider down/unreachable ⇒ return `None`, attach `Finding(info,…,"… unavailable")`,
  never raise. Gate with `LIVE_DISABLED` / `OFFLINE` env (copy gpxsheet's
  `sources.py` env convention: `<SRC>_CACHE_DIR / DISABLE_<SRC> / RECORD_<SRC> /
  *_BASE_URL`, umbrella `OFFLINE`).

## Weather (Open-Meteo, keyless)

- Sample the route at intervals + at each stop; for each sample compute the
  **group ETA** (from group math) and query Open-Meteo hourly forecast at
  `(lat, lon, nearest_hour(eta))`: temp, feels-like, wind speed/gust/dir, precip
  prob/amount, visibility, WMO code.
- **Crosswind**: project wind vector onto the route bearing at the sample →
  per-sample crosswind (the bike-dangerous signal). gpxsheet already does this.
- Output per stop (shown in the share view + briefing) + summary findings:
  - `Finding(warning,"wind","Gusts ≤40 mph crossing the ridge ~mile 60 (2pm)")`
  - `Finding(warning,"weather","Rain likely near mile 120 ~3pm (70%)")`
- Beyond the ~16-day forecast horizon → a `note`, empty samples (don't fail).
- Needs a `departure`/KSU; without it, weather is skipped.

## Wildfire (NIFC / WFIGS perimeters, keyless)

- Query current incident perimeters near the route bbox; for any within a buffer,
  emit `Finding(warning,"fire","King Fire perimeter ~3 mi off route near mile
  88")` with distance + (if available) status + info URL. On-route → "on route".
- Attribution: "Wildfire perimeters: NIFC / WFIGS".

## Attribution (required)

Surface a `sources` list on the plan/share view + briefing footer:
`["Map data © OpenStreetMap contributors (ODbL)", "Weather © Open-Meteo (CC BY
4.0)", "Wildfire: NIFC / WFIGS"]` — include only sources actually used.

## Where it shows

- **Map:** fire perimeter overlay; per-stop weather chip.
- **Share view + briefing:** a conditions block per stop + the findings.
- **`plan.computed.findings`:** merged with fuel/dark/services findings.

## Acceptance criteria

- With a KSU set, each stop gets a weather sample at its group ETA; crosswind is
  computed from bearings.
- A fixture route near a recorded fire perimeter yields a `fire` finding.
- Providers disabled/`OFFLINE` ⇒ plan still computes, conditions omitted with an
  info finding, no error.
- Deterministic offline tests via committed live fixtures (cache-only).
