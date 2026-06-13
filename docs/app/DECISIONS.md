# Convoy — Decision Log (provenance)

Chronological record of the owner's design decisions for Convoy, with the
**rejected alternatives** and one-line rationale — the "why we didn't do X" that
the conclusion-only specs don't preserve. Owner = a motorcycle group-ride leader.
Captured 2026-06-13 (session that designed Convoy on branch
`claude/group-ride-planner-app`). Conclusions are baked into
[`SPEC.md`](SPEC.md) + components; this is the audit trail.

## Origin

Convoy grew out of two interviews on top of the `gpxsheet` product:
- **Group-ride feature interview** → [`../group-rides-design.md`](../group-rides-design.md)
  (the group model, artifacts, freshness, stop vetting, and the phasing).
- **New-app architecture interview** → this app (a web app reframing).

The reframe: gpxsheet answers a *solo rider's glance*; Convoy answers a *leader's
pre-planning*. Same route analysis, different product.

## Architecture decisions (round 1–2)

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Analysis engine | **Rewrite fresh in Python** | Reuse `gpxsheet` package; hybrid | Clean slate; gpxsheet is being retired anyway. Carry *lessons* not code. |
| Backend | **FastAPI, engine in-process** | TS/Node + Python svc; Go + sidecar | One language; reuse the proven async-job pattern. |
| Accounts/sharing | **Leader accounts + public rider links** | Tokenized no-accounts; clubs/orgs | Matches "co-leads edit, riders just receive"; clubs were heavier than needed. |
| Primary visual | **Interactive MapLibre map** + strip as later artifact | Strip is the star; map+strip co-equal | Mobile web wants a slippy map; the schematic strip is a fast-follow. |
| Frontend | **React + TS PWA, offline-cached** | SSR (Next/Svelte); plain SPA | Team stack + the staging-lot-no-signal need → PWA offline. |
| Data | **Postgres + PostGIS + MinIO** | SQLite + disk; Postgres no-PostGIS | PostGIS for corridor/nearest-highway/stop-scoring geo queries. |
| Auth | **Email magic-link** | OAuth-only; email+password | Easiest self-host (just SMTP), no password storage. |
| Geo backbone | **Self-host Overpass + Valhalla + tiles** | External APIs+keys; hybrid | Independence, no runtime keys/limits; gpxsheet already self-hosts Overpass. |

## Scope decisions (round 3)

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| v1 scope | **Full core loop** (analyze → plan → share) | Thin analyze-only; core + freshness | Prove the whole leader workflow; defer freshness/stop-intel. |
| Live v1 | **Weather + wildfire (keyless)** | Defer all; all conditions | Highest value + proven keyless (Open-Meteo/NIFC); 511/reviews are key-gated/harder. |
| Printable v1 | **Map+table briefing PDF** | Schematic strip day-one; both | The hand-out is map+table; strip is a fast-follow. |
| Route input | **Upload + place stops on map** | Upload-only; full in-app builder | Marking a regroup needs map interaction; route-drawing is a big later feature. |

## Refinement decisions (round 4 — with challenges)

| Topic | Decision | Note / what I challenged |
|---|---|---|
| Overpass availability | **Hard dependency → clean error** (not geometry-only degrade) | Owner's call; I agreed strongly (geometry-only is *wrong* on twisty roads). I split out 3 non-errors: sparse route (valid mode), empty Overpass (valid data), Valhalla can't-match (raw-polyline fallback). |
| Tulip diagrams | **Allowed** (optional output) | Reverses the gpxsheet non-goal; fine for a different product, kept optional. |
| Share links | **Public, read-default, short (QR-friendly)** | I *challenged*: short codes are semi-guessable + leader packet has PII → split into public **`/r/{code}`** (no PII) vs long unlisted **`/l/{token}`** (roster/phones/bail-outs). |
| Sessions | **Long persistent, 3-month sliding** | "Not a bank." I noted the kiosk-device downside → added sign-out-everywhere + per-session review; passkey as an optional later one-tap path. |
| Alternate fuel | **Emergency alternates, leader-only** | Prefer major brands; sparse → take anything. |
| OSM fuel quality | **Cluster + dedupe + confidence** | OSM mis-/double-tags stations; clean it in the provider, not downstream. |
| OSM as data | **Treat as a (filtered+cached) provider** | Same shape as weather/fire; differs only by *criticality* (hard vs soft). |
| Perf | **Instrument hot paths** (per-job phase line + spans) | Carry gpxsheet's `perf` pattern. |
| Multiprocessing | **Design pure/chunkable; don't build yet** | Keep seams (per-day/segment/provider); no shared mutable state. |

## Fuel-brand + bail-out + auth (round 5)

| Topic | Decision | Note |
|---|---|---|
| Major brands | **Typical North American set** (config-overridable) | Seeded list in [`10-group-math.md`](components/10-group-math.md). |
| Brand scope | **All fuel stops** (not just emergency), **balanced by detour tolerance** | My proposed balance: brand-aware fuel *score*; a major brand wins only within ~2 mi extra detour (primary) / ~5 mi (emergency); sparse → take anything. |
| Bail-out target | **`primary` counts** (with motorway/trunk) | Often the only paved option in the foothills. |
| Auth convenience | **3-month sliding session** (riders never log in); **passkey later** | The "don't log in all the time" answer. |

## Still open (non-blocking — see SPEC §8)

- Default OSM region/extract + tile self-host footprint.
- Co-lead invite UX (email-invite vs edit-link) — defaulting to email-invite.

## The two real spikes (see component 11)

1. **Static map image for the PDF** (tileserver-gl static endpoint; fallback
   headless-MapLibre).
2. **Valhalla map-matching quality** on twisty recorded tracks.
Plus the crown-jewel risk: **decision-detection parity** with gpxsheet,
validated on gpxsamples.
