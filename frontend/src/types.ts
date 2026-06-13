export type JobState = "queued" | "running" | "done" | "error";

export interface JobStatus {
  id: string;
  status: JobState;
  error?: string;
  result_url?: string;
  content_type?: string;
  // Jobs ahead of this one in the worker queue while it waits (null/omitted once
  // it starts or finishes, or when the backend can't order the queue).
  queue_position?: number | null;
}

export interface DecisionPoint {
  mile: number;
  instruction: string;
  significance: number;
}

export interface FuelStop {
  mile: number;
  name: string;
}

export interface Segment {
  name: string;
  start_mile: number;
  end_mile: number;
}

export interface AnalyzeResult {
  name: string;
  length_miles: number;
  decision_points: DecisionPoint[];
  fuel_stops: FuelStop[];
  segments: Segment[];
  longest_fuel_gap_miles: number | null;
}

export type Layout = "portrait" | "landscape" | "preview" | "strip";
export type Format = "pdf" | "png";
export type Profile = "minimalist" | "sport-touring" | "rally";
export type TurnStyle = "stylized" | "faithful";
export type Paper = "letter" | "a4";

export interface RenderOptions {
  profile: Profile;
  layout: Layout;
  format: Format;
  fuel_range: number | null;
  turn_style: TurnStyle;
  paper: Paper;
  lanes_per_page: number;
  decisions_per_lane: number;
  show_branches: boolean;
}

export const DEFAULT_OPTIONS: RenderOptions = {
  profile: "sport-touring",
  layout: "portrait",
  format: "pdf",
  fuel_range: null,
  turn_style: "stylized",
  paper: "letter",
  lanes_per_page: 4,
  decisions_per_lane: 0,
  show_branches: false,
};

// "sheet" = the PDF/PNG map renderers; "table" = the native route table
// (HTML/markdown); "daycard" = per-day read-ahead briefings (structured JSON).
// All rendered from the analyze pipeline (OSM on by default).
export type Mode = "sheet" | "table" | "daycard";
export type TableFormat = "html" | "markdown" | "json";
export type Units = "imperial" | "metric";

// The Table tab renders the structured `format=json` output and applies
// units/coordinates/cue as CLIENT-SIDE display toggles (no re-fetch). Only
// departure/speed/timezone/osm change the computed data (a backend re-run).
export interface TableOptions {
  departure: string | null; // value of a <input type="datetime-local">; null = no ETA
  speed: number; // mph/kph; 0 = auto (overrides OSM speeds)
  units: Units; // display-only: JSON is always imperial; converted in-browser
  coordinates: boolean; // display-only: show/hide lat/lon columns
  osm: boolean; // OSM enrichment: auto fuel, road names, road-snapped distance
  cue: boolean; // display-only: show/hide the turn-by-turn cue section
  timezone: string | null;
}

// JSON shapes — mirror routetable.TableDocument.to_dict() (always imperial:
// mi/mph; datetimes ISO 8601 with offset, null when absent).
export interface TableSpeedData {
  mode: string; // "osm" | "flat"
  avg_mph: number;
}

export interface TableSunData {
  sunrise: string | null;
  sunset: string | null;
}

export interface TableRowData {
  name: string;
  mile: number; // section-local distance from the section start
  since_gas_mi: number; // distance since the last fuel reset
  marker: string; // "" | "G" | "L" | "GL" (true classification, not edge-blanked)
  gas: boolean;
  lunch: boolean;
  fuel_reset: boolean;
  layover_min: number;
  eta: string | null;
  road: string | null;
  symbol: string | null;
  lat: number;
  lon: number;
}

export interface TableCueData {
  mile: number;
  eta: string | null;
  instruction: string;
  skip: string[];
}

export interface TableSectionData {
  day: number; // 1-based
  title: string; // e.g. "Route: Foo" or "Day 1: Coast"
  departure: string | null;
  distance_mi: number;
  speed: TableSpeedData;
  sun: TableSunData | null;
  rows: TableRowData[];
  cue: TableCueData[];
}

export interface TableDocData {
  name: string;
  units: string; // always "imperial"
  sections: TableSectionData[];
}

export const DEFAULT_TABLE_OPTIONS: TableOptions = {
  departure: null,
  speed: 0,
  units: "imperial",
  coordinates: false,
  osm: true,
  cue: false,
  timezone: null,
};

// ---------------------------------------------------------------------------
// Day card (per-day read-ahead briefing) — /v1/daycard
// ---------------------------------------------------------------------------

// The tab renders the structured JSON (one card per day) and builds its
// Markdown/HTML/JSON exports client-side, so it only ever requests `json`.
export type DayCardFormat = "json" | "markdown";

export interface DayCardOptions {
  departure: string | null; // datetime-local value; null = no sun/weather
  timezone: string | null;
  units: Units;
  speed: number; // mph/kph; 0 = auto
  profile: Profile;
  fuel_range: number | null; // null = profile default; drives no-services gaps
  osm: boolean;
  live: boolean; // keyless live providers (weather/air/elevation/wildfire)
}

export const DEFAULT_DAYCARD_OPTIONS: DayCardOptions = {
  departure: null,
  timezone: null,
  units: "imperial",
  speed: 0,
  profile: "sport-touring",
  fuel_range: null,
  osm: true,
  live: true,
};

// JSON shapes — mirror DayCard.to_dict() (src/gpxsheet/daycard.py). All values
// are IMPERIAL (mi/ft/°F/mph) regardless of the `units` param; convert
// client-side. Datetimes are ISO strings carrying their display-tz offset.

export interface DayPass {
  name: string;
  mile: number;
  elevation_ft: number | null;
}

export interface DayPOI {
  name: string;
  mile: number;
  kind: string;
}

export interface DaySpan {
  start_mile: number;
  end_mile: number;
  kind: string;
  name: string | null;
}

export interface DayServiceGap {
  start_mile: number;
  end_mile: number;
}

export interface DaySun {
  sunrise: string | null;
  sunset: string | null;
  golden_morning_end: string | null;
  golden_evening_start: string | null;
  after_dark: boolean;
  dark_from_mile: number | null;
}

export interface DayWeatherSample {
  mile: number;
  time: string | null;
  temp_f: number | null;
  feels_f: number | null;
  wind_mph: number | null;
  gust_mph: number | null;
  wind_dir_deg: number | null;
  crosswind_mph: number | null;
  precip_prob: number | null;
  precip_in: number | null;
  visibility_mi: number | null;
  code: number | null;
}

export interface DayWeather {
  source: string;
  as_of: string | null;
  note: string | null;
  samples: DayWeatherSample[];
}

export interface DayAir {
  max_aqi: number | null;
  max_pm25: number | null;
  smoke: boolean;
  source: string;
  as_of: string | null;
  note: string | null;
}

export interface DayFire {
  name: string;
  dist_mi: number;
  status: string | null;
  url: string | null;
}

export interface DayElevationProfile {
  min_ft: number | null;
  max_ft: number | null;
  gain_ft: number | null;
  source: string;
}

export interface DayWarning {
  level: string; // "warning" | "info"
  code: string;
  message: string;
}

export interface DayCardData {
  index: number;
  name: string;
  date: string | null;
  start_mile: number;
  end_mile: number;
  miles: number;
  moving_minutes: number | null;
  arrive: string | null;
  elevation_gain_ft: number | null;
  elevation_max_ft: number | null;
  passes: DayPass[];
  scenic: DayPOI[];
  construction: DayPOI[];
  wildlife: DayPOI[];
  gravel: DaySpan[];
  no_services: DayServiceGap[];
  sun: DaySun | null;
  weather: DayWeather | null;
  air: DayAir | null;
  fire: DayFire[];
  elevation_profile: DayElevationProfile | null;
  warnings: DayWarning[];
  attributions: string[];
}
