# GPXSheet Product Design Specification

### Version 1.0

### Motorcycle Sport-Touring Route Awareness Generator

---

# Executive Summary

GPXSheet is a Python-based command-line application and reusable library that converts GPX routes into highly glanceable, map-centric motorcycle navigation PDFs optimized for tank-bag use.

Unlike rally roadbooks, GPS turn-by-turn navigation, or printed map exports, GPXSheet is designed specifically for motorcycle sport-touring riders traveling long distances on back roads where:

* Navigation decisions are infrequent
* Situational awareness is more important than detailed navigation
* Riders need to understand where they are in the route at a glance
* Printed navigation remains valuable as a primary or backup navigation tool

Examples include roads such as:

* Skaggs Springs Road
* Mines Road
* CA-36
* Sierra Foothill routes
* Trinity County routes
* Backcountry paved touring routes
* Mixed-surface touring routes

The product's primary goal is:

> Allow a rider to glance at a tank-bag navigation sheet for less than one second and immediately understand:
>
> * What road they are on
> * What their next navigation decision is
> * How far away it is
> * What comes after that
> * Where they are within the overall route

---

# Design Philosophy

## Not a Rally Roadbook

GPXSheet is intentionally not optimized for:

* Rally navigation
* Tulip diagrams
* Off-road rally racing
* Constant navigation prompts

Those use cases are already well served by existing roadbook software.

---

## Not a GPS Replacement

GPXSheet is not intended to replace:

* Garmin
* CarPlay
* Android Auto
* Smartphone navigation

Instead, it provides:

* Route context
* Route awareness
* Backup navigation
* Enhanced situational understanding

---

## Primary Design Principle

The rider should never need to ask:

* Am I still on the route?
* What road am I on?
* What is my next decision?
* How far away is it?
* How much farther is the ride?

---

# Supported Inputs

## Initial Support

### GPX Track

```xml
<trk>
```

### GPX Route

```xml
<rte>
```

### GPX Track + Waypoints

```xml
<trk>
<wpt>
```

---

## Future Support

* Kurviger exports
* Garmin BaseCamp exports
* REVER exports
* Combined route/track files

---

# System Architecture

```text
GPX
 ↓
Geometry Cleanup
 ↓
OSM Enrichment
 ↓
Decision Point Detection
 ↓
Reassurance Marker Detection
 ↓
Fuel Analysis
 ↓
Route Simplification
 ↓
Route Graph Construction
 ↓
Schematic Layout Engine
 ↓
PDF Rendering
```

---

# Product Components

## Command Line Interface

```bash
gpxsheet route.gpx
```

Default behavior:

```bash
gpxsheet route.gpx \
  --profile sport-touring
```

Advanced example:

```bash
gpxsheet route.gpx \
  --profile sport-touring \
  --fuel-range 180 \
  --reassurance-interval 15 \
  --output route.pdf
```

---

## Library API

```python
from gpxsheet import generate_pdf

generate_pdf(
    gpx_file="route.gpx",
    output_file="route.pdf",
    profile="sport-touring",
    fuel_range=180
)
```

---

## Future Web Service

```http
POST /generate
```

Returns:

```json
{
  "pdf_url": "...",
  "decision_points": [...],
  "fuel_stops": [...],
  "markers": [...]
}
```

---

# User Profiles

## Minimalist

Purpose:

Maximum simplicity.

Includes:

* Critical navigation decisions only

Excludes:

* Fuel information
* Reassurance markers
* Supplemental annotations

---

## Sport-Touring (Default)

Primary target profile.

Includes:

* Critical navigation decisions
* Fuel opportunities
* Reassurance markers
* Town labels
* Road name ribbon

Suppresses:

* Navigation noise
* Unnecessary intersections

---

## Rally

Includes:

* All sport-touring features
* Confirmation points
* Additional route annotations
* More frequent markers

---

# OSM Enrichment

OpenStreetMap data is used to enrich the GPX.

Collected information:

* Road names
* Road classifications
* Intersections
* Junction geometry
* Towns
* Fuel stations
* Geographic features

---

# Decision Point Engine

The Decision Point Engine is the core intelligence layer.

---

## Significant Intersections

Significance is determined by three rule sets.

### Rule Set 1: Road Name Changes

Example:

```text
Skaggs Springs Rd
→ Annapolis Rd
```

Even if physically straight.

---

### Rule Set 2: Major Road Crossings

Examples:

* State highways
* County highways
* Major collectors
* Arterial roads

---

### Rule Set 3: Route Ambiguity

Examples:

```text
Y intersection
```

```text
T intersection
```

```text
Fork
```

Situations where a rider could easily choose the wrong path.

---

# Significance Scoring

Every route event receives a score.

Example scoring:

| Event                  | Score |
| ---------------------- | ----- |
| Road name change       | +40   |
| State highway junction | +50   |
| County road junction   | +30   |
| Y intersection         | +60   |
| T intersection         | +60   |
| Fuel opportunity       | +20   |
| Town center            | +20   |

Profile settings determine display thresholds.

---

# Decision Point Types

## Critical Turn

Examples:

```text
Right on Skaggs Springs Rd
```

```text
Left on CA-1
```

```text
Continue onto Mines Rd
```

Highest priority.

---

## Confirmation Point

Displayed only in Rally profile.

Examples:

```text
Continue through stop sign
```

```text
Continue across bridge
```

---

## Fuel Point

Examples:

```text
Fuel Available
Gualala
```

---

# Reassurance Markers

Purpose:

Provide confidence between major navigation decisions.

---

## Placement Rules

Markers are generated when:

* Entering towns
* Crossing major geographic features
* Passing major landmarks
* Exceeding distance intervals

---

## Default Interval

```text
15 miles
```

---

## Examples

```text
Continue CA-36

Wildwood
15 mi

Platina
31 mi

South Fork Summit
44 mi
```

---

# Fuel Intelligence

User configurable.

Example:

```bash
--fuel-range 180
```

---

## Analysis Performed

* Fuel stations near route
* Longest fuel gap
* Recommended fuel locations
* Fuel-range warnings

---

## Example Output

```text
Longest Fuel Gap:
104 miles

Recommended Fuel:
Gualala
Fort Bragg
Leggett
```

---

## Warning Example

```text
⚠ Fuel gap exceeds configured range
```

---

# Route Simplification

Aggressive simplification is required.

---

## Goals

Preserve:

* Major curves
* Route character
* Junction geometry

Remove:

* GPS noise
* Redundant points
* Excessive detail

---

## Expected Reduction

Target:

```text
95%+ point reduction
```

for recorded tracks.

---

# Route Graph Model

Internal representation:

```python
Route
 ├─ Segments
 ├─ DecisionPoints
 ├─ ReassuranceMarkers
 ├─ FuelStops
 └─ Pages
```

Example segment:

```python
Segment(
    name="Skaggs Springs Rd",
    length_miles=35.7
)
```

Example decision:

```python
DecisionPoint(
    mile=35.7,
    instruction="Left onto CA-1",
    significance=95
)
```

---

# Hybrid Schematic Map System

## Core Philosophy

Do not render the GPX directly.

Instead:

```text
Route Graph
 ↓
Schematic Layout Engine
 ↓
Map Strip
```

---

## Hybrid Schematic Design

Characteristics:

* Preserves route character
* Preserves major bends
* Compresses low-information stretches
* Exaggerates important junctions
* Improves readability

Inspiration:

* AAA TripTik
* Aviation charts
* Transit maps

Not:

* GIS maps
* Garmin maps
* Google Maps printouts

---

# Segment Compression

Visual size is determined by information density.

Example:

| Segment                 | Real Distance | Visual Length |
| ----------------------- | ------------- | ------------- |
| Long uninterrupted road | 40 mi         | Medium        |
| Complex junction        | 2 mi          | Large         |
| Town center             | 1 mi          | Large         |
| Fuel stop               | 0 mi          | Medium        |

---

# Road Name Ribbon

Displayed on every page.

Example:

```text
Skaggs Springs Rd
========================

Annapolis Rd
============

CA-1
====================

Fort Bragg
```

Purpose:

Allow navigation by road names.

---

# Page Layout

## Format

Landscape US Letter.

Optimized for:

* Color printing
* Tank-bag viewing
* Sunlight readability

---

## Header

```text
Route Name
Page X of Y
```

---

## Map Zone

Approximately:

```text
70% of page height
```

Contains:

* Hybrid schematic route strip
* Decision points
* Fuel markers
* Reassurance markers
* Town labels

---

## Cue Zone

Large text.

Example:

```text
NEXT
7.3 mi

Left CA-1

AFTER
12.8 mi

Fuel Gualala

TOTAL
64 / 217 mi
```

---

## Progress Indicator

Every page contains:

```text
START
│
│========
│============
│==== YOU
│
│==========
│
END
```

Purpose:

Immediate route progress awareness.

---

# Route-Aware Pagination

Pages are not split solely by mileage.

Page breaks should occur near:

* Major decisions
* Road transitions
* Significant route changes

This preserves continuity.

---

# Rendering Priorities

## Level 1

Next navigation decision.

---

## Level 2

Upcoming navigation decision.

---

## Level 3

Map strip.

---

## Level 4

Reassurance markers.

---

## Level 5

Metadata.

---

# Output Modes

## Analyze

```bash
gpxsheet analyze route.gpx
```

Produces route analysis.

Example:

```text
Route Length: 217.3 mi

Decision Points:
  35.7  L onto CA-1
  78.2  R onto CA-128

Fuel:
  Gualala
  Fort Bragg

Longest Fuel Gap:
  104 mi

Road Segments:
  Skaggs Springs Rd
  CA-1
  CA-128
```

---

## Generate PDF

```bash
gpxsheet route.gpx
```

Produces:

```text
route.pdf
```

---

## Validate

```bash
gpxsheet validate route.gpx
```

Detects:

```text
⚠ Fuel gap exceeds configured range

⚠ Route contains unpaved segment

⚠ Seasonal closure risk

⚠ Ferry crossing present
```

---

# Recommended Technology Stack

## GPX Parsing

```python
gpxpy
```

## OSM Integration

```python
osmnx
```

## Geometry

```python
shapely
```

## Graph Analysis

```python
networkx
```

## Mapping

```python
matplotlib
```

## PDF Generation

```python
reportlab
```

## CLI

```python
typer
```

---

# Phase 1 Deliverables

## Milestone 1

Route analysis engine.

Outputs:

* Decision points
* Fuel points
* Reassurance markers

---

## Milestone 2

Schematic map-strip renderer.

Outputs:

```text
route_strip.png
```

---

## Milestone 3

PDF generation.

Outputs:

```text
route.pdf
```

Including:

* Map strip
* Cue blocks
* Road ribbon
* Fuel analysis
* Progress indicator

---

## Milestone 4

Packaged CLI.

```bash
pip install gpxsheet
```

---

## Milestone 5

Web service extraction.

Expose the same engine through REST APIs.

---

# Success Criteria

The product succeeds if a rider can glance at the printed document for less than one second and reliably determine:

* Current road
* Next navigation decision
* Distance to that decision
* Upcoming fuel opportunities
* Overall route progress
* Confidence that they remain on the intended route

without needing to interpret a traditional map, tulip diagram, or turn-by-turn GPS interface.

