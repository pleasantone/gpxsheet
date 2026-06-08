# Changelog

## 0.1.0 (unreleased)

First packaged release. Phase 1 milestones 1–4 complete.

- **Route analysis engine** — GPX loading (track/route/waypoint), geometry
  cleanup (RDP), decision-point detection, reassurance markers, fuel analysis,
  segmentation, and the `analyze` text output.
- **OSM enrichment** (optional `osm` extra) — decisions from durable road-name
  changes, named segments, and fuel discovery; sparse routes skip it and long
  routes are queried in chunks. Degrades to geometry-only when unavailable.
- **Schematic map strip** (`strip`) — stylized (default) or faithful turns,
  collision-placed labels with dashed leaders, road ribbon.
- **Tank-bag PDF** (`generate`) — route-aware pagination, landscape (one strip
  per page) and portrait (stacked roadbook lanes) layouts, cue-free header with
  page mileage, progress bar. Portrait + OSM are the CLI defaults.
- Packaged for `pip install gpxsheet` (core) / `gpxsheet[osm]` (enrichment);
  PEP 561 typed.
