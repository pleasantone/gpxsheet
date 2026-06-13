// One normalized display model for the Table tab, derived from the structured
// JSON + the client-side display toggles (units / coordinates / cue). The React
// view AND the markdown/HTML exporters all render from this, so the on-screen
// table and the copied/downloaded text never drift.

import {
  fmtClock,
  fmtDeparture,
  fmtDist,
  fmtDistCell,
  fmtLatLon,
  fmtLayover,
  fmtSpeed,
} from "./tableFormat";
import type { TableDocData, TableOptions } from "./types";

export interface DisplayRow {
  name: string;
  latlon: string | null; // null unless coordinates are shown
  dist: string;
  marker: string; // edge-blanked G/L/GL, matching the old table
  eta: string;
  road: string; // "" when this row has no road name
  notes: string; // symbol + layover suffix
}

export interface DisplayCue {
  mile: string;
  eta: string;
  cue: string; // instruction + " — skip A, B"
}

export interface DisplaySection {
  title: string;
  departure: string | null; // friendly "9:00 AM, Jun 12"
  distance: string; // "45 mi"
  speed: string; // "avg 30 mph" / "OSM limits · avg 32 mph"
  sun: { sunrise: string; sunset: string } | null;
  showRoad: boolean; // any row in this section has a road name
  rows: DisplayRow[];
  cue: DisplayCue[]; // empty unless the cue toggle is on
}

export interface DisplayModel {
  name: string;
  showCoords: boolean;
  showCueAnywhere: boolean; // any section has cue rows (with the toggle on)
  sections: DisplaySection[];
}

export function buildDisplayModel(doc: TableDocData, opts: TableOptions): DisplayModel {
  const imperial = opts.units === "imperial";
  const sections = doc.sections.map((sec) => {
    const last = sec.rows.length - 1;
    const showRoad = sec.rows.some((r) => r.road);
    const rows: DisplayRow[] = sec.rows.map((r, i) => {
      const isEdge = i === 0 || i === last;
      const split = r.fuel_reset || i === last;
      return {
        name: r.name,
        latlon: opts.coordinates ? fmtLatLon(r.lat, r.lon) : null,
        dist: fmtDistCell(r.mile, r.since_gas_mi, imperial, split),
        marker: isEdge ? "" : r.marker, // old table blanks edge markers
        eta: fmtClock(r.eta),
        road: r.road ?? "",
        notes: (r.symbol ?? "") + fmtLayover(r.layover_min),
      };
    });
    const cue: DisplayCue[] = opts.cue
      ? sec.cue.map((c) => ({
          mile: fmtDist(c.mile, imperial).replace(/ (mi|km)$/, ""),
          eta: fmtClock(c.eta),
          cue: c.instruction + (c.skip.length ? ` — skip ${c.skip.join(", ")}` : ""),
        }))
      : [];
    const speed =
      sec.speed.mode === "osm"
        ? `OSM limits · avg ${fmtSpeed(sec.speed.avg_mph, imperial)}`
        : `avg ${fmtSpeed(sec.speed.avg_mph, imperial)}`;
    const sun =
      sec.sun && sec.sun.sunrise && sec.sun.sunset
        ? { sunrise: fmtClock(sec.sun.sunrise), sunset: fmtClock(sec.sun.sunset) }
        : null;
    return {
      title: sec.title,
      departure: fmtDeparture(sec.departure),
      distance: fmtDist(sec.distance_mi, imperial),
      speed,
      sun,
      showRoad,
      rows,
      cue,
    };
  });
  return {
    name: doc.name,
    showCoords: opts.coordinates,
    showCueAnywhere: sections.some((s) => s.cue.length > 0),
    sections,
  };
}
