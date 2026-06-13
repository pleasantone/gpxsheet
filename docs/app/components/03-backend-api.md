# 03 — Backend API (FastAPI)

The REST surface + job orchestration. In-process analysis engine; Redis jobs;
Postgres/MinIO. Parent: [`../SPEC.md`](../SPEC.md). Depends on engine (01), data
model (04), auth (05).

## Shape

- `/v1` base; JSON + multipart upload + binary download.
- Session-cookie auth for owner/editor routes; **public, unauthenticated**
  short `/v1/r/{code}/…` (rider) + long unlisted `/v1/l/{token}/…` (leader) routes.
- Async jobs for slow work (`202`+poll); sync for cheap reads (plan math).
- All list/detail responses are imperial; datetimes ISO-8601-with-offset.
- **Hard-dependency down** (Overpass/Valhalla/db/redis/minio unreachable) → a
  clean `503 {type:"dependency_unavailable", detail:"Overpass not reachable …"}`
  (the failing job carries `error`), **never** a degraded `200`. `/readyz`
  reflects it. Soft sources (weather/fire) down never error — they drop a
  `Finding`. (See conventions §Reliability.)

## Endpoints (v1)

### Auth (see [`05-auth.md`](05-auth.md))
```
POST /v1/auth/magic-link        {email}                 -> 202 (email sent)
GET  /v1/auth/callback?token=…                          -> sets session, 303 → app
POST /v1/auth/logout
GET  /v1/auth/me                                         -> {user} | 401
```

### Routes (analysis; cacheable, group-agnostic)
```
POST /v1/routes        multipart gpx + {osm?}           -> 202 job(analyze) | 200 cached
GET  /v1/jobs/{id}                                      -> {status, result_url?}
GET  /v1/routes/{id}                                    -> Route (analysis JSON)
GET  /v1/routes/{id}/points                             -> dense polyline (maybe 303→MinIO)
GET  /v1/routes                                         -> my routes (reuse across plans)
```

### Plans (authored; owner/editor only)
```
POST /v1/plans         {route_id, title}                -> Plan
GET  /v1/plans                                          -> my plans (+shared-with-me)
GET  /v1/plans/{id}                                     -> Plan (full, with computed group math)
PATCH/v1/plans/{id}    {group?, schedule?, leaders?, text?, title?}
DELETE /v1/plans/{id}                                   -> soft-delete (revokes share)
POST /v1/plans/{id}/share   {enabled}                   -> {share_token, share_url}
POST /v1/plans/{id}/members {email, role}               -> invite co-lead
```

### Stops & bail-outs (plan-scoped)
```
POST   /v1/plans/{id}/stops    {role, point|mile, name?, mandatory?, duration_min?}
PATCH  /v1/plans/{id}/stops/{sid}
DELETE /v1/plans/{id}/stops/{sid}
POST   /v1/plans/{id}/bailouts {name, point}            -> 202 job(bailout) → routed exit
DELETE /v1/plans/{id}/bailouts/{bid}
```
Placing a stop by `point` snaps to the route (PostGIS `ST_LineLocatePoint`) to
fill `mile`. Posting by `mile` interpolates the point.

### Group math (computed, cheap, on read)
Returned **inline** in `GET /v1/plans/{id}` as `plan.computed`:
```
computed: {
  fuel: { mandatory_stops:[mile…], longest_gap_mi, gap_exceeds_range:bool },
  timing: { ksu, per_stop:[{stop_id, arrive, depart, overhead_min}], finish, after_dark:{…} },
  findings: [Finding…],            # fuel/services/dark/weather/fire merged
}
```
See [`10-group-math.md`](10-group-math.md). Recomputed each read (or Redis-cached
by `plan.updated_at`).

### Live conditions
```
POST /v1/plans/{id}/conditions   {departure?}           -> 202 job(live) (weather+fire)
GET  → merged into plan.computed.findings + per-stop weather when ready
```

### Artifacts (see [`07-artifacts.md`](07-artifacts.md))
```
POST /v1/plans/{id}/artifacts/{kind}                    -> 202 job(render) | 200 cached
        kind ∈ briefing_pdf | gpx_garmin | gpx_plain
GET  /v1/plans/{id}/artifacts/{kind}                    -> binary (or 303→MinIO presigned)
```

### Public share — rider tier (no auth, short link)
```
GET /v1/r/{code}                 -> rider view-model (map data, stops, ETAs,
                                    briefing text, conditions, findings) — NO PII
GET /v1/r/{code}/briefing.pdf    -> rider briefing artifact
GET /v1/r/{code}/route.gpx       -> enriched GPX (plain; garmin via ?flavor=)
GET /v1/r/{code}/qr.png          -> QR to /r/{code}
POST /v1/plans/{id}/share {enabled}  -> {code, share_url}  (owner; rotatable)
```
`code` is **short** (~7-char base62) for QR density and is **semi-guessable by
design** — so the rider view-model **must omit rider PII** (names/phones) unless
the leader explicitly opted a field public.

### Leader tier (PII: roster, phones, bail-outs) — gated
```
GET /v1/l/{token}                -> leader view-model (adds roster/phones,
                                    bail-outs, alt-fuel, full cue)
GET /v1/l/{token}/packet.pdf     -> leader/sweep packet
POST /v1/plans/{id}/leader-link {enabled} -> {token}  (owner; long 128-bit, unlisted)
```
Served to the **long unlisted leader token** *or* an owner/editor **session**.
Never to the short public `code`.

## Jobs

- Redis queue; `worker` runs `process_job(kind, params)`. Kinds: `analyze`,
  `match` (part of analyze), `enrich`, `bailout`, `live`, `render`.
- Idempotent by `params_hash` (`UNIQUE(kind, params_hash)`); a duplicate submit
  returns the existing job. Route analysis additionally cached in `routes`.
- Progress/queue position surfaced like gpxsheet (`queue_position`).
- Renderers (PDF) are not thread-safe if they use matplotlib → run in the worker
  process, concurrency 1 per process, scale by processes.

## Authorization matrix

| Route group | Anonymous | Owner | Editor |
|---|---|---|---|
| `/share/*` | ✅ read | ✅ | ✅ |
| `routes` (own) | ❌ | ✅ | ✅ (if on a shared plan's route) |
| `plans` read | ❌ | ✅ | ✅ |
| `plans` write | ❌ | ✅ | ✅ |
| `members`/`delete`/`share` toggle | ❌ | ✅ | ❌ (owner-only) |

## Acceptance criteria

- Upload→analyze→plan→stops→share happy path works end-to-end via TestClient.
- A second identical GPX upload returns the cached Route (no re-analyze).
- `plan.computed` reflects group size / min-range changes **without** a job.
- Share link is read-only, unguessable, and 404s after soft-delete.
- Editor can edit a shared plan but cannot delete it or invite others.
