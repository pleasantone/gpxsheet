# Day Card tab (SPA) — implementation plan & resume context

> **Status:** planned, not yet built. This branch
> (`claude/day-card-frontend-tab`) is **stacked on** `claude/day-cards-phase-2-y7fkps`
> (PR #63), which adds the Phase 2 `/v1/daycard` backend. Open the frontend PR with
> **base = `claude/day-cards-phase-2-y7fkps`** (not `main`) until #63 merges.
> This doc is the working spec; delete it when the tab lands.

## Context / why
Phase 2 (PR #63) added the `/v1/daycard` endpoint — per-day read-ahead briefings
(stats, sun, weather + crosswind, air/smoke, wildfire, warnings) in `markdown | html
| json`. The SPA never exposed it: it only has **Sheet** and **Table** tabs. This adds
a third **Day card** tab. Backend is unchanged (additive only) — this is purely
frontend + a Playwright test + a doc touch.

**Multi-day is the explicit correctness target.** `/v1/daycard` JSON is an array with
one object per day (`len == route.day_breaks + 1`; a single-day route gives a
1-element array). Each element carries its own `date`/`arrive`/`sun`/`weather`/`air`/
`fire`, so the UI maps the array to per-day cards in order.

## Locked design decisions (from the user)
1. **Render from structured JSON** — one styled card per day (not the HTML blob).
2. **Stacked layout** — all days top-to-bottom (no accordion/day-selector).
3. **Live on by default + toggle**; departure prefilled from the GPX start time.
4. **Full option set** — departure, timezone, units, speed, profile, fuel_range, osm,
   live.

## Backend facts to build against (no changes needed)
- `POST /v1/daycard` → 202 + `JobStatus`; poll `/v1/jobs/{id}`; fetch
  `/v1/jobs/{id}/result`. (`src/gpxsheet/service/app.py`)
- `DayCardParams` (`src/gpxsheet/service/models.py`): `format
  ^(markdown|html|json)$` (default markdown), `departure`, `timezone`, `units`
  `^(imperial|metric)$`, `speed` ≥0, `profile`, `fuel_range`, `osm` (default true),
  `live` (default true).
- JSON shape = `DayCard.to_dict()` (`src/gpxsheet/daycard.py`), array of:
  `index, name, date?, start_mile, end_mile, miles, moving_minutes, arrive?,
  elevation_gain_ft?, elevation_max_ft?, passes[], scenic[], construction[],
  wildlife[], gravel[], no_services[], sun?{sunrise,sunset,golden_*,after_dark,
  dark_from_mile}, weather?{source,as_of,note,samples[{mile,time,temp_f,feels_f,
  wind_mph,gust_mph,wind_dir_deg,crosswind_mph,precip_prob,precip_in,visibility_mi,
  code}]}, air?{max_aqi,max_pm25,smoke,source,as_of}, fire[]{name,dist_mi,status,url},
  elevation_profile?{min_ft,max_ft,gain_ft,source}, warnings[]{level,code,message},
  attributions[]`.
- **JSON is always imperial** (mi/ft/°F/mph); the `units` param only affects the
  md/html render. So the structured cards must **convert units client-side**.
- Nulls: `date`/`sun`/`weather`/`air` are null with no departure or live off/down;
  `weather.note` ("beyond ~16-day horizon") comes with empty `samples`; `fire` is `[]`
  when none/unavailable; `elevation_profile` only set when GPX lacked elevation.

## Approach
Mirror the **Table tab** wiring, but consume JSON like the **Sheet tab**'s analyze
result (`App.tsx` ref-guarded effect → `fetchResultJson`). Two jobs per run:
`format=json` (drives the cards) + `format=markdown` (copy/download parity).

### Files to add (`frontend/src`)
- **`dayCardFormat.ts`** — pure formatters honoring `units`: `fmtDistance` mi/km,
  `fmtElev` ft/m, `fmtTemp` °F/°C, `fmtSpeed` mph/kph, `fmtClock` (HH:MM from an ISO
  string's own offset), `fmtDuration` (from minutes). Mirrors `daycard.py` `_fmt_*`.
- **`components/DayCardOptionsPanel.tsx`** — full options via `controls.tsx`
  (`Row`/`Select`/`NumberInput`/`Checkbox`) + native `datetime-local`, copying
  `TableOptionsPanel.tsx` (incl. its timezone `<select>`): departure, timezone, units,
  speed, profile (Select), fuel_range (NumberInput; null=blank), osm, **live**.
  testids `dc-departure`, etc.
- **`components/DayCardResultPane.tsx`** — maps `DayCardData[]` → one stacked card per
  day. Each: header `Day {index+1}{name ? ": "+name : ""}` + date; stats (distance ·
  moving · arrive); climb; sun (↑/↓ + after-dark); passes/scenic; weather (temp range,
  wind, **crosswind**, precip — or `weather.note`); air (AQI/PM2.5 + smoke); fires;
  gravel/no-services; Warnings (⚠ warning / · info). Omit null/empty sections; if live
  on but a day has no `date`, show "add a departure for sun + weather". Copy/Download
  **markdown** (from the md blob; reuse `TableResultPane` button pattern) + client-side
  **Download JSON** from in-memory data. testids `daycard-output`, `daycard-day-{i}`.
- **`components/DayCardInfo.tsx`** — `SummaryCards` parity: Days (`data.length`),
  Distance (Σ `miles` via `fmtDistance`), Warnings (total). testid `daycard`.
- **`../tests/daycard.spec.ts`** — Playwright mirroring `tests/table.spec.ts`:
  (1) single-day `examples/sample_route.gpx` → `tab-daycard` → `daycard-output` +
  `daycard-day-0` + Distance summary; (2) **multi-day** `gpxsamples/ich-north.gpx` →
  ≥2 `daycard-day-{i}` cards; (3) departure prefilled from a timed GPX. Tests run
  offline → assert day-count/stats/warnings, **not** weather.

### Files to edit (`frontend/src`)
- **`types.ts`** — add `"daycard"` to `Mode`; `DayCardFormat = "json"|"markdown"`;
  `DayCardOptions` + `DEFAULT_DAYCARD_OPTIONS` (departure null, timezone null, units
  "imperial", speed 0, profile "sport-touring", fuel_range null, osm true, **live
  true**); JSON types `DayCardData` + nested mirroring `to_dict`.
- **`api.ts`** — generalize `fetchResultJson<T = AnalyzeResult>(...)`; add
  `submitDaycard(file, opts, format)` mirroring `submitTable` (stringify fields;
  only-if-present for departure/timezone/fuel_range).
- **`App.tsx`** — `ReadyState`: add `daycardJobId` (json) + `daycardMdJobId` (md) +
  `daycardResult: DayCardData[] | null`. Add `daycardOpts` state; `runDaycard` (mirror
  `runTable`, submit json + markdown); ref-guarded effect calling
  `fetchResultJson<DayCardData[]>` (mirror analyze effect at App.tsx:71–78) +
  `useJobPoll(daycardMdJobId, true)`+`useBlobText` for md. Wire `switchMode`/
  `handleFile` (reset + auto-run + departure prefill via existing `gpxStartLocal`).
  `ModeTabs`: add `{ value: "daycard", label: "Day card" }` (testid `tab-daycard`).
  Add `daycardGenerating` branch; conditional render of `DayCardInfo` /
  `DayCardResultPane` / `DayCardOptionsPanel`.

### Reuse (don't reinvent)
`controls.tsx`; `TableOptionsPanel.tsx` (timezone select + `set<K>` pattern);
`TableResultPane.tsx` (copy/download buttons); `SummaryCards.tsx`; `useJobPoll.ts`;
`useBlobText` (App.tsx:411); analyze-JSON effect (App.tsx:71–78); `gpxStartLocal`
departure prefill.

### Docs
- `CLAUDE.md`: update the SPA line to mention the **Day card** tab (alongside
  Sheet/Table).

## Related backend TODO (separate from this tab — add to `TODO.md`)
Day-card already emits `json|html|markdown`; **the table API is `html|markdown` only**
(`TableParams.format = ^(html|markdown)$`, `service.render._table_result`,
`routetable`). For parity (and so a future SPA could render a structured table like
these cards), give `/v1/table` a `json` format: extend the pattern + emit a structured
table payload. Add this as a `TODO.md` item when implementing.

## Verification
- `cd frontend && npm run build` (tsc -b + vite) and `npm run lint` — clean.
- `make frontend` (build into `service/static/`).
- Manual: `make dev-api` + `make dev-ui`; drop `gpxsamples/ich-north.gpx`
  (multi-`<trk>`) → **Day card** tab → one card per day, departure prefilled, toggling
  live/units re-renders; drop `examples/sample_route.gpx` → single card.
- E2E: `cd frontend && npx playwright test daycard.spec.ts` (needs
  `git submodule update --init` for `gpxsamples/`). `table.spec.ts`/`smoke.spec.ts`
  still pass.
- Backend untouched → `python3 -m pytest -q` still green; `ruff`/`mypy` clean.

## Out of scope
No backend changes (the table-json item above is a separate TODO). No accordion/day
selector. No live recording.
