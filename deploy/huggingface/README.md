---
title: GPXSheet
emoji: 🏍️
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 8000
pinned: false
license: agpl-3.0
---

# GPXSheet

Convert GPX routes into glanceable, map-centric **motorcycle tank-bag navigation
PDFs** (sport-touring). Drop a `.gpx` file, get a print-ready roadbook.

This Space runs the GPXSheet web service in **simple mode** — a single container,
no external queue or object store. Renders run **off the request path on an
in-process worker thread** (`GPXSHEET_BACKGROUND_RENDER=1`): the upload returns a
job immediately and the client polls for the result, so a slow route (dense urban
OSM enrichment can take a couple of minutes) doesn't hold the HTTP connection open
or trip the Space's request timeout.

- **Source & docs:** https://github.com/pleasantone/gpxsheet
- **API reference:** see `/docs` on this Space.

> This Space is built and deployed automatically from the `main` branch of the
> GitHub repository. Do not edit it directly — changes will be overwritten on the
> next push.
