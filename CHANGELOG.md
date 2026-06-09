# Changelog

All notable changes are documented here. From the next release onward this file
is maintained automatically by [release-please](https://github.com/googleapis/release-please)
from [Conventional Commits](https://www.conventionalcommits.org/).

## 0.1.0 (unreleased)

First packaged release. Phase 1 milestones 1–4 complete.

### Features

* **analysis:** route analysis engine — GPX loading (track/route/waypoint),
  geometry cleanup (RDP), decision-point detection, reassurance markers, fuel
  analysis, segmentation, and the `analyze` text output
* **osm:** optional OpenStreetMap enrichment (`osm` extra) — decisions from
  durable road-name changes, named segments, and fuel discovery; sparse routes
  skip it and long routes are queried in chunks; degrades to geometry-only when
  unavailable
* **strip:** schematic map strip (`strip`) — stylized (default) or faithful
  turns, collision-placed labels with dashed leaders, road ribbon
* **pdf:** tank-bag PDF (`generate`) — route-aware pagination, landscape
  (one strip per page) and portrait (stacked roadbook lanes) layouts, cue-free
  header with page mileage, progress bar; portrait + OSM are the CLI defaults

### Build System

* package for `pip install gpxsheet` (core) / `gpxsheet[osm]` (enrichment);
  PEP 561 typed

### Chores

* license under the GNU Affero General Public License v3.0 or later
  (AGPL-3.0-or-later)
