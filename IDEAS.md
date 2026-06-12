# GPXSheet — Feature Ideas

Brainstormed feature ideas for what a motorcycle rider on a touring trip might
want, beyond the current navigation-awareness core. These deliberately set aside
the stated non-goals ("not a rally roadbook", "not a GPS replacement") to explore
a wider space. As-built status is in [docs/product.md](docs/product.md); planned
work in [TODO.md](TODO.md).

## The reframe

Today the product answers *navigation* questions (what road, next decision, how
far, where in the route). A touring rider's real anxieties are broader:
**weather, fuel/range, the quality of the ride itself, and "what if something
goes wrong out here."** Extend "awareness" from *where am I* to *what am I riding
into* — reusing the OSM route graph already built (and the self-hosted Overpass
in `osm/`, which makes heavy enrichment cheap).

## Top picks (highest value × best fit)

1. **Weather-along-the-route, at your ETA.** The table already computes a
   per-waypoint ETA and has lat/lon. Key a forecast API on
   `(lat, lon, arrival_time)` and add **temp / wind / precip** columns, plus a
   `weather` validate finding for the bike-dangerous case: **crosswind/gust
   warnings** ("35 mph gusts crossing the CA-58 ridge ~2pm") and "rain near mile
   120 around 3pm." Arguably the #1 touring concern; slots into the existing
   table + validate seams.

2. **Elevation profile + mountain-pass summits.** `GeoPoint.ele` already exists;
   OSM tags pass summits (`mountain_pass=yes`, `ele`). Add a thin **elevation
   sparkline** to the strip / per-day header and mark **pass summits with
   elevation**. Pairs with the seasonal-closure check ("Tioga summit 9,945 ft —
   pack for 40°F"). Mostly data already held.

3. **Curviness / "fun factor" per segment.** Pure geometry — bearings and turn
   angles are already measured. Score each segment's twistiness and surface it as
   a **"Twisty" rating** (a column, or strip shading mellow→technical). Riders
   *choose* routes for this; no new data source.

4. **"No services for N miles" + dead-zone safety.** Fuel gaps are already
   computed; generalize to **services** (fuel/food/lodging) and add **cell-coverage
   dead zones** (FCC broadband data or a crowd map). For a solo rider in the
   Sierra/PNW, "no fuel **and** no cell for 47 mi — top off + tell someone" is a
   safety-relevant glance using the same gap-analysis machinery.

5. **GPX "backup nav" export.** Emit the *enriched* route — decisions as named
   waypoints, fuel/POIs, day breaks — as a **GPX/Garmin file** to load back into
   the rider's actual GPS. The sheet is the glance, the device is the backup, both
   from one analysis. Mostly serialization + a `/v1/export` op on the existing
   route graph.

## Broader menu, by theme

### Conditions
- Smoke / air-quality overlay (wildfire season is real in CA/PNW).
- Golden-hour / "you'll be riding in the dark after mile X" (sun times already
  exist).
- Heat / cold + altitude → a **gear-packing hint** per day.

### Fuel & range
- Tank-range rings ("with 180 mi range, your safe top-off point is the 76 at mile
  145").
- Premium-availability / 24-hr / fuel-price annotations on stops.

### The ride itself (rider POIs)
- Scenic overlooks & viewpoints (`tourism=viewpoint`), National/State **Scenic
  Byway** tagging, photo stops.
- Motorcycle dealers / tire shops / repair (`shop=motorcycle`) — peace of mind on
  a long trip.
- Famous moto roads & landmarks ("you're about to ride [road]").

### Safety
- Nearest **hospital/ER** along route + a printable **emergency-info card** (blood
  type, contacts, bike VIN/plate).
- **Wildlife corridors** (deer/elk crossing zones) and known gravel/construction
  stretches as cautions.

### Multi-day
- **Per-day cards**: miles, ride time, fuel stops, elevation gain, sunset,
  suggested overnight — `day_breaks`/`day_names` already exist.
- **Lodging/camping at day-ends** (`tourism=hotel|motel|camp_site`), with a "this
  day is 450 mi / 9 hr — consider splitting" nudge.
- A trip **overview page** (whole-route thumbnail + day summary table).

### Social / group rides
- A **staging/meet point** + "regroup at each fuel stop," and per-rider table
  splits (lead/sweep).

## Bolder, imagination-on (these lean into the dropped non-goals)

- **Live companion view** (phone/web): your dot against the schematic strip,
  next-decision countdown, live weather/closures, and a quiet "you're off-route"
  nudge — explicitly *backup*, not turn-by-turn.
- **Voice "next decision" earbud cue** at a set distance — eyes-up, glance-free.
- **Post-ride layer**: replay the actual recorded track over the planned sheet —
  "where did we stop, how close were the ETAs" — feeding back into better profiles.
- **Community road ratings**: crowd-sourced twistiness/scenery/pavement that
  refines the curviness score over time.

## How these map to what exists

- **Table columns / findings**: weather, twisty, services, dead-zones,
  golden-hour — all ride on the existing `analyze` → table/validate seams.
- **Strip overlays**: elevation sparkline, pass summits, scenic/POI markers —
  extend the renderer's existing span/POI drawing.
- **New `analyze`/endpoint fields**: elevation, curviness, weather, POIs —
  additive to the JSON the SPA already consumes.
- **Synergy with `osm/`**: viewpoints, byways, dealers, wildlife, lodging are all
  extra OSM queries — cheap against the self-hosted Overpass, painful against the
  public one.

## Most shovel-ready

**Weather-at-ETA** and **elevation/passes** are the most ready given what's
already in the route graph (per-waypoint ETA + lat/lon; `GeoPoint.ele` + OSM pass
tags). **Curviness** is the cheapest (pure geometry, no new data source).
