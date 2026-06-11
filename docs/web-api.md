# GPXSheet Web API — front-end integration guide

This guide is for a web developer building a UI on top of the GPXSheet service.
It covers what the product does, the one mental model the API follows, every
endpoint, and how to drive them from a browser (with worked `fetch` examples).

## Why this exists

GPXSheet turns a GPX route into **glanceable, map-centric motorcycle tank-bag
navigation aids** for sport-touring. A rider plans a route in their mapping tool
of choice, exports the GPX, and wants something they can actually read at a
glance in a tank-bag while moving — not a turn-by-turn list and not a full map.

The service takes that GPX and produces:

- a **roadbook-style PDF** (or PNG) — the route broken into a sequence of
  schematic "strips," each showing the shape of the road, the decision points
  (where you actually have to do something), road names, and fuel;
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
   (`/v1/render`, `/v1/analyze`, or `/v1/validate`). You get back a job `{id,
   status, ...}` and a `Location` header pointing at the job.
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

### `POST /v1/analyze` — structured route analysis (JSON)

Form fields: `gpx` (required), `profile`, `fuel_range`. Returns a job whose
result is `application/json`:

```json
{
  "name": "Skyline Loop",
  "length_miles": 74.8,
  "decision_points": [
    {"mile": 12.3, "instruction": "Right onto CA-9", "significance": 70}
  ],
  "fuel_stops": [{"mile": 41.0, "name": "76 Bodega Bay"}],
  "segments": [{"name": "Skyline Blvd", "start_mile": 0.0, "end_mile": 12.3}],
  "longest_fuel_gap_miles": 63.0
}
```

Use this to build your own UI (a list of decisions, a segment timeline, fuel
markers) instead of rendering an image.

### `POST /v1/validate` — route warnings (JSON)

Form fields: `gpx` (required), `profile`, `fuel_range`. Returns a job whose JSON
result lists findings; `level` is `warning` or `info`, `code` is one of `fuel`,
`unpaved`, `ferry`, `seasonal`:

```json
{
  "name": "Skyline Loop",
  "length_miles": 74.8,
  "findings": [
    {"level": "warning", "code": "fuel", "message": "Longest fuel gap 63 mi exceeds the 50 mi range."},
    {"level": "info", "code": "ferry", "message": "Ferry check skipped (no OSM data)."}
  ]
}
```

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
```

## Interactive reference

The service serves live OpenAPI docs at **`/docs`** (Swagger UI) and the schema
at **`/openapi.json`** — every endpoint, parameter, and response code, generated
from the running service.
