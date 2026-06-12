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
// (HTML/markdown) rendered from the analyze pipeline (OSM on by default).
export type Mode = "sheet" | "table";
export type TableFormat = "html" | "markdown";
export type Units = "imperial" | "metric";

export interface TableOptions {
  departure: string | null; // value of a <input type="datetime-local">; null = no ETA
  speed: number; // mph/kph; 0 = auto (overrides OSM speeds)
  units: Units;
  coordinates: boolean;
  osm: boolean; // OSM enrichment: auto fuel, road names, road-snapped distance
  cue: boolean; // append a turn-by-turn cue sheet
  timezone: string | null;
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
