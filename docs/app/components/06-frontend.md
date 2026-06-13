# 06 — Frontend PWA (React + MapLibre)

Mobile-first, installable PWA. Map-primary. The leader builds the plan here; the
rider opens the share page here. Parent: [`../SPEC.md`](../SPEC.md). Depends on the
API (03).

## Stack

React 19 + TypeScript (strict) + Vite + Tailwind v4 + MapLibre GL JS +
`vite-plugin-pwa` (Workbox). State: lightweight (Zustand or React Query for
server state). Shared API types generated from the backend Pydantic schemas
(OpenAPI → TS) so the contract can't drift.

## Surfaces

### A. Leader app (authenticated)
1. **Sign-in** — enter email → "check your inbox" → magic-link returns to app.
2. **Dashboard** — my routes + my plans + shared-with-me. New plan = upload GPX.
3. **Upload + analyze** — drop GPX → job spinner → map fills with the matched
   route line, **decision markers**, fuel, day breaks. Route stats header
   (distance / decisions / fuel) — *re-fetched on profile change* (a lesson the
   old Sheet tab got wrong: keep the header in sync).
4. **Plan editor** (the core screen) — map on top (mobile) / left (desktop):
   - **Group panel:** riders, min fuel range → **mandatory-fuel markers update
     live** (client-side from `plan.computed`, no job).
   - **Schedule:** KSU datetime + tz (prefilled from GPX start), staging (tap map
     or search).
   - **Stops:** tap the route to add a stop → choose role (regroup/fuel/lunch) →
     it snaps to the line; list is reorderable; per-stop duration override.
   - **Bail-outs:** tap an exit point → job computes the paved exit → draw it +
     show miles/roads.
   - **Conditions:** toggle → weather chips per stop + fire overlay (needs KSU).
   - **Findings rail:** fuel/dark/wind/fire warnings, each linking to its map
     marker.
   - **Briefing text:** separation protocol / rules / notes; visibility toggle for
     leader phones on the public page.
5. **Share & export** — toggle public share → copy link + QR; download briefing
   PDF, leader packet, enriched GPX (plain/garmin, per-day).

### B. Rider share page (public, no auth) — `/r/{token}`
Read-only twin: the same map + numbered stops + stop table + conditions +
briefing text, **plus** big buttons: *Add to phone (GPX)*, *Open in Maps*,
*Briefing PDF*. This is what the QR opens at staging.

## Map (MapLibre)

- Style from the self-hosted `tileserver`. Layers: route line (casing+line),
  decision markers (significance-sized), stop markers (role icons, numbered to
  match the table/PDF), bail-out lines, fire perimeter fill, unpaved/ferry span
  styling. Tap a marker → detail sheet.
- Mobile gestures native; "recenter to route" control; respects reduced-motion.

## Units (client-side toggle)

API is imperial; a metric **display** toggle converts in-browser (miles↔km,
mph↔kph, ft↔m, °F↔°C) — exactly the gpxsheet pattern. Never re-fetches.

## PWA / offline

- Installable (manifest + icons). Service worker (Workbox) caches the app shell,
  the **opened plan's** share view-model + briefing + GPX, and **map tiles for
  the plan bbox** — so a rider who opened the link on wifi still has the map +
  briefing + GPX in the **no-signal staging lot**. Plan data is read-only
  offline; edits require connectivity.
- Cache strategy: app shell = precache; API GETs = stale-while-revalidate; tiles
  = cache-first within the plan bbox, capped.

## Cross-cutting (apply the gpxsheet front-end lessons)

- One **display-model seam** feeds the on-screen views and any client-built text
  (so screen ↔ exports never drift — the table/day-card lesson).
- Keep instant toggles (units, conditions show/hide) **client-side**; only
  inputs that change computed data (group size already comes back in
  `plan.computed`, so it's instant; KSU/speed/osm/live re-run jobs).
- Accurate labels (e.g. "Decisions", not "Turns"); safe download filenames.

## Acceptance criteria (Playwright)

- Upload → map shows route + decisions; header stats correct.
- Set group=12/min=120 → a mandatory-fuel marker appears with **no** network job.
- Add a stop by tapping the route → it snaps + appears in the list + table.
- Toggle metric → distances switch to km instantly (no fetch).
- Share toggle → public `/r/{token}` renders the read-only twin on a mobile
  viewport; GPX + PDF download; QR resolves to the share URL.
- Installable; offline reload of an opened share page still shows map+briefing.
