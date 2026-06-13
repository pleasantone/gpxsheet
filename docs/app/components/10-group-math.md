# 10 — Group Math (fuel · timing · bail-outs)

The group-aware layer over a Route's analysis. **Cheap, recomputed per read**
(never persisted — mirrors gpxsheet `derive_products`). Parent:
[`../SPEC.md`](../SPEC.md). Depends on engine (01), geo-infra (02 for bail-outs).

Input: a `Plan` (group, schedule, stops, leaders) + its `Route.analysis`.
Output: `plan.computed` (fuel / timing / findings) returned inline by the API.

## 1. Group fuel (vs the group's smallest tank)

The binding constraint is the **smallest fuel range in the group**
(`group.min_fuel_range_mi`), not the leader's.

- Take fuel opportunities = `route.fuel_stops` ∪ stops with role `fuel`.
- Walk the route; whenever the distance since the last fuel opportunity would
  exceed `min_fuel_range_mi × SAFETY (0.9)`, the **last reachable** fuel
  opportunity becomes **mandatory** (`Stop.mandatory=true` semantics, surfaced as
  a marker + `Finding(warning,"fuel","Mandatory fuel at mile 95 — 130 mi gap > 120 mi group range")`).
- `longest_gap_mi`, `gap_exceeds_range` for the header. If a gap **cannot** be
  covered (no fuel in range), emit `Finding(warning,"services","No fuel for 140 mi …")`.

## 2. Group timing (honest ETAs)

Cruising speed comes from the Route's `speed_samples_mph` (OSM `maxspeed`/class),
or a flat plan speed override. **Stop overhead is the group-specific part** — and
the owner's rule is explicit:

- **Gas / restroom stops scale with headcount:**
  `overhead_min = GAS_BASE + GAS_PER_RIDER × riders`
  (defaults `GAS_BASE=8`, `GAS_PER_RIDER=1.5`; tunable per plan later).
  A 14-rider fuel stop is ~30 min, not 10.
- **Lunch is a fixed block:** `LUNCH_DEFAULT_MIN = 60` (overridable per stop via
  `Stop.duration_min`). Not headcount-scaled.
- **Regroup** stops: a small fixed `REGROUP_MIN = 5–10` (configurable).

ETA walk:
```
t = ksu
for each stop in mile order:
    t += riding_time(prev_mile → stop.mile, speed_samples)
    arrive = t
    t += overhead(stop)          # gas: scaled · lunch: fixed · regroup: small
    depart = t
finish = ksu + total_riding + Σ overhead
```
Return `per_stop:[{stop_id, arrive, depart, overhead_min}]` + `finish`. The
**lunch arrival must be reservation-grade** (overhead of all stops before it is
applied) — call this out in tests.

## 3. After-dark check (for the GROUP)

Using the group-overhead timeline + sun times (sunset at the route end for the
day, computed from lat/lon/date like gpxsheet `timing.sun_times`):
- If `finish > sunset` → `Finding(warning,"dark","Group finishes ~45 min after
  sunset; riding after dark from ~mile 150")`, with the first mile whose group-ETA
  passes sunset. Groups leaving at 9 with 4 scaled stops hit dusk **far** earlier
  than the solo math predicts — that's the point of doing it group-aware.
- Multi-day: per-day sunset, +24h/day.

## 4. Bail-outs (leader-marked exits → fastest paved way out)

For each `BailOut` the leader places (see API 03, geo-infra 02):
1. Snap the exit to the route (mile).
2. Find the nearest **major-highway** node (`motorway|trunk|primary`, configurable)
   via PostGIS nearest on the seeded `highways` table.
3. `valhalla.route(exit → node, costing=motorcycle, avoid unpaved)`.
4. Store `route_geom`, `exit_miles`, `exit_roads` (names traversed).

Surface in the **leader/sweep packet** as: "Bail-out @ mile 80 (Mt Aukum Rd):
14 mi via Mt Aukum Rd → E16 → US-50 (major highway)." The leader picks the exit
points; the tool only measures + names + routes (per the interview decision).
Bail-out routing is a **job** (Valhalla call), cached per `(plan, exit_point)`.

## Constants (start here, tune with evidence)

```
FUEL_SAFETY = 0.9
GAS_BASE_MIN = 8 ; GAS_PER_RIDER_MIN = 1.5
LUNCH_DEFAULT_MIN = 60
REGROUP_MIN = 8
MAJOR_HWY_CLASSES = ("motorway","trunk","primary")
```
Expose these as plan-level overrides later; defaults in config now.

## Acceptance criteria

- Min-range 120 on a route with a 130-mi dry stretch → exactly one mandatory-fuel
  marker at the correct stop + a `fuel` finding.
- Bumping `riders` 4→14 measurably pushes `finish` later and can flip `after_dark`
  on — without re-running analysis (pure recompute).
- Lunch ETA equals KSU + riding + all prior scaled gas/regroup overhead +
  fixed lunch; reservation-grade.
- Bail-out from a mid-route exit returns a paved route to a primary/trunk road
  with road names + miles (fixture-backed, offline).
- Nothing here is persisted; toggling group inputs never enqueues a job.
