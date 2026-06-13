# Group-Ride Planning — design notes (from the ride-leader interview)

> Status: **designed, not built.** Captured from a structured interview with the
> product owner (a group-ride leader), 2026-06-13. The existing product serves
> the *solo rider's glance*; this layer serves the *ride leader's pre-planning*.
> Build order was decided explicitly: **Phase 1 first** — everything else
> consumes its outputs. This is a pre-planning tool; nothing here runs on the
> bike in real time.

## The gap, in one line

The product analyzes the **route**; a group ride is a route **plus a group plus
a schedule plus a distribution problem** — none of which the tool models today.

## What the interview decided

| Topic | Decision |
|---|---|
| Group model | **Headcount + minimum fuel range** only. No pace/skill modeling — the leader judges pace. |
| Regroups | At planned fuel/lunch stops, **plus named regroup points the leader picks**. The tool *suggests candidates*, never auto-places. No corner-man/waves support. |
| Contingency | **Bail-out routes only** (ER/cell/roster/breakdown layers explicitly declined). |
| Timing | Stop overhead is **headcount-scaled for gas/restroom** stops (base + per-rider), **fixed for lunch (default 1 h)**. Cruising speed stays OSM-based. |
| Plan state | A **plan file next to the GPX** (`ride.yaml`) is the format and ships first; **server-saved plans** come later as a persistence layer over the *same* format. |
| Bail-outs | Leader **marks exit points**; tool computes the **fastest paved path to the nearest major highway** from each, names the roads, measures miles. |
| GPX re-export | All targets: **Garmin** (route + `trp:ViaPoint` + proper `<sym>` — the mirror of the BaseCamp loader we already have), **universal plain GPX** for phone apps, **QR code on the briefing** → hosted download, **per-day files** for multi-`<trk>` tours. |
| Briefing core | **Route thumbnail (preview strip) + compact stop table** (mile, what, mandatory-fuel flag, ETA) + staging/KSU. Leader phones / separation protocol / riding-rules blurb are *optional plan-file fields*, not must-haves. |
| Road freshness | All three: **DOT/511 closures + construction**, **burn-scar / long-term fire damage** (beyond active perimeters), **event conflicts** (hardest source, big payoff). |
| Stop vetting | All three: **suggest + score candidates** (parking size, pumps, seating), **recon deep links** (maps/street-view/satellite per decision + stop), **reviews/hours** (key-gated source, e.g. Google Places, following the Phase-3 key-gating pattern). |

## Phase 1 — group plan file + group math (build first)

The foundation. Small, testable, and every artifact consumes its outputs.

- **`ride.yaml` schema** (passed alongside the GPX; CLI `--plan`, web `plan`
  multipart field):
  - `group:` `riders: N`, `min_fuel_range_mi:` (the smallest tank coming)
  - `schedule:` `ksu:` (kickstands-up), `staging:` name + optional lat/lon
  - `leaders:` list of `{role: lead|sweep, name, phone}` (optional)
  - `stops:` overrides — mark a waypoint as `regroup`, `mandatory_fuel`,
    `lunch` (with `duration_min`, default 60)
  - `bailouts:` leader-marked exit points (name + lat/lon or waypoint ref)
  - `text:` reusable blurbs (separation protocol, riding rules) — optional
- **Group-aware fuel:** gap analysis against `min_fuel_range_mi`, emitting
  *mandatory fuel* designations ("with a 120-mi tank in the group, everyone
  fuels at mile 95") as findings + table/sheet markers.
- **Group-aware timing:** `waypoints.py` already assigns per-stop `delay` by
  classified type — make gas/restroom delay `base + per_rider × N` (tunable),
  lunch a fixed block. The after-dark check inherits the honest math for free;
  the **lunch ETA becomes reservation-grade**.

## Phase 2 — artifacts (the hand-built-email killers)

- **Rider briefing one-pager** (`brief` op): preview-strip thumbnail + stop
  table + staging/KSU; optional sections render only if the plan file provides
  them; **QR codes** → hosted GPX + share page.
- **Leader/sweep packet**: the briefing + full route table/cue sheet +
  **bail-out section** (per exit point: road names, miles to the major highway).
- **Enriched GPX re-export** (`/v1/export`): the analyzed route with
  regroup/fuel/lunch as named waypoints — Garmin-convention and plain variants,
  optional per-day split. We parse these conventions already; this is the writer.
- **Share link**: hosted read-only plan page (the SPA exists; needs short-lived
  result links first, full co-lead editing only after server-saved plans).

## Phase 3 — freshness validate (independent; can parallel Phase 2)

New providers under `gpxsheet/live/` (graceful + cached, same env conventions):
- **511/DOT closures + construction** along the corridor (Caltrans API first).
- **Burn-scar damage**: long-term closures / signal-controlled sections through
  recent fire areas (active perimeters are already built).
- **Event conflicts**: parades/festivals/centuries sharing the corridor that
  date — hardest data source; treat as best-effort findings.

All surface as `validate` findings + day-card warnings ("CA-168 one-way control
at mile 42 — Caltrans, updated yesterday").

## Phase 4 — stop intelligence

- **Regroup candidate suggestion + scoring**: pullouts/parking polygons after
  long no-stop stretches, pump counts, group seating — leader picks from
  candidates (decision stays human).
- **Recon deep links** (cheap — may ride along Phase 2): per decision point and
  stop, Google Maps / street-view / satellite URLs in the leader packet & SPA.
- **Reviews/hours** for lunch/fuel candidates ("closed Sundays") via a
  key-gated source, following the AirNow/OpenWeather Phase-3 key pattern.

## Later — server-saved plans

Persistence over the `ride.yaml` format (not a new format): co-leads edit one
plan, the share link stays live. Requires accounts/storage; intentionally after
the stateless phases prove the artifact set.
