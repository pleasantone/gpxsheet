// One display model per day, derived from the structured JSON + the units
// toggle. The React card AND the Markdown/HTML exporters render from this, so the
// on-screen card and the copied/downloaded text never drift. Mirrors the section
// set of the backend's build_day_cards_markdown.

import {
  fmtClock,
  fmtDistance,
  fmtDuration,
  fmtElev,
  fmtSpeed,
  fmtTemp,
} from "./dayCardFormat";
import type { DayAir, DayCardData, DaySun, DayWeather } from "./types";

export interface DayCardLine {
  icon: string;
  text: string; // "Label: …" — self-describing (no icon needed in exports)
}

export interface DayCardView {
  index: number;
  title: string; // "Day 1: Name"
  date: string | null; // YYYY-MM-DD
  stats: string;
  lines: DayCardLine[];
  hint: string | null; // shown when a day has no departure
  warnings: { level: string; message: string }[];
  attributions: string[];
}

function range(values: (number | null)[]): [number, number] | null {
  const nums = values.filter((v): v is number => v != null);
  return nums.length ? [Math.min(...nums), Math.max(...nums)] : null;
}

function sunText(sun: DaySun, imperial: boolean): string | null {
  const parts: string[] = [];
  if (sun.sunrise) parts.push(`↑ ${fmtClock(sun.sunrise)}`);
  if (sun.sunset) parts.push(`↓ ${fmtClock(sun.sunset)}`);
  if (!parts.length && !sun.after_dark) return null;
  let text = `Sun: ${parts.join("  ")}`;
  if (sun.after_dark) {
    text +=
      sun.dark_from_mile != null
        ? ` — riding after dark from ${fmtDistance(sun.dark_from_mile, imperial)}`
        : " — finishes after dark";
  }
  return text;
}

function goldenText(sun: DaySun): string | null {
  const parts: string[] = [];
  if (sun.golden_morning_end) parts.push(`morning to ${fmtClock(sun.golden_morning_end)}`);
  if (sun.golden_evening_start) parts.push(`evening from ${fmtClock(sun.golden_evening_start)}`);
  return parts.length ? `Golden hour: ${parts.join(", ")}` : null;
}

function weatherText(w: DayWeather, imperial: boolean): string | null {
  if (w.samples.length === 0) return `Weather: ${w.note ?? "unavailable"}`;
  const parts: string[] = [];
  const temp = range(w.samples.map((s) => s.temp_f));
  if (temp) {
    parts.push(
      temp[0] === temp[1]
        ? fmtTemp(temp[0], imperial)
        : `${fmtTemp(temp[0], imperial)}–${fmtTemp(temp[1], imperial)}`,
    );
  }
  const wind = range(w.samples.map((s) => s.wind_mph));
  if (wind) parts.push(`wind ≤${fmtSpeed(wind[1], imperial)}`);
  const cross = range(w.samples.map((s) => s.crosswind_mph));
  if (cross && cross[1] > 0) parts.push(`crosswind ≤${fmtSpeed(cross[1], imperial)}`);
  const precip = range(w.samples.map((s) => s.precip_prob));
  if (precip && precip[1] > 0) parts.push(`precip ≤${Math.round(precip[1])}%`);
  return parts.length ? `Weather: ${parts.join(", ")}` : null;
}

function airText(air: DayAir): string | null {
  const parts: string[] = [];
  if (air.max_aqi != null) parts.push(`AQI ${air.max_aqi}`);
  if (air.max_pm25 != null) parts.push(`PM2.5 ${Math.round(air.max_pm25)}`);
  if (!parts.length) return null;
  return `Air: ${parts.join(", ")}${air.smoke ? " — possible smoke" : ""}`;
}

function span(a: number, b: number, imperial: boolean, withLen: boolean): string {
  const base = `${fmtDistance(a, imperial)}–${fmtDistance(b, imperial)}`;
  return withLen ? `${base} (${fmtDistance(b - a, imperial)})` : base;
}

/** The ordered caution/info lines for one day (climb → no-services). */
export function cardLines(day: DayCardData, imperial: boolean): DayCardLine[] {
  const lines: DayCardLine[] = [];
  const push = (icon: string, text: string | null) => {
    if (text) lines.push({ icon, text });
  };

  if (day.elevation_gain_ft != null) {
    const dem =
      day.elevation_profile && day.elevation_profile.source !== "gpx" ? " (approx, via DEM)" : "";
    push(
      "⛰",
      `Climb: ${fmtElev(day.elevation_gain_ft, imperial)} gain` +
        (day.elevation_max_ft != null ? `, max ${fmtElev(day.elevation_max_ft, imperial)}` : "") +
        dem,
    );
  }
  if (day.sun) {
    push("☀", sunText(day.sun, imperial));
    push("🌅", goldenText(day.sun));
  }
  if (day.passes.length) {
    push(
      "🏔",
      `Passes: ${day.passes
        .map((p) => (p.elevation_ft != null ? `${p.name} (${fmtElev(p.elevation_ft, imperial)})` : p.name))
        .join(", ")}`,
    );
  }
  if (day.scenic.length) push("📷", `Scenic: ${day.scenic.map((p) => p.name).join(", ")}`);
  if (day.weather) push("🌦", weatherText(day.weather, imperial));
  if (day.air) push("🌫", airText(day.air));
  if (day.fire.length) {
    push(
      "🔥",
      `Wildfire: ${day.fire
        .map((f) => `${f.name} (${f.dist_mi > 0 ? fmtDistance(f.dist_mi, imperial) : "on route"})`)
        .join(", ")}`,
    );
  }
  if (day.gravel.length) {
    push("🟫", `Gravel/unpaved: ${day.gravel.map((g) => span(g.start_mile, g.end_mile, imperial, false)).join(", ")}`);
  }
  if (day.construction.length) {
    push("🚧", `Construction: ${day.construction.map((p) => p.name).join(", ")}`);
  }
  if (day.wildlife.length) push("🦌", `Wildlife: ${day.wildlife.map((p) => p.name).join(", ")}`);
  if (day.no_services.length) {
    push("⛽", `No services: ${day.no_services.map((g) => span(g.start_mile, g.end_mile, imperial, true)).join(", ")}`);
  }
  return lines;
}

export function buildDayCardModel(data: DayCardData[], imperial: boolean): DayCardView[] {
  return data.map((day) => {
    const stats = [
      fmtDistance(day.miles, imperial),
      `moving ${fmtDuration(day.moving_minutes)}`,
      ...(day.arrive ? [`arrive ~${fmtClock(day.arrive)}`] : []),
    ].join("  ·  ");
    return {
      index: day.index,
      title: `Day ${day.index + 1}${day.name ? `: ${day.name}` : ""}`,
      date: day.date ? day.date.slice(0, 10) : null,
      stats,
      lines: cardLines(day, imperial),
      hint: day.date ? null : "Add a departure time for sun + weather.",
      warnings: day.warnings.map((w) => ({ level: w.level, message: w.message })),
      attributions: day.attributions,
    };
  });
}
