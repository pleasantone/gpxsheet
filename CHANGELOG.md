# Changelog

All notable changes are documented here. From the next release onward this file
is maintained automatically by [release-please](https://github.com/googleapis/release-please)
from [Conventional Commits](https://www.conventionalcommits.org/).

## [0.1.1](https://github.com/pleasantone/gpxsheet/compare/v0.1.0...v0.1.1) (2026-06-09)


### Features

* **service:** security hardening + audit findings ([37e8f1e](https://github.com/pleasantone/gpxsheet/commit/37e8f1edc2e7365a30472f815e5558222b1966a1))


### Documentation

* drop milestone references from comments, README, and CLAUDE.md ([4a76e0e](https://github.com/pleasantone/gpxsheet/commit/4a76e0e003e792a89a4199c6a4248eafdf856286))
* expand CLAUDE.md test-data section with sample GPX breakdown ([bc40eab](https://github.com/pleasantone/gpxsheet/commit/bc40eabeb9cf5dd39ed3b107ac20fd5975d471b7))
* log Phase 2 TODOs (security audit, magic numbers, A4, preview, front end) ([f47cdcd](https://github.com/pleasantone/gpxsheet/commit/f47cdcd9363fa70cc95d724813f6195293b93502))
* move personal/workflow notes out of CLAUDE.md ([65b8ef5](https://github.com/pleasantone/gpxsheet/commit/65b8ef51cb5ca96632e1ef378d1fc61b80250fd0))
* queue nav-detail TODOs (roads-not-taken, roundabout exits) ([d231ec6](https://github.com/pleasantone/gpxsheet/commit/d231ec6b06924f9e9785817e68ceb794bdae3420))
* TODO to make portrait + OSM the default modes ([144c6d6](https://github.com/pleasantone/gpxsheet/commit/144c6d68e88dabccf2fcf1246fbe567fd1d151ad))


### Build System

* use httpx2 for the Starlette TestClient ([45d8e55](https://github.com/pleasantone/gpxsheet/commit/45d8e553b9bbd283e0fb2c9e116159d71df2cea9))

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
