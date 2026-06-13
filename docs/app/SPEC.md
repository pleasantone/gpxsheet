# Convoy — Group-Ride Pre-Planning Web App

> **Master specification.** Working codename **Convoy** (provisional — rename
> freely). This is a *new program*, designed from scratch, living in the
> `pleasantone/gpxsheet` repo on branch `claude/group-ride-planner-app` under
> `app/`. It is a **pre-planning** tool — used at a desk before the ride, never
> on the bike in real time.
>
> This document is the entry point. Each major component has its own focused
> spec under `docs/app/components/` (each linked in §5) that a subagent can build
> from in isolation. Read this file first for the shared vision, decisions, data model,
> and glossary; then the component spec for your piece.

---

## 1. What Convoy is

A web app that helps a **motorcycle group-ride leader** turn a planned route
(GPX) plus a roster and schedule into the artifacts they hand out before a ride:
a **rider briefing**, a **leader/sweep packet**, an **enriched GPX**, and a
**shareable plan page** — with the route automatically analyzed for navigation
decisions, fuel, timing, weather, and wildfire.

The predecessor (`gpxsheet`, same repo) is a CLI/library that produces a
solo rider's *glanceable tank-bag sheet*. Convoy is a **superset reframing**:
the route analysis is similar work, but the product is a **web app for the
leader**, centered on the **group** and the **plan**, not a single PDF.

Source design discussions to read for context (not requirements — Convoy
supersedes them, but they capture the domain and the hard-won lessons):
- [`docs/group-rides-design.md`](../group-rides-design.md) — the leader interview that defined the group features and phasing.
- [`docs/product.md`](../product.md) — the original product spec + **"Implementation Status & Engineering Notes" / "Decision Point Engine — as built"** (the lessons to carry forward).
- [`IDEAS.md`](https://github.com/pleasantone/gpxsheet/blob/main/IDEAS.md) — the broader feature brainstorm.
- [`DECISIONS.md`](DECISIONS.md) — the decision log (provenance: chosen options, rejected alternatives, rationale).

### Primary user & job-to-be-done

A leader who plans and runs group rides. Today they hand-build briefings in
email/Word every ride. Convoy replaces that with: **upload the route → fill in
the group/schedule → get every artifact, consistent and correct.**

### Non-goals (hard)

- **Not** a real-time / on-bike navigation app. No live GPS tracking, no
  turn-by-turn voice, nothing that runs while riding.
- **Not** a rally roadbook / tulip-diagram tool.
- **Not** a GPS replacement. The enriched GPX export feeds the rider's *own*
  device; Convoy is the planning surface.

---

## 2. Settled architecture decisions

These were decided with the product owner (a ride leader). Treat as fixed for
v1 unless this doc is updated.

| Area | Decision | Notes |
|---|---|---|
| **Analysis engine** | **Rewritten from scratch in Python** | Do *not* import the old `gpxsheet` package. Carry forward its *lessons* (§6, and `product.md` "as built"), not its code. |
| **Backend** | **Python 3.12+ / FastAPI**, analysis engine in-process | Async job model for slow OSM/routing/live work. |
| **Frontend** | **React 19 + TypeScript + Vite + Tailwind**, as an installable **PWA** | Offline-cache the opened plan + map tiles for the staging lot. |
| **Primary visual** | **Interactive MapLibre GL map** | Route line + numbered stop markers + bail-out markers; tap for detail. Schematic strip is a *later* printable artifact, not v1. |
| **Auth** | **Email magic-link** (passwordless), **long-lived persistent sessions** | SMTP in compose (MailHog in dev). Not a bank — sessions persist ~3 months (sliding), persistent cookie, with "sign out everywhere". OAuth later. |
| **Accounts/sharing** | **Leader accounts** create/edit plans; **rider view needs no login**; share links are **public, read-by-default, short (QR-friendly)** | Short base62 code at `/r/{code}`. PII (rider names/phones) is **never** on the public link unless the leader opts in per-field; the **leader/sweep packet (PII, bail-outs) uses a separate long unlisted token or auth** (§7). Co-leads invited to edit. |
| **Data store** | **PostgreSQL + PostGIS** (data + geo queries) + **MinIO/S3** (artifacts) | PostGIS for corridor POIs / nearest-highway / stop scoring. |
| **Geo backbone** | **Self-hosted in compose:** Overpass + Valhalla + tile server. **Overpass & Valhalla map-matching are HARD dependencies** (see Reliability). | Regional `.osm.pbf` extract. No per-call API keys at runtime. |
| **Reliability** | **Two-tier:** geo backbone (Overpass, Valhalla, Postgres, Redis, MinIO) unreachable ⇒ **clean, clear job error** (no degraded output). Live/optional sources (weather, fire, future 511) down ⇒ skip section + info finding. | Overpass is critical — geometry-only decisions are *wrong* on twisty roads, so we **fail loudly** rather than emit garbage. A legitimately *sparse* route still uses geometry-only as a valid *mode* (not a degradation). |
| **Live data (v1)** | **Weather-at-ETA (Open-Meteo) + wildfire (NIFC)** only, graceful + cached | 511/events/air/reviews are later phases. **OSM/Overpass corridor queries are modeled as a (filtered+cached) provider too** (§7), just not a *soft* one. |
| **Printable (v1)** | **Map+table briefing PDF** (+ QR). **Optional roadbook/tulip turn diagrams** per decision point allowed as an output. | Schematic strip artifact is a fast-follow. Tulip diagrams reverse the *gpxsheet* non-goal — fine here (different product), kept optional. |
| **Route input (v1)** | **Upload GPX** (Valhalla map-matched) + **place/mark stops & bail-outs on the map** | No in-app route *drawing* in v1. |
| **Perf / scaling** | **Instrument hot paths** (per-job phase breakdown, `perf.span`); **design pure/chunkable code for future multiprocessing** | Don't build the parallelism now; keep the seams (§7). |

---

## 3. System architecture (containers)

```text
                        ┌─────────────────────────────────────────────┐
                        │                 Browser (PWA)                │
                        │   React + MapLibre · service worker cache    │
                        └───────────────┬─────────────────────────────┘
                                        │ HTTPS (JSON + multipart)
                        ┌───────────────▼─────────────────────────────┐
                        │            api  (FastAPI, Uvicorn)           │
                        │  auth · plans CRUD · jobs · serves PWA + PDF │
                        │  analysis engine (in-process, sync helpers)  │
                        └──┬─────────┬──────────┬───────────┬──────────┘
              enqueue jobs │         │ SQL      │ S3        │ HTTP (internal)
                        ┌──▼──┐   ┌──▼─────┐ ┌──▼────┐  ┌───▼──────────────┐
                        │redis│   │postgres│ │ minio │  │ overpass · valhalla
                        │     │   │+postgis│ │  (S3) │  │ · tileserver-gl   │
                        └──▲──┘   └────────┘ └───────┘  └──────────────────┘
                  consume │
                        ┌─┴───────────────────┐
                        │  worker (same image) │  long jobs: analyze, route-
                        │  analysis + render   │  match, enrich, live, render
                        └──────────────────────┘
```

Containers in `docker-compose.yml`: `api`, `worker`, `postgres` (PostGIS image),
`redis`, `minio`, `overpass`, `valhalla`, `tileserver`, and dev-only `mailhog`.
A `seed`/`init` one-shot loads the regional OSM extract into Overpass + builds
Valhalla tiles. Full deployment spec: [`components/09-deployment.md`](components/09-deployment.md).

### Job model (carried from the old service, simplified)

Slow work (OSM enrichment, Valhalla map-matching, live fetches, PDF render) runs
as **async jobs**: client POSTs → `202` + job id → polls `GET /jobs/{id}` →
fetches result. Redis-backed queue; `worker` consumes. The analysis of a route
is **cached by `(gpx_hash, engine_version)`** so re-opening a plan is instant.
Keep the matplotlib/PDF renderers single-threaded (global state); concurrency
via separate worker processes, not threads.

---

## 4. The domain model (shared vocabulary)

These entities are referenced by every component. Authoritative schema (columns,
types, PostGIS geometry) lives in [`components/04-data-model.md`](components/04-data-model.md);
this is the conceptual model.

- **User** — a leader. Has email, owns Plans, can be invited as co-editor.
- **Route** — an uploaded GPX, **map-matched** to clean road geometry, then
  **analyzed**. Immutable analysis output cached by content hash. A Route is
  reusable across Plans (you ride the same road with different groups).
  - **RoutePoint[]** — the dense matched polyline (lat/lon/ele/cumulative-dist).
  - **DecisionPoint[]** — navigation decisions (turns, forks, road-name changes,
    crossings, roundabouts) with mile, instruction, significance, branches.
  - **Segment[]** — named road stretches between decisions (from OSM names).
  - **Waypoint[]** — named points from the GPX (`<wpt>`/via points).
  - **DayBreak[]** — indices where a multi-`<trk>` route splits into days.
- **Plan** — a Route + a group + a schedule + stop roles + briefing text. The
  thing a leader creates, saves, and shares. Owned by a User; has a **public
  read token** and an **edit membership** (owner + invited co-leads).
  - **group**: `riders:int`, `min_fuel_range_mi:float`
  - **schedule**: `ksu` (kickstands-up datetime + tz), `staging` (name + point)
  - **Stop[]** — a point on/near the route with a **role**: `regroup` |
    `fuel` | `lunch` | `poi`, plus `mandatory` flag, `duration_min` override,
    and notes. Stops are derived (analysis/waypoints) and/or leader-placed.
  - **AltFuel[]** — *emergency-only* alternate fuel options near the route, shown
    **only in the leader packet** (not the rider view). Prefer major brands;
    where fuel is sparse, include any `amenity=fuel`. Used when the planned stop
    is closed/skipped. See group math (§10).
  - **BailOut[]** — leader-marked exit points; each gets a computed
    *fastest-paved-path-to-major-highway* route + miles.
  - **leaders**: `[{role: lead|sweep, name, phone}]`
  - **text**: reusable blurbs (separation protocol, riding rules) — optional.
- **Job** — an async unit of work (analyze / match / enrich / live / render).
- **Artifact** — a generated file in MinIO (briefing PDF, enriched GPX, later
  the schematic strip PNG), keyed to a Plan + kind + params hash.

### The "two routes, two plans" rule

A **Route** (geometry + analysis) is **group-agnostic and cacheable**; a **Plan**
layers the group/schedule/stops on top and is cheap to recompute. This mirrors
the old engine's `analyze_core` (cacheable) vs `derive_products` (per-request)
split — keep expensive OSM/routing work in Route analysis; keep Plan math cheap.

---

## 5. Component map & build order

Each links to a self-contained spec. **Build order** is chosen so each piece has
its dependencies ready; pieces marked ⟂ can be built in parallel.

| # | Component | Spec | Depends on |
|---|---|---|---|
| 0 | Architecture & conventions | this doc + [`components/00-conventions.md`](components/00-conventions.md) | — |
| 1 | **Geo infra** (Overpass, Valhalla, tiles, compose seed) | [`02-geo-infra.md`](components/02-geo-infra.md) | 0 |
| 2 | **Analysis engine** (match → decisions → segments → fuel → timing) | [`01-analysis-engine.md`](components/01-analysis-engine.md) | 1 |
| 3 | **Data model & migrations** (Postgres/PostGIS schema) ⟂ | [`04-data-model.md`](components/04-data-model.md) | 0 |
| 4 | **Auth** (magic-link, sessions) ⟂ | [`05-auth.md`](components/05-auth.md) | 3 |
| 5 | **Backend API** (FastAPI: routes, plans, jobs, sharing) | [`03-backend-api.md`](components/03-backend-api.md) | 2,3,4 |
| 6 | **Group math** (fuel-vs-min-range, group timing, bail-outs) | [`10-group-math.md`](components/10-group-math.md) | 2 |
| 7 | **Live data** (weather + wildfire providers) ⟂ | [`08-live-data.md`](components/08-live-data.md) | 2 |
| 8 | **Frontend PWA** (map, plan editor, share page, offline) | [`06-frontend.md`](components/06-frontend.md) | 5 |
| 9 | **Artifacts** (briefing PDF, enriched GPX, QR, share render) | [`07-artifacts.md`](components/07-artifacts.md) | 5,6 |
| 10 | **Deployment** (compose, seeding, env, prod notes) | [`09-deployment.md`](components/09-deployment.md) | all |
| — | **New-repo bootstrap** (read-only refs, gpxsheet modules to study, pinned choices, spikes) | [`11-new-repo-bootstrap.md`](components/11-new-repo-bootstrap.md) | read first |

> **Building this in a fresh repository?** Read
> [`components/11-new-repo-bootstrap.md`](components/11-new-repo-bootstrap.md)
> first: it covers using gpxsheet + gpxsamples as **read-only references** (which
> modules to study), the cross-repo reference convention, the **pinned** tech
> choices, and the two spikes to retire early.

### v1 acceptance (the demo that proves it)

> A leader signs in with a magic link, uploads a real Bay-Area GPX, watches it
> analyze (decisions + fuel + ETAs on the map), sets group=12 / min-range=120 /
> KSU=Sat 8am / staging=a café, marks two regroups and a lunch stop and one
> bail-out, sees the **mandatory-fuel** marker appear (a 130-mi gap > 120),
> sees a **wildfire** caution near the route and a **weather** line per stop,
> saves, and opens the **public share link on a phone** showing the map +
> briefing + stop table, downloads the **enriched GPX**, and prints the
> **briefing PDF** with a working QR to the GPX.

---

## 6. Lessons carried forward from gpxsheet (do not re-learn the hard way)

The old engine encodes years of tuning against real California/PNW tracks. The
rewrite is free to restructure, but **must not regress on these**:

1. **Decision detection is two-tier; pure geometry floods twisty roads.** A
   recorded Mt-Hamilton-Road track produced **100+ false "turns"** from
   curvature alone. The fix: use OSM **durable road-name changes** + major
   crossings + junction ambiguity (Y/T/fork/roundabout) as the signal, with the
   geometry pass only as a *fallback* (sparse routes / Overpass down) and to
   supply turn *direction*. See `product.md` "Decision Point Engine — as built".
2. **Tuned constants** (sweeps on real tracks): `TURN_ANGLE_THRESHOLD_DEG=35`,
   `MAX_TURN_ARC_M=90`, `CONTINUE_MAX_ANGLE_DEG=25`, `MIN_ROAD_RUN_MILES=0.3`,
   `MERGE_MIN_SEPARATION_MILES=0.2`. Start here; re-tune only with evidence.
3. **Rider waypoints win over OSM.** A named GPX `<wpt>` always renders; an OSM
   fuel station within a buffer of a rider waypoint is suppressed as a duplicate.
4. **Degradation is two-tier (Convoy changes the gpxsheet default).** The geo
   backbone is **critical**: Overpass or Valhalla map-matching *unreachable* ⇒
   **clean, clear error**, *not* a silent geometry-only fallback — because
   geometry-only decisions are wrong on twisty roads (lesson #1), so emitting
   them would be worse than failing. **Optional** sources (weather, fire) down ⇒
   skip the section + an info `Finding`. A *sparse* route (waypoint-only `<rte>`)
   still uses geometry-only as a **valid mode**, distinct from a degradation, and
   distinct from "Overpass returned no features" (valid empty data).
5. **Variable ETAs from OSM `maxspeed`/road class**, a flat user speed overrides.
   Layover/since-gas/sun-times are part of timing. (See `timing.py` concepts.)
6. **Plain `<rte>` and Garmin BaseCamp routes** carry real geometry in
   extensions; map-matching (Valhalla) replaces the old osmnx snapping but the
   *waypoint-lifting* rules (via points → waypoints, shaping points excluded)
   still apply. See `docs/basecamp-routes.md`.
7. **Multi-`<trk>` = multi-day.** Per-day sections, +24h/day, day-relative miles.

A fuller "lessons" appendix is inlined in [`components/01-analysis-engine.md`](components/01-analysis-engine.md).

---

## 7. Cross-cutting conventions

Detailed in [`components/00-conventions.md`](components/00-conventions.md); the essentials:

- **Units:** store/compute SI internally is tempting, but the domain is imperial
  (miles/mph/ft/°F). **Decision:** store canonical **imperial floats**; the API
  returns imperial; the frontend offers a metric *display* toggle (client-side),
  matching the gpxsheet precedent. Datetimes are **ISO 8601 with offset**.
- **IDs & links:** UUIDv7 (sortable) for entities. **Public share links are
  short** (`/r/{code}`, ~7-char base62) so they fit a low-density QR — *not*
  secret, read-by-default, semi-guessable by design ("not a bank"). Because they
  are semi-guessable, the **public share view carries no rider PII** (names,
  phones) unless the leader explicitly opts a field in; the **leader/sweep packet
  (PII, bail-outs, roster) is gated** behind the owner's session **or** a separate
  long unlisted token (`/l/{token}`, 128-bit). Magic-link/session tokens are
  256-bit, hashed at rest.
- **Providers (incl. OSM):** every external data source — weather, fire, **and
  Overpass corridor queries** — goes through one **provider abstraction**:
  *filter → normalize to typed JSON → cache on disk* (record/replay). Raw OSM
  geometry never leaks into the serialized model; only filtered, normalized
  features do. The difference between Overpass and weather is **criticality**, not
  shape: Overpass is a *hard* provider (down ⇒ error), weather/fire are *soft*
  (down ⇒ skip + finding).
- **Sessions:** long-lived & persistent (≈3 months sliding, persistent cookie) — the
  rider/leader shouldn't get logged out between rides. Offer "sign out
  everywhere". (Trade-off accepted; see auth §05 and the challenge notes.)
- **Money/keys:** no runtime third-party keys in v1 (self-hosted geo + keyless
  live). Keep a provider seam for later key-gated sources.
- **Privacy:** a self-hosted box keeps rider PII in its own Postgres; public
  links are short and non-PII; no analytics calls out.
- **Instrumentation:** every job logs **one `perf` line with a phase breakdown**
  (`match=… enrich=… decisions=… fuel=… render=…`), and hot code uses
  `with perf.span("name")` — carry gpxsheet's `gpxsheet.perf` pattern so slow
  areas are findable without a profiler attached.
- **Multiprocessing-ready (not yet built):** keep analysis stages **pure and
  side-effect-free**, and structure work into **independent chunks** (per-day,
  per-corridor-segment, per-provider) that a future `ProcessPoolExecutor` can
  fan out. Don't add the parallelism now; **don't add shared mutable state that
  would block it.** Renderers (matplotlib/global state) stay single-process —
  scale them by worker processes, not threads.
- **Testing:** record/replay fixtures for Overpass/Valhalla/live (cache-only in
  CI, offline + deterministic) — mirror the gpxsheet `conftest` cache harness.
- **Versioning:** an `ENGINE_VERSION` constant invalidates the Route analysis
  cache when detection logic changes.

---

## 8. Open questions (resolve before/while building the affected component)

- **Map tiles**: self-host with `tileserver-gl` + an OpenMapTiles regional
  extract (heavier image, fully offline) vs. a planet-light style. Default:
  tileserver-gl with the same regional extract used for Overpass/Valhalla.
  (Owner to confirm acceptable disk footprint.)
- **Region/extract**: which `.osm.pbf` ships by default (NorCal? California?
  US-West?). Affects all three geo services' disk/RAM. Owner to choose the
  default; doc the swap procedure.
- **Co-lead invite UX**: email-invite vs. shareable edit-link. Defaulting to
  email-invite (ties to accounts); see [`components/05-auth.md`](components/05-auth.md).

### Resolved (owner, 2026-06-13)

- **Bail-out "major highway" = `motorway`, `trunk`, **and `primary`** — `primary`
  counts (often the only paved option in the foothills). Locked in §10
  `MAJOR_HWY_CLASSES`.
- **Major fuel brands = typical North American brands** (Shell/Chevron/Exxon/
  Mobil/BP/Marathon/Valero/Circle K/…); seeded + config-overridable in §10
  `MAJOR_FUEL_BRANDS`.
- **Brand preference applies to ALL fuel stops** (not just emergencies), balanced
  by a **detour tolerance** (~2 mi primary / ~5 mi emergency): a major brand wins
  only when it costs little convenience; sparse areas take anything. See §10 §1a.
- **Auth convenience:** long-lived sliding session so leaders rarely re-login;
  see [`components/05-auth.md`](components/05-auth.md) for the recommended
  mechanism (+ optional passkey for one-tap new-device re-auth).
