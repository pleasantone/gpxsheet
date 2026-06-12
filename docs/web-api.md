# GPXSheet Web API — front-end integration guide

This guide is for a web developer building a UI on top of the GPXSheet service.
It covers what the product does, the one mental model the API follows, every
endpoint, and how to drive them from a browser (with worked `fetch` examples).

## Why this exists

GPXSheet turns a GPX route into **glanceable, map-centric motorcycle tank-bag
navigation aids** for sport-touring (the [design notes](product.md) cover the
goals). The service takes a rider's exported GPX and produces:

- a **roadbook-style PDF** (or PNG) — the route broken into a sequence of
  schematic "strips," each showing the shape of the road, the decision points
  (where you actually have to do something), road names, and fuel;
- a **route table** (markdown or HTML) — waypoints, cumulative distance,
  fuel/lunch markers, ETAs and sunrise/sunset, for a glanceable trip plan;
- a **structured analysis** of the route (decision points, segments, fuel
  stops) as JSON, so a UI can render its own view;
- a **validation report** flagging fuel-range gaps, unpaved stretches, and ferry
  crossings.

Route structure (which turns are real decisions vs. just curves, road names,
fuel) comes from OpenStreetMap, so rendering a route is real work — seconds for a
rural route, longer for dense urban areas. That's why **everything is an
asynchronous job**.

## The one mental model: submit → poll → fetch

Every operation works the same way:

1. **Submit** a job: `POST` the GPX plus parameters to a typed endpoint
   (`/v1/render`, `/v1/table`, `/v1/analyze`, or `/v1/validate`). You get back a
   job `{id, status, ...}` and a `Location` header pointing at the job.
2. **Poll** the job: `GET /v1/jobs/{id}` until `status` is `done` or `error`.
3. **Fetch** the result: `GET /v1/jobs/{id}/result` — a PDF/PNG download or a
   JSON report.

If you submit an identical request again, you get the same finished job back
immediately (results are cached), so polling is often a no-op.

- **Base path:** all operations live under `/v1`. Health probes (`/healthz`,
  `/readyz`) are unversioned.
- **Uploads** are `multipart/form-data`: the GPX file in a field named `gpx`,
  every other parameter as a form field.
- **Job IDs** are opaque, unguessable strings.

## Authentication

If the operator configures API keys, **every `/v1/*` request must authenticate**
(the health probes do not). Send either header:

```
X-API-Key: <your-key>
# or
Authorization: Bearer <your-key>
```

When keys are enabled, **a job is only visible to the key that created it** —
another key polling or fetching that job ID gets `404`. Rate limits are also
per-key. When keys are not configured (e.g. local dev), the API is open and
limits are per-IP.

## Endpoints

### `POST /v1/render` — produce a map (PDF or PNG)

Form fields (all optional except `gpx`):

| field | type | default | values / meaning |
|-------|------|---------|------------------|
| `gpx` | file | — | the `.gpx` upload (**required**) |
| `layout` | string | `portrait` | `portrait`, `landscape`, `preview`, `strip` (see below) |
| `format` | string | `pdf` | `pdf` or `png` |
| `profile` | string | `sport-touring` | `minimalist`, `sport-touring`, `rally` — how much detail to show |
| `fuel_range` | number | — | rider range in miles; enables fuel-gap analysis |
| `turn_style` | string | `stylized` | `stylized` (schematic bends) or `faithful` (true angles) |
| `paper` | string | `letter` | `letter` or `a4` (paginated PDF layouts only) |
| `lanes_per_page` | int ≥ 1 | `4` | strip lanes per page (`portrait` only) |
| `decisions_per_lane` | int ≥ 0 | `0` | max decisions per page/lane (`portrait` / `landscape` / `preview`); the default **`0` = auto-fit** as many as fit each lane (pass a positive number to force a fixed cap) |
| `show_branches` | bool | `false` | draw ghosted "roads not taken" stubs at junctions |

**Layouts:**

- `portrait` — the roadbook: several stacked strip "lanes" per page, multi-page.
  The default, designed for a tank bag.
- `landscape` — one large strip per page, multi-page.
- `preview` — the whole route as a single continuous image (no page breaks); the
  best choice for an on-screen overview / thumbnail.
- `strip` — a single schematic map strip of the entire route.

**Format × layout:** any layout works in either format. A `pdf` of a paginated
layout (`portrait`/`landscape`) is multi-page; a `png` of one stacks every page
into a single tall image. `preview` and `strip` are single images in either
format.

Returns a job (see [Job lifecycle](#job-lifecycle)). The finished result's
`content_type` is `application/pdf` or `image/png`.

### `POST /v1/table` — route table (markdown or HTML)

A glanceable trip-planning table: each named waypoint with cumulative distance,
a `G`/`L`/`GL` fuel/lunch marker, ETA, and the symbol; plus a sunrise/sunset
line. Multi-track GPX renders one section per day. Built on the same analysis as
`/v1/render`, so OSM enrichment adds auto-discovered fuel, a Road column and
road-snapped distance.

Form fields (all optional except `gpx`):

| field | type | default | values / meaning |
|-------|------|---------|------------------|
| `gpx` | file | — | the `.gpx` upload (**required**) |
| `format` | string | `html` | `html` or `markdown` |
| `departure` | string | — | natural-language or ISO time ("9:00 AM", "July 4 2pm"); **required for the ETA column** |
| `timezone` | string | — | IANA zone for displayed times (e.g. `US/Pacific`) |
| `speed` | number ≥ 0 | `0` | average speed (mph imperial / kph metric); **`0` = auto** — OSM per-segment speed limits, else 30 mph. A positive value overrides OSM speeds with a flat speed |
| `units` | string | `imperial` | `imperial` or `metric` |
| `coordinates` | bool | `false` | add latitude/longitude columns |
| `cue` | bool | `false` | append a turn-by-turn cue sheet from the decision points |
| `osm` | bool | `true` | OSM enrichment (auto fuel, road names, road-snapped distance); `false` is fast and fully offline |

Returns a job whose result `content_type` is `text/html` or `text/markdown`.
The HTML is the same table wrapped in a `gpxtable` CSS class you can style; the
markdown is what's shown below. A real run (`format=markdown`, `departure="9:00
AM"`, `timezone=US/Pacific`) of a route with named waypoints:

```markdown
## Route: Table Test Route
* Departure at Fri Jun 12 09:00:00 2026 PDT
* Total distance: 45 mi
* Default speed: 30.00 mph

| Name                           |   Dist. | GL |  ETA  | Notes
| :----------------------------- | ------: | -- | ----: | :----
| Start Cafe                     |       0 |    | 09:00 | Restaurant
| Nicasio Square                 |       7 |    | 09:14 | Restroom (+0:15)
| Shell Gas Station              |   19/19 |  G | 09:53 | Gas Station (+0:15)
| Pat's Diner                    |      32 |  L | 10:34 | Restaurant (+1:00)
| Trailhead                      |   26/46 |    | 12:01 | Flag

* 06/12/26: Sunrise: 05:45, Starts: 09:00, Ends: 13:31, Sunset: 20:34
```

Reading the columns: `Dist.` is cumulative miles, and once past the first fuel
stop becomes `since-gas/total` (so `19/19` then `26/46` means 26 mi since the
last gas on a 46-mi running total); `GL` flags **G**as / **L**unch stops; `ETA`
is the arrival clock time (needs `departure`); `Notes` carries the symbol and any
layover (`+0:15`, `+1:00`). The header/footer line gives departure, total
distance, the speed basis, and sunrise/sunset.

**With OSM on (the default)**, the table also auto-discovers fuel, snaps
distances to the road, derives per-segment speed limits (so the ETA is variable,
not a flat average), and adds a **Road** column. The same pipeline on an
OSM-enriched clip yields a row the GPX never named — the fuel station and road
come straight from OpenStreetMap, the speed from its `maxspeed` tags:

```markdown
* Speed: OSM limits (avg 32.40 mph)

| Name                           |   Dist. | GL |  ETA  | Road                     | Notes
| :----------------------------- | ------: | -- | ----: | :----------------------- | :----
| Canyon Auto Service            |   14/14 |    | 09:24 | Farm Hill Boulevard      | Gas Station
```

### `POST /v1/analyze` — structured route analysis (JSON)

The same OSM-enriched analysis that drives the map and the table, returned as
plain JSON so a UI can render its own view (a list of decisions, a segment
timeline, fuel markers) instead of an image.

Form fields (all optional except `gpx`):

| field | type | default | values / meaning |
|-------|------|---------|------------------|
| `gpx` | file | — | the `.gpx` upload (**required**) |
| `profile` | string | `sport-touring` | `minimalist`, `sport-touring`, `rally` — the detail cut (see below) |
| `fuel_range` | number | — | rider range in miles; sets `longest_fuel_gap_miles` and is what a UI compares the gap against |

OSM enrichment always runs: road names, the turn-vs-curve distinction, and
fuel discovery come from OpenStreetMap (the analysis falls back to geometry-only,
with coarser road names and no auto-fuel, only when the route is too sparse to
snap or Overpass is unreachable).

Returns a job whose result is `application/json`. A real OSM-enriched run (the
`profile=sport-touring`, `fuel_range=180` analysis of a short clip through a
roundabout) looks like:

```json
{
  "name": "Riverbank roundabout clip (La Loma Ave)",
  "length_miles": 2.0,
  "decision_points": [
    {"mile": 0.0, "instruction": "Left at the fork", "significance": 60},
    {"mile": 0.6, "instruction": "Continue onto La Loma Avenue", "significance": 40},
    {"mile": 0.9, "instruction": "Take the 2nd exit onto La Loma Avenue", "significance": 50},
    {"mile": 1.9, "instruction": "Continue onto Needham Street", "significance": 40}
  ],
  "fuel_stops": [],
  "segments": [
    {"name": "Yosemite Boulevard", "start_mile": 0.0, "end_mile": 0.6},
    {"name": "La Loma Avenue", "start_mile": 0.6, "end_mile": 1.9},
    {"name": "Needham Street", "start_mile": 1.9, "end_mile": 2.0}
  ],
  "longest_fuel_gap_miles": 2.0
}
```

**Response fields:**

| field | type | meaning |
|-------|------|---------|
| `name` | string | the route name (from the GPX, else a fallback) |
| `length_miles` | number | total route length, one decimal |
| `decision_points` | array | where the rider must act — see below |
| `fuel_stops` | array | `{mile, name}` per fuel opportunity, in route order |
| `segments` | array | `{name, start_mile, end_mile}` named road stretches, contiguous and in order |
| `longest_fuel_gap_miles` | number \| null | longest distance between fuel opportunities (route start/end count as endpoints); `null` when the profile omits fuel |

Each **decision point** is `{mile, instruction, significance}`:

- `instruction` is a human-readable cue derived from OSM road names and the
  turn geometry — `"Continue onto <road>"` for a straight-through name change,
  `"<Left|Right|Sharp left|…> onto <road>"` for a turn, `"<Left|Right> at the
  fork"`, or `"Take the Nth exit onto <road>"` at a roundabout.
- `significance` is 0–80: higher = more consequential (a sharp turn or a
  state-highway junction scores higher than a gentle residential name change).
  The **`profile` gates this**: a decision survives only if its significance
  clears the profile's threshold — `minimalist` = 55, `sport-touring` = 40,
  `rally` = 30. So the same route returns fewer, higher-stakes decisions under
  `minimalist` (here, only the `significance: 60` fork) and more under `rally`.

**`fuel_stops` / `longest_fuel_gap_miles`** populate from OSM-discovered fuel
(plus any fuel waypoints in the GPX). The roundabout clip above is too short to
pass a station, so `fuel_stops` is empty; on a real touring route they fill in —
e.g. a longer clip returns `"fuel_stops": [{"mile": 13.7, "name": "Canyon Auto
Service"}]` with `"longest_fuel_gap_miles": 13.7`. The `minimalist` profile
omits fuel entirely (`fuel_stops: []`, `longest_fuel_gap_miles: null`); use
`sport-touring` or `rally` for fuel.

### `POST /v1/validate` — route warnings (JSON)

Same form fields and OSM-enriched analysis as `/v1/analyze` (`gpx` required,
plus `profile`, `fuel_range`). Returns a job whose JSON result lists findings.
A real run (the OSM-enriched 15 mi clip with a deliberately tight
`fuel_range=10` to trip the gap check):

```json
{
  "name": "Enrich Fixture (gaia 15mi clip)",
  "length_miles": 14.8,
  "findings": [
    {"level": "warning", "code": "fuel", "message": "Longest fuel gap 14 mi exceeds the 10 mi range."},
    {"level": "info", "code": "ferry", "message": "Ferry check skipped (no OSM data)."},
    {"level": "info", "code": "seasonal", "message": "Seasonal-closure risk is not checked yet (see TODO.md)."}
  ]
}
```

Each finding has a `level` (`warning` or `info`) and a `code`:

| `code` | `warning` when… | `info` when… |
|--------|-----------------|--------------|
| `fuel` | the longest fuel gap exceeds `fuel_range` | no `fuel_range` given, or the profile omits fuel |
| `unpaved` | the route has ≥0.2 mi of unpaved/track surface | the OSM surface data wasn't available (a "skipped" note) |
| `ferry` | a ferry crossing is on the route (named) | the OSM ferry data wasn't available (a "skipped" note) |
| `seasonal` | — (not implemented yet) | always present, as a reminder it isn't checked |

So a clean route within range is a successful job with only `info` notes; a route
with a fuel gap, unpaved miles, or a ferry surfaces `warning`s. The `unpaved` and
`ferry` checks need OSM hazard data — when it's present they're either a `warning`
(found) or silent (clear); the `info` "skipped (no OSM data)" note above appears
only when that data is unavailable (sparse route, or Overpass unreachable).

Warnings do **not** fail the job — a route with warnings is still a successful
job; read the findings.

### `GET /v1/jobs/{id}` — job status

```json
{
  "id": "9f2c…",
  "status": "done",
  "error": null,
  "result_url": "/v1/jobs/9f2c…/result",
  "content_type": "application/pdf"
}
```

`status` is one of `queued`, `running`, `done`, `error`. When `error`, `error`
holds a safe, human-readable message. When `done`, `content_type` tells you what
the result is and `result_url` is where to get it (a relative path, or an
absolute pre-signed URL when object storage is in front).

### `GET /v1/jobs/{id}/result` — the artifact

- `200` with the bytes (`Content-Type` matches the job's `content_type`). Maps
  come back as a download (`Content-Disposition: attachment`) with a filename
  derived from the route name; JSON reports are served inline.
- `303` redirect to a pre-signed download URL when object storage is configured
  (follow it). 
- `425 Too Early` if the job isn't finished yet — keep polling the status URL
  (honor `Retry-After`).
- `409` if the job failed (the body's `detail` is why).
- Results are immutable: responses carry an `ETag` and a long-lived
  `Cache-Control`. Send `If-None-Match` to get a `304`.

### `GET /healthz` and `GET /readyz`

`/healthz` → `200 {"status":"ok"}` if the process is up. `/readyz` → `200` only
when the job store and result storage are reachable, else `503`. Use these for
uptime checks, not in the normal request flow.

## Job lifecycle

```
POST /v1/render ──▶ 202 { id, status:"queued" }   (Location: /v1/jobs/{id})
                     │
        ┌────────────┘  poll GET /v1/jobs/{id}
        ▼
   status:"running" ──▶ status:"done"  ──▶ GET /v1/jobs/{id}/result ──▶ 200 bytes
                   └──▶ status:"error" ──▶ GET …/result ──▶ 409 (reason)
```

- **Submit returns `202`** when work was queued, or **`200`** when the result
  already exists (an identical earlier request, or a synchronous dev server).
  Either way the body is the job and `Location` is the job URL.
- **Poll** `GET /v1/jobs/{id}` until `status` is terminal (`done`/`error`). If a
  `Retry-After` header is present (on the `202` or on a `425` result), wait that
  many seconds before the next poll; otherwise a 1–2 s interval is reasonable.
- Don't hard-code timeouts: a large urban route can take a while. Show progress
  and let the user cancel.

## Rate limiting

Over the limit returns `429` with `Retry-After` (seconds) and `RateLimit-Limit`
/ `RateLimit-Remaining` / `RateLimit-Reset`. Back off accordingly.

## Errors

| status | when | body |
|--------|------|------|
| `400` | empty upload or not a GPX document | `{"detail": "..."}` |
| `401` | missing/invalid API key (when keys are enabled) | `{"detail": "..."}` |
| `404` | unknown job, or a job owned by a different key | `{"detail": "..."}` |
| `409` | fetching the result of a **failed** job | `{"detail": "<reason>"}` |
| `413` | upload too large, or too many track/route points | `{"detail": "..."}` |
| `422` | invalid parameter value | `{"detail": [ … ]}` (FastAPI validation) |
| `425` | result not ready yet | `{"detail": "job is running"}` |
| `429` | rate limited | `{"detail": "rate limit exceeded"}` |

There are upload limits (a max byte size and a max point count); oversized
uploads are rejected up front with `413`, before any work starts.

## Browser / CORS notes

- The operator must allow your origin (and the `X-API-Key` / `Authorization` /
  `Content-Type` headers) via CORS for cross-origin calls. Same-origin needs no
  config.
- When the result is a `303` to a pre-signed object-storage URL, that download
  is a **different origin**; either let the browser navigate to it (e.g. set
  `window.location` / an `<a download>`), or ensure the object store allows your
  origin if you `fetch` it.
- Never put API keys in client-side code for a public site — proxy through your
  own backend, or scope keys tightly.

## Worked example (browser, `fetch`)

```js
const BASE = "https://gpxsheet.example.com";
const HEADERS = { "X-API-Key": "…" }; // omit if the API is open

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Submit a render job and return the finished job status.
async function renderRoute(gpxFile, { layout = "portrait", format = "pdf", fuelRange } = {}) {
  const form = new FormData();
  form.append("gpx", gpxFile);            // a File/Blob from <input type=file>
  form.append("layout", layout);
  form.append("format", format);
  if (fuelRange != null) form.append("fuel_range", String(fuelRange));

  const res = await fetch(`${BASE}/v1/render`, { method: "POST", headers: HEADERS, body: form });
  if (!res.ok) throw new Error(`submit failed: ${res.status} ${await res.text()}`);
  return pollJob(res.headers.get("Location") ?? `/v1/jobs/${(await res.json()).id}`);
}

// Poll a job URL until it finishes.
async function pollJob(jobUrl) {
  for (;;) {
    const res = await fetch(`${BASE}${jobUrl}`, { headers: HEADERS });
    if (!res.ok) throw new Error(`poll failed: ${res.status}`);
    const job = await res.json();
    if (job.status === "done") return job;
    if (job.status === "error") throw new Error(`job failed: ${job.error}`);
    await sleep(Number(res.headers.get("Retry-After") ?? 2) * 1000);
  }
}

// Download a finished map result as a blob URL (PDF or PNG).
async function fetchResult(job) {
  const res = await fetch(`${BASE}${job.result_url}`, { headers: HEADERS }); // follows 303
  if (!res.ok) throw new Error(`result failed: ${res.status}`);
  return URL.createObjectURL(await res.blob()); // -> use as <embed>/<img> src or download
}

// JSON reports: analyze / validate
async function analyzeRoute(gpxFile) {
  const form = new FormData();
  form.append("gpx", gpxFile);
  const res = await fetch(`${BASE}/v1/analyze`, { method: "POST", headers: HEADERS, body: form });
  const job = await pollJob(res.headers.get("Location"));
  return (await fetch(`${BASE}${job.result_url}`, { headers: HEADERS })).json();
}
```

## Worked example (curl)

```bash
# Submit (preview PNG), capture the job id
id=$(curl -s -F gpx=@route.gpx -F layout=preview -F format=png \
        https://gpxsheet.example.com/v1/render | jq -r .id)

# Poll until done
until [ "$(curl -s https://gpxsheet.example.com/v1/jobs/$id | jq -r .status)" = done ]; do sleep 2; done

# Fetch the image (follow a possible 303 with -L)
curl -sL https://gpxsheet.example.com/v1/jobs/$id/result -o route.png

# A JSON report
curl -s -F gpx=@route.gpx https://gpxsheet.example.com/v1/analyze   # then poll + fetch as above

# A markdown route table with ETAs (poll + fetch as above)
curl -s -F gpx=@route.gpx -F format=markdown -F 'departure=9:00 AM' \
        https://gpxsheet.example.com/v1/table
```

## Interactive reference

The service serves live OpenAPI docs at **`/docs`** (Swagger UI) and the schema
at **`/openapi.json`** — every endpoint, parameter, and response code, generated
from the running service.
