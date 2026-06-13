# 04 — Data Model & Migrations (Postgres + PostGIS)

Authoritative schema. SQLAlchemy 2.x async ORM + Alembic migrations. PostGIS for
geometry + spatial queries. Parent: [`../SPEC.md`](../SPEC.md) §4. Can be built
in parallel with the engine.

## Conventions

- PKs: `uuid` (UUIDv7, app-generated). `created_at`/`updated_at` tz-aware UTC.
- Geometry: `geography(Point,4326)` for points, `geography(LineString,4326)` for
  the route line; GiST indexes. Miles stored as `double precision` (imperial).
- Soft-delete plans (`deleted_at`) so a shared link can be revoked without losing
  history. Cascade route-analysis rows on route delete.

## Tables

### `users`
`id, email (citext unique), display_name, created_at, last_login_at`. No
password (magic-link). See [`05-auth.md`](05-auth.md) for sessions/tokens.

### `routes`  (the cacheable analysis — group-agnostic)
```
id, owner_id→users,
name, gpx_sha256 (unique per owner), engine_version,
length_mi, day_breaks jsonb, day_names jsonb,
line geography(LineString,4326),          -- matched polyline (simplified)
bbox geometry(Polygon,4326),              -- for tile prefetch
analysis jsonb,                           -- full Route payload (points may be
                                          --   offloaded to MinIO if large)
created_at
UNIQUE (gpx_sha256, engine_version)        -- cache key
```
Large `points[]` (dense polyline) may live in MinIO (`routes/{id}/points.json`)
with only a reference in the row; decision_points/segments/fuel stay in `jsonb`
for queryability. `analysis` mirrors the Route dataclass (01).

### `plans`
```
id, owner_id→users, route_id→routes, title,
group jsonb,          -- {riders:int, min_fuel_range_mi:float}
schedule jsonb,       -- {ksu: iso, timezone: iana, staging:{name, point}}
leaders jsonb,        -- [{role, name, phone}]
text jsonb,           -- {separation, rules, notes}
share_token (unique), share_enabled bool,
created_at, updated_at, deleted_at
```

### `stops`  (plan-scoped; on/near the route)
```
id, plan_id→plans, source enum(derived|placed),
role enum(regroup|fuel|lunch|poi),
name, mile double, point geography(Point,4326),
mandatory bool, duration_min int null,    -- null => role default (lunch=60)
notes text, sort_order int
```

### `bailouts`  (plan-scoped; leader-marked exits)
```
id, plan_id→plans, name, point geography(Point,4326), mile double,
route_geom geography(LineString,4326) null,  -- computed paved path
exit_miles double null, exit_roads jsonb null,  -- names traversed
target_point geography(Point,4326) null         -- the major-highway node
```

### `plan_members`  (co-lead editing)
`plan_id→plans, user_id→users, role enum(owner|editor), invited_at, accepted_at`.

### `jobs`
`id, kind enum(analyze|match|enrich|live|render|bailout), status enum(queued|
running|done|error), plan_id null, route_id null, params_hash, result_ref,
error, created_at, finished_at`. Idempotency: `UNIQUE(kind, params_hash)`.

### `artifacts`
`id, plan_id→plans, kind enum(briefing_pdf|gpx_garmin|gpx_plain|strip_png),
params_hash, object_key (MinIO), content_type, bytes, created_at`.
`UNIQUE(plan_id, kind, params_hash)`.

### `live_cache`  (optional; or reuse the file cache)
`provider, key, fetched_at, payload jsonb, ttl_s`. For weather/fire responses.

### `magic_links`, `sessions`
See [`05-auth.md`](05-auth.md).

## Key spatial queries (why PostGIS)

- **Corridor POIs** (if not via Overpass): `ST_DWithin(poi.geog, route.line,
  buffer_m)`.
- **Nearest major highway** for a bail-out target:
  `ORDER BY ST_Distance(node.geog, :exit) LIMIT 1` on a seeded `highways` table
  (class motorway/trunk/primary).
- **Stop snapping**: project a placed point onto the route line
  (`ST_LineLocatePoint`) to get its mile.
- **Plan bbox** for the PWA tile prefetch.

## Derived vs stored

- `routes.analysis` is **derived + cached** (recomputable from GPX + engine).
- `plans.*`, `stops`, `bailouts`, `leaders`, `text` are **authored** (the leader's
  data) — back these up; they're the irreplaceable part.
- Group-math outputs (mandatory-fuel flags, group ETAs, after-dark) are
  **recomputed on read** from `plan + route.analysis` (cheap) — do **not** persist
  (mirrors gpxsheet `derive_products`). Cache in Redis if needed.

## Acceptance criteria

- Alembic migrations create the schema clean; `down` reverses.
- A plan + its route + stops + bailouts round-trips through the API.
- PostGIS nearest-highway and line-locate queries return correct miles on a
  fixture route.
- Deleting/soft-deleting a plan revokes the share link (404) without touching the
  shared Route.
