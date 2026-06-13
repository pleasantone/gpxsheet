# 07 — Artifacts (briefing PDF · enriched GPX · QR · share render)

The hand-out deliverables. Generated server-side as **jobs**, stored in MinIO,
cached by `(plan, kind, params_hash)`. Parent: [`../SPEC.md`](../SPEC.md). Depends
on API (03), group math (10).

## v1 artifacts

### 1. Rider briefing PDF (`briefing_pdf`) — the headline
A clean, printable one-pager (US-Letter + A4) a leader hands out:
- **Header:** ride title, date, **KSU time**, **staging** name/address.
- **Static map snapshot:** the route line + **numbered stop markers** (regroup/
  fuel/lunch) + bail-out markers. Render via a static-map step (MapLibre headless
  / `maplibre-gl-native`, or render server-side from the tile server). Numbered to
  match the table.
- **Stop table:** `# · mile · what (role) · mandatory-fuel? · group ETA`.
- **Conditions block:** per-stop weather (if KSU set) + any fire/closure findings.
- **Briefing text:** separation protocol + group-riding rules (from plan `text`,
  only if provided) + leader/sweep names & phones (if the leader opted to show).
- **QR codes:** one → the **share URL**, one → the **enriched GPX** download.
- **Sources/attribution** footer (OSM/Open-Meteo/NIFC).

Implementation: HTML→PDF (WeasyPrint or Playwright/print) is simplest for a
map+table layout; keep it deterministic and offline. (matplotlib only if the
schematic strip lands later.)

### 2. Leader / sweep packet
The briefing **plus**: the full decision/cue list, the **bail-out section**
(per exit: roads + miles to the major highway), the after-dark note, and the
roster (`leaders` + any rider list). Same renderer, a `variant=leader` flag.

### 3. Enriched GPX export (`gpx_plain`, `gpx_garmin`)
Emit the analyzed route as GPX so every rider's device shows the same stops.
- **`gpx_plain`:** `<trk>` (matched line) + named `<wpt>`s for regroup/fuel/lunch
  /bail-out + `<sym>` hints. Loads in OsmAnd/Calimoto/REVER/Google.
- **`gpx_garmin`:** route with `trp:ViaPoint` + Garmin `<sym>` values (Gas
  Station, Restaurant, Flag) so stops **announce** on a zūmo. This is the mirror
  of gpxsheet's BaseCamp *loader* (`docs/basecamp-routes.md`) — now the *writer*.
- **Per-day split:** for multi-`<trk>` plans, optional one file per day
  (`?day=N` or a zip).

### 4. QR (`qr.png`)
Served at `/v1/share/{token}/qr.png` and embedded in the PDFs. Encodes the share
URL (and a second QR for the GPX). Riders scan at staging to pull route+plan onto
their phone.

## Share render (rider-facing, no auth)

`GET /v1/share/{token}` returns a **view-model** the PWA renders into the same
map + briefing layout (interactive), and `…/briefing.pdf`, `…/route.gpx`,
`…/qr.png` serve the artifacts. The share page is the digital twin of the PDF.

## Jobs & caching

- `POST /v1/plans/{id}/artifacts/{kind}` → `202` job(render) or `200` if cached.
- `params_hash` includes plan `updated_at` + group inputs + engine version, so a
  plan edit invalidates stale artifacts.
- Store in MinIO `artifacts/{plan}/{kind}/{hash}.{ext}`; serve via presigned URL
  or stream through the API.

## Fast-follow (not v1)

- **Schematic tank-bag strip** (the gpxsheet signature): port the strip/pdf
  renderer as a `strip_png`/strip-PDF variant. Carries its own tuned constants
  (`MIN_SEGMENT_LEN=2.6`, stylized angles 10/30/55°). A glanceable alternative
  page to the map.

## Acceptance criteria

- Briefing PDF renders deterministically (offline) with map + numbered stops +
  table matching, working QR codes, and conditions when a KSU is set.
- `gpx_garmin` loads on a zūmo with stops announcing; `gpx_plain` imports in a
  phone app; per-day split produces N files for a multi-day plan.
- Editing the plan (e.g. add a stop) invalidates and regenerates the cached PDF.
- Share artifacts are reachable with only the token (no session).
