# Changelog

All notable changes are documented here. From the next release onward this file
is maintained automatically by [release-please](https://github.com/googleapis/release-please)
from [Conventional Commits](https://www.conventionalcommits.org/).

## [1.0.0](https://github.com/pleasantone/gpxsheet/compare/v0.3.0...v1.0.0) (2026-06-11)


### Features

* add full-stack dev workflow (Redis + MinIO in Docker, Python on host) ([b285376](https://github.com/pleasantone/gpxsheet/commit/b285376b33cef1a99ff3ce9f23f94a8f1131fe92))
* add GPXtable route tables alongside map sheets ([208b93b](https://github.com/pleasantone/gpxsheet/commit/208b93b54f70eadc949e32bd5bc267918e56ff2b))
* add Python 3.14 support and promote it to default ([852630c](https://github.com/pleasantone/gpxsheet/commit/852630c7c4cd9cca9f80e49ab7200e42e74ab2c0))
* add Python 3.14 support and promote it to default ([7263199](https://github.com/pleasantone/gpxsheet/commit/726319946313c0334609c423039bf619c5180ac8))
* add React+Vite web UI bundled with FastAPI service ([c14c44b](https://github.com/pleasantone/gpxsheet/commit/c14c44b8e07c8a15099a6487895415be97e864e3))
* **deploy:** Hugging Face Space deployment (build-from-source) ([050c0e2](https://github.com/pleasantone/gpxsheet/commit/050c0e2afb5557ab5cd35d4f7622f745f9afd2f6))
* **deploy:** Hugging Face Space deployment (build-from-source) ([c25c8f2](https://github.com/pleasantone/gpxsheet/commit/c25c8f23e5e299df89be5d4747305cc1a8fa4167))
* **deploy:** use HF Trusted Publishing (OIDC), drop HF_TOKEN ([232eceb](https://github.com/pleasantone/gpxsheet/commit/232eceb59268fac3cddb2aacf0dc21651bd558ed))
* **frontend:** add landing-page guide with example output ([ad3662b](https://github.com/pleasantone/gpxsheet/commit/ad3662b2ab3b23dd6969e46faa1adef52cfd79a9))
* **frontend:** brand the SPA header and favicon with the route glyph ([7ab207c](https://github.com/pleasantone/gpxsheet/commit/7ab207cf1ea8d8787ab682e8db109a5944680c00))
* **frontend:** brand the SPA header and favicon with the route glyph ([49ca719](https://github.com/pleasantone/gpxsheet/commit/49ca7192eb53cbbf84b6ce0c0dddabab33cb779e))
* **frontend:** make the SPA an installable home-screen web app ([df38f7f](https://github.com/pleasantone/gpxsheet/commit/df38f7fcbe547a391c95791f795f915af8627beb))
* **frontend:** make the SPA an installable home-screen web app ([d79e81a](https://github.com/pleasantone/gpxsheet/commit/d79e81ae33ffa45acc88a381c23f255d03c86827))
* **service:** fail loudly when the OSM cache dir isn't writable ([e3294f2](https://github.com/pleasantone/gpxsheet/commit/e3294f2156514e598fbba17927f7633e0c46c670))
* **service:** fail loudly when the OSM cache dir isn't writable ([012ab77](https://github.com/pleasantone/gpxsheet/commit/012ab77cd672c56b3790f915b9e4798ff9d65bbc))
* **service:** sign first-party SPA token instead of trusting headers ([46e12bd](https://github.com/pleasantone/gpxsheet/commit/46e12bdf18ad4032e637287f83c695139d27e6ea))
* **service:** sign first-party SPA token instead of trusting headers ([0eac92d](https://github.com/pleasantone/gpxsheet/commit/0eac92df9a04edb6f7ef4118e89c39efb41d45cc))
* **service:** trust first-party same-origin SPA, key for everyone else ([0bd6e6f](https://github.com/pleasantone/gpxsheet/commit/0bd6e6f627fb3fbf14e5454910df311ef0fb4ef4))
* **service:** trust first-party same-origin SPA, key for everyone else ([dcf9f2f](https://github.com/pleasantone/gpxsheet/commit/dcf9f2f139727a157b7923a1819226bf1c46a65a))


### Bug Fixes

* build frontend before packaging so PyPI wheel includes SPA assets ([e7bb572](https://github.com/pleasantone/gpxsheet/commit/e7bb572934994c14919c597eb7002e9749683a6f))
* **ci:** stop the e2e smoke flake by disabling OSM in the smoke run ([cb0ef87](https://github.com/pleasantone/gpxsheet/commit/cb0ef874a9e46585b2114b63224134021b7098c3))
* **ci:** stop the e2e smoke flake by disabling OSM in the smoke run ([bd0aff1](https://github.com/pleasantone/gpxsheet/commit/bd0aff142f342a0860c576186f303d492107ea11))
* **deploy:** upload only build inputs to the HF Space ([3f12815](https://github.com/pleasantone/gpxsheet/commit/3f128151e165bc0af75597cba26bb3d819e84ab1))
* **deploy:** upload only build inputs to the Space, not the whole repo ([4058329](https://github.com/pleasantone/gpxsheet/commit/40583295f977c8efadb910890890581d26cf03da))
* **deploy:** use a valid HF colorFrom value in Space frontmatter ([2fe9a1a](https://github.com/pleasantone/gpxsheet/commit/2fe9a1a405bd8a2f477b6c6504acc369e7b66c6a))
* **deploy:** valid HF Space colorFrom value ([bf6d247](https://github.com/pleasantone/gpxsheet/commit/bf6d24709e79eb3b0a5ed2b0c5474f2e5cf63e38))
* **enrich:** make osmnx cache dir configurable so containers can enrich ([6d1dcd9](https://github.com/pleasantone/gpxsheet/commit/6d1dcd9bbfba31a636c1064ca47cf3c74de1828e))
* **enrich:** make osmnx cache dir configurable so containers can enrich ([0186eab](https://github.com/pleasantone/gpxsheet/commit/0186eabf2524c465bdad8bd9ee2e01582c0e6dab))
* fire analyze and preview jobs independently instead of Promise.all ([5b38c21](https://github.com/pleasantone/gpxsheet/commit/5b38c213716e239d99c2011a64092e3a93538565))
* **frontend:** add download icon to table-mode download buttons ([d2a95b1](https://github.com/pleasantone/gpxsheet/commit/d2a95b1f09c1a08574f97f9c456b06b7c8c5144f))
* **service:** allow configured frame-ancestors so the HF iframe can embed ([f320b31](https://github.com/pleasantone/gpxsheet/commit/f320b31940e6ac65478928fea7fbcc842fbc106c))
* **service:** allow configured frame-ancestors so the HF iframe can embed ([e69a927](https://github.com/pleasantone/gpxsheet/commit/e69a92766f4b896302d21884d856683743ae78fe))
* **service:** deliver first-party token via meta tag, not inline script ([bcd960d](https://github.com/pleasantone/gpxsheet/commit/bcd960d04675dcc29d8fc191bc774b2947bd86c5))
* use 127.0.0.1 in Vite proxy target instead of localhost ([e4bd11d](https://github.com/pleasantone/gpxsheet/commit/e4bd11dcfd8b4afccbfb55e38cdff29fc7e31402))


### Refactoring

* **frontend:** portability, result-url auth, ESLint, and dedup ([912c5a3](https://github.com/pleasantone/gpxsheet/commit/912c5a3097bc8b5f1438705ec968cd6854dd5199))


### Documentation

* document dev modes; bind infra ports to loopback ([8ce7659](https://github.com/pleasantone/gpxsheet/commit/8ce76597a1ad161debd209658223c9daab092636))
* how to enable OSM/Overpass in web sessions ([f0afa62](https://github.com/pleasantone/gpxsheet/commit/f0afa623218e4d905c388488c7e07b5672987b95))


### Chores

* release 1.0.0 ([763baad](https://github.com/pleasantone/gpxsheet/commit/763baadc4160fffe6599ab4a0cd1c0be4edd93e5))

## [0.3.0](https://github.com/pleasantone/gpxsheet/compare/v0.2.1...v0.3.0) (2026-06-11)


### ⚠ BREAKING CHANGES

* **stage3:** public-API consistency pass (v0.3.0)

### Features

* **stage3:** public-API consistency pass (v0.3.0) ([5649dac](https://github.com/pleasantone/gpxsheet/commit/5649dac0db0f69a16b9eb25040bb57b803725a11))
* waypoint label improvements, defaults cleanup, CLAUDE.md update ([#21](https://github.com/pleasantone/gpxsheet/issues/21)) ([a0317fc](https://github.com/pleasantone/gpxsheet/commit/a0317fc68e2ed59d12776943bd686d25b74b8262))


### Bug Fixes

* **stage-5:** web-service hardening ([035678e](https://github.com/pleasantone/gpxsheet/commit/035678e0e8e04bf8c7ed846b411d6bdfaed76729))


### Refactoring

* remove dead off variable from slice_route; fix stale comments ([0d21fc3](https://github.com/pleasantone/gpxsheet/commit/0d21fc3aa57a677730b2a7d2442b5ef20567bd1f))
* **stage-4:** dead code & type clarity cleanup ([f708c12](https://github.com/pleasantone/gpxsheet/commit/f708c12d9a90c03167cd3ce40272bb3a4aa593df))
* **stage-6:** decompose long functions, log broad excepts, promote scoring ([94485ce](https://github.com/pleasantone/gpxsheet/commit/94485cec9c8855bd14cd803734442915896af32d))
* **stage1:** centralize constants and shared geometry ([fb45470](https://github.com/pleasantone/gpxsheet/commit/fb45470e22274e7f46fb1d2fdbf35cf5fa10c66f))
* **stage2:** unify pagination engine in paginate.py ([03bfec9](https://github.com/pleasantone/gpxsheet/commit/03bfec9397ceea66e3d65e046605254960e80904))
* unify CLI layouts, remove rebase, add portrait progress bar ([08b8d72](https://github.com/pleasantone/gpxsheet/commit/08b8d72b4142c616a7b18690b18a383cf1fde03c))


### Documentation

* add show_branches to web-api parameter table ([6e1b509](https://github.com/pleasantone/gpxsheet/commit/6e1b50913a937605029d45624c5c58b3eada35e7))
* note remote/web sandbox setup in CLAUDE.md ([ee6a2fe](https://github.com/pleasantone/gpxsheet/commit/ee6a2fe528ef00a325d4bb31a6b226c765baef75))
* trim CLAUDE.md to load-bearing non-obvious facts ([0f77895](https://github.com/pleasantone/gpxsheet/commit/0f77895aad385d64009c4ed1bcc8aa47defe2f6e))

## [0.2.1](https://github.com/pleasantone/gpxsheet/compare/v0.2.0...v0.2.1) (2026-06-10)


### Features

* **analysis:** drop off-route waypoints past a cross-track cutoff ([9a2b843](https://github.com/pleasantone/gpxsheet/commit/9a2b843748d78055fe206a3f23acc87b7f49f9f9))
* **analysis:** drop off-route waypoints past a cross-track cutoff ([4cd4a5f](https://github.com/pleasantone/gpxsheet/commit/4cd4a5fe9d96bd7050ed409b33ccb898d22f25b1))
* **render:** reproducible fonts + vendored symbol glyphs ([504a780](https://github.com/pleasantone/gpxsheet/commit/504a780284c9f58e0600a941a011128e1d479298))
* **render:** reproducible fonts + vendored symbol glyphs ([740653e](https://github.com/pleasantone/gpxsheet/commit/740653e3343ff300967781b4ed1e905564b44518))


### Refactoring

* **profiles:** drop unused significance-score constants ([93d4c50](https://github.com/pleasantone/gpxsheet/commit/93d4c50c901d8f55438d17a6eab586e0575a2ba8))
* **strip:** extract label placement into a pure, tested module ([3fd28b2](https://github.com/pleasantone/gpxsheet/commit/3fd28b2eda0535290b8774124c0d379537cf5109))
* **strip:** extract label placement into a pure, tested module ([4c99327](https://github.com/pleasantone/gpxsheet/commit/4c993274c225d1f91a25c4efccb696b6c6ef024c))


### Documentation

* move PRODUCT.md to docs ([add876c](https://github.com/pleasantone/gpxsheet/commit/add876ca76c51440f34ec04bb73c8edcf968ba39))
* **product:** record rendering-backend analysis (matplotlib vs SVG) ([1665c5a](https://github.com/pleasantone/gpxsheet/commit/1665c5a7e6460ab3be576ccc2a8851e99eeb222a))
* sync TODO.md and PRODUCT.md with as-built state ([e62a1dc](https://github.com/pleasantone/gpxsheet/commit/e62a1dc0f02d710befe8fa8184d56f3e4e3b0cfd))
* sync TODO.md and PRODUCT.md with as-built state ([c1c8802](https://github.com/pleasantone/gpxsheet/commit/c1c88025c91b1b42545dcd449782928731c18e47))

## [0.2.0](https://github.com/pleasantone/gpxsheet/compare/v0.1.1...v0.2.0) (2026-06-10)


### ⚠ BREAKING CHANGES

* **api:** gpxsheet.generate_pdf and gpxsheet.generate_strip are removed. Use gpxsheet.render(layout=..., format=...) instead (layout defaults to portrait). gpxsheet.validate now returns a ValidationReport, not None.
* **service:** the web API is reorganized. POST /v1/jobs, the synchronous POST /v1/analyze and POST /v1/preview, and the use_osm/kind request fields are removed. Submit jobs to POST /v1/render, /v1/analyze, or /v1/validate with the GPX and parameters as multipart form fields; poll GET /v1/jobs/{id} and fetch GET /v1/jobs/{id}/result.
* **osm:** the use_osm parameter (library + CLI --osm/--no-osm + service GenerateParams.use_osm) and the GPXSHEET_ALLOW_OSM service setting are removed; OSM enrichment always runs. The [osm] install extra is removed (osmnx is now a core dependency). The preview --dpi flag is removed.

### Features

* **api:** unify the library API into render/analyze/validate ([31ece70](https://github.com/pleasantone/gpxsheet/commit/31ece7073d789e99118dd60a05f35a24966f085c))
* display named GPX waypoints on the strip ([aa6d305](https://github.com/pleasantone/gpxsheet/commit/aa6d3053f6c0f71c78409bfb25d3355dc95b8cd9))
* **enrich:** down-weight straight "Continue onto" residential changes ([58f7988](https://github.com/pleasantone/gpxsheet/commit/58f7988857c0fee8fea337a40ec8cccec66e633d))
* **enrich:** promote nameless high-degree forks to decisions ([be22f22](https://github.com/pleasantone/gpxsheet/commit/be22f222fd78fbb7a51fe059d059676c711df508))
* **enrich:** stabilize durable-run detection near MIN_ROAD_RUN_MILES ([391b008](https://github.com/pleasantone/gpxsheet/commit/391b008614a97657b840772193728d6e38d28e4f))
* **layout:** nudge START/END-coincident markers off the endpoint ([e8acca8](https://github.com/pleasantone/gpxsheet/commit/e8acca8ccd6ffbdf2ffecbe366de1ce37417dc1d))
* **layout:** relax stylized turn accumulation to curb ribbon curl ([b1675e8](https://github.com/pleasantone/gpxsheet/commit/b1675e8cb96536b4aa3970d4cfbd6fb50e4003c4))
* **osm:** make OSM enrichment intrinsic and a core dependency ([a55e834](https://github.com/pleasantone/gpxsheet/commit/a55e8340a67eae8a23a7439883af84a9a422984d))
* record unpaved & ferry spans and render styled ribbon stretches ([36bbac0](https://github.com/pleasantone/gpxsheet/commit/36bbac00a56d2254065b43e8e40fe26a328b4321))
* **render:** auto-fit decisions per lane (decisions_per_lane=0/None) ([8b43eea](https://github.com/pleasantone/gpxsheet/commit/8b43eea48f431913b0ef19e404b15646e0517d6d))
* **render:** auto-fit decisions per lane (decisions_per_lane=0/None) ([c8b9ee9](https://github.com/pleasantone/gpxsheet/commit/c8b9ee95b430224fd1d157725931ed21ddd26ba4))
* **render:** default decisions_per_lane to auto-fit ([8c954cc](https://github.com/pleasantone/gpxsheet/commit/8c954cc151faebcc578a89235b58855b9fa83b19))
* **render:** default decisions_per_lane to auto-fit ([c205554](https://github.com/pleasantone/gpxsheet/commit/c20555450c3490f9f8e28d8ee4fc86043f16dc31))
* **render:** make landscape honor decisions_per_lane ([b0bab60](https://github.com/pleasantone/gpxsheet/commit/b0bab60c3adc2a71136133d23c428cbbd029ba2b))
* **service:** redesign web API around typed async job endpoints ([8df0149](https://github.com/pleasantone/gpxsheet/commit/8df0149dd8a11a2e255a476692c92ee3baf6c08d))
* **strip:** alternate label sides to de-collide dense strips ([0bac099](https://github.com/pleasantone/gpxsheet/commit/0bac099758a072ff75b2c24e0296b81df6c0a578))
* **strip:** make named reassurance (town) labels more prominent ([fedf270](https://github.com/pleasantone/gpxsheet/commit/fedf2705f2ff2e3c620ec858bc1e2869bff18ff2))
* **strip:** symbol glyphs and mileage on fuel/food/ferry markers ([bc148a3](https://github.com/pleasantone/gpxsheet/commit/bc148a354d276898b8a717ccb9764805a6c48609))


### Bug Fixes

* **enrich:** count only outgoing spurs as roundabout exits ([903a96d](https://github.com/pleasantone/gpxsheet/commit/903a96d4b6d3d9f13966dc82d23a09e902a3ce90))
* **enrich:** fall back to drive_service so remote roads still enrich ([a6b8398](https://github.com/pleasantone/gpxsheet/commit/a6b8398737623cc6d486f4cbbc752007696d7d49))
* **enrich:** restrict Continue-onto penalty to unambiguous cul-de-sac suffixes ([8ef0c5e](https://github.com/pleasantone/gpxsheet/commit/8ef0c5e4ae96ca90a2e41df5f123fb53c598c427))
* **enrich:** stop nameless-fork promotion flooding twisty roads ([239c2aa](https://github.com/pleasantone/gpxsheet/commit/239c2aa95d4d135e7aa7e73f1507815568150d73))


### Refactoring

* **render:** name the renderer colors instead of inline hex ([88c4971](https://github.com/pleasantone/gpxsheet/commit/88c49718eed599b36903b42890ecbbea587c0fe3))
* **render:** named colors + landscape honors decisions_per_lane ([452299f](https://github.com/pleasantone/gpxsheet/commit/452299f264a7c22adf56813426bcd914c6733b5d))


### Documentation

* add front-end web API integration guide ([10c8946](https://github.com/pleasantone/gpxsheet/commit/10c8946508acb72c7fc58118b59c285a3dbabbbb))
* **pdf:** drop stale cue-zone wording from pdf docstrings ([0a0eb63](https://github.com/pleasantone/gpxsheet/commit/0a0eb636c5aae518046686157f0c9e391f689e11))
* publish library + web API documentation to ReadTheDocs ([83b5ddd](https://github.com/pleasantone/gpxsheet/commit/83b5ddde1b19284f9d911e9c42b2b7831e841015))
* publish library + web API documentation to ReadTheDocs ([26262ed](https://github.com/pleasantone/gpxsheet/commit/26262edb42006f3044c327400e622b9dad022c0f))
* **todo:** mark OSM robustness + [#7](https://github.com/pleasantone/gpxsheet/issues/7)/[#8](https://github.com/pleasantone/gpxsheet/issues/8)/[#9](https://github.com/pleasantone/gpxsheet/issues/9) validated and fixed ([5fef18d](https://github.com/pleasantone/gpxsheet/commit/5fef18d70255e22ca8a54a4e32f1180a5f32a43b))
* **todo:** note osmnx thin-polygon enrichment fallback ([ca10be7](https://github.com/pleasantone/gpxsheet/commit/ca10be7c25e09fa29ec3369dbd8b8ce18ba9146d))
* **todo:** note waypoint-projection cutoff + name-prefix revisit ([feedd34](https://github.com/pleasantone/gpxsheet/commit/feedd346f3219686658e27563aecd52adfe3ac87))
* **todo:** record shipped polish + remaining ground-truth tuning ([0bd620f](https://github.com/pleasantone/gpxsheet/commit/0bd620f147219f8c50fe229e41b4845dd78fcea1))

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
* **osm:** OpenStreetMap enrichment — decisions from durable road-name changes,
  named segments, and fuel discovery; sparse routes skip it and long routes are
  queried in chunks; degrades to the geometry baseline automatically on sparse
  routes or Overpass failure
* **strip:** schematic map strip (`strip`) — stylized (default) or faithful
  turns, collision-placed labels with dashed leaders, road ribbon
* **pdf:** tank-bag PDF (`generate`) — route-aware pagination, landscape
  (one strip per page) and portrait (stacked roadbook lanes) layouts, cue-free
  header with page mileage, progress bar; portrait is the CLI default orientation

### Build System

* package for `pip install gpxsheet` (OSM enrichment included); PEP 561 typed

### Chores

* license under the GNU Affero General Public License v3.0 or later
  (AGPL-3.0-or-later)
