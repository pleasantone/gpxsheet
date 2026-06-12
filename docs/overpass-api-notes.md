# Overpass API: Analysis for Motorcycle Route Queries

## What Is Overpass API?

The Overpass API is a read-only query interface for OpenStreetMap data. It lets you retrieve nodes, ways, and relations matching spatial and tag-based filters. It is not a tile server or routing engine — it's a data retrieval tool.

---

## Spatial Query Types

### Bounding Box (`bbox`)
The simplest spatial filter — a rectangular lat/lon envelope. Fast and predictable, but returns everything in the rectangle regardless of proximity to your actual route.

```
node["amenity"="fuel"](37.2,-122.1,37.5,-121.8);
```

### `around` Filter (Polyline Corridor)
Accepts a radius in meters plus a sequence of lat/lon coordinate pairs, and returns all matching elements within that distance of *any point along the line*. This is the correct approach for route-based queries.

```
[out:json];
(
  node["amenity"~"fuel|restaurant|toilets"](around:5000,
    37.3382,-121.8863,
    37.3500,-121.8700,
    37.3700,-121.8500
  );
);
out body;
```

You can feed it as many coordinate pairs as needed — a full GPX route exported as lat/lon pairs works directly. The `around` radius of 5,000 meters gives a 5km corridor on each side of the line.

---

## Public Infrastructure: Two Different Things

### overpass-api.de
The **backend server** — runs the Overpass engine and executes queries against the OSM database. You hit it programmatically via HTTP:

```
https://overpass-api.de/api/interpreter?data=...
```

No UI. Raw data in, results out (JSON, XML, or CSV). Use this in scripts and pipelines.

### overpass-turbo.eu
A **web-based IDE** built on top of the API. Provides a query editor, live map visualization of results, syntax highlighting, error messages, and a Wizard mode (type `fuel near San Jose` → generates Overpass QL automatically). Under the hood it sends your query to a public API instance and renders the response on a Leaflet map.

**Workflow:** Build and test queries in turbo.eu. Once they work, move them into scripts pointing at the API directly.

Other public API instances exist (`overpass.kumi.systems`, OpenStreetMap France) and can be used as alternates if the main instance is slow.

---

## Rate Limits on the Public Instance

The public instance uses a **slot-based system**, not a simple requests-per-minute counter:

- Each IP gets a limited number of concurrent query **slots** (typically 2)
- If both slots are occupied, new requests queue or get a 429
- A separate "rate limit" tracks how much **server CPU time** your IP has consumed recently
- Heavy queries (10+ seconds of CPU each) will get you throttled faster than many cheap ones
- The actual limits are **deliberately unpublished** and adjust dynamically with server load

**What triggers throttling:**
- Long-running queries
- Rapid-fire sequential requests from the same IP
- Very large result sets

### `around` vs `bbox` — Rate Limit Treatment

Neither is favored by policy — both are judged purely on query execution time and result size. However, `around` with a long polyline is often *slower* than an equivalent `bbox` because the server must compute distances from every candidate element to every point in your line. So `around` can indirectly burn more of your rate limit budget per query than a tight `bbox` over a small area.

---

## Optimization Strategies for Route Queries

### 1. Simplify Your Polyline Aggressively
The biggest lever. A 200-mile GPX route may have thousands of trackpoints — Overpass doesn't need that resolution. Use **Ramer-Douglas-Peucker simplification** to reduce to ~20–50 points while preserving the corridor shape. A 5km `around` radius is forgiving enough that you lose nothing meaningful.

### 2. Split Long Routes Into Segments and Cache Results
Break a 300-mile route into 50-mile chunks, query each separately, and cache the JSON response. Route geometry doesn't change, so cached results are valid for weeks. If you query the same segment again later, serve from cache.

### 3. Declare `[timeout]` and `[maxsize]` Upfront
Prevents runaway queries from burning your slot for minutes:

```
[out:json][timeout:60][maxsize:536870912];
```

### 4. Filter Aggressively — Fetch Only What You Need
Be specific in the query rather than grabbing everything and filtering client-side:

```
node["amenity"~"fuel|restaurant|toilets"](around:5000,...);
```

Narrow tag filters dramatically reduce result size and server work.

### 5. Use `out ids center;` Instead of Full Geometry
If you just need to know what exists and roughly where, request only IDs and center points rather than full way geometry:

```
out ids center;
```

Cuts response size significantly.

### 6. Bbox Pre-filter Trick
Do a fast `bbox` query over the route's overall envelope first. If it comes back empty for a given amenity type, skip the `around` query entirely. Cheap bbox miss → no expensive around query.

### 7. Honor `Retry-After`
When you get a 429, the response includes a `Retry-After` header. Honor it rather than retrying immediately.

---

## Self-Hosting: California Extract

GPXSheet ships a ready-to-run self-hosted Overpass stack in the repo's
[`osm/`](https://github.com/pleasantone/gpxsheet/tree/main/osm) directory — a
self-contained Docker Compose service that imports the Geofabrik California extract,
keeps it current from Geofabrik diffs, and serves the standard Overpass API locally
(no slot/CPU rate limits, so you can use unsimplified tracks and fire queries
rapidly). See [`osm/README.md`](https://github.com/pleasantone/gpxsheet/blob/main/osm/README.md)
for setup, requirements (disk/RAM), data freshness, and operations.

Wire gpxsheet to it with `GPXSHEET_OVERPASS_URL=http://localhost:12345/api` (the base
`/api` — osmnx appends `/interpreter`); see the deploy guide's
[Self-hosted Overpass](deploy.md#self-hosted-overpass) section.

---

## Query Template for Route Corridor

Complete template for querying motorcycle-relevant POIs within 5km of a route:

```
[out:json][timeout:120][maxsize:1073741824];
(
  node["amenity"~"fuel|restaurant|fast_food|cafe|toilets"](around:5000,
    LAT1,LON1,
    LAT2,LON2,
    LAT3,LON3
  );
  node["tourism"~"hotel|motel|camp_site|caravan_site"](around:5000,
    LAT1,LON1,
    LAT2,LON2,
    LAT3,LON3
  );
  node["shop"="motorcycle"](around:5000,
    LAT1,LON1,
    LAT2,LON2,
    LAT3,LON3
  );
);
out ids center;
```

Replace `LAT,LON` pairs with a simplified version of your GPX track. Use `out body;` instead of `out ids center;` if you want full tags and metadata.
