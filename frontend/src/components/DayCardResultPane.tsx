import { useState } from "react";
import {
  fmtClock,
  fmtDistance,
  fmtDuration,
  fmtElev,
  fmtSpeed,
  fmtTemp,
} from "../dayCardFormat";
import type {
  DayAir,
  DayCardData,
  DayFire,
  DaySun,
  DayWeather,
  DayWarning,
} from "../types";
import { Spinner } from "./Spinner";

interface DayCardResultPaneProps {
  data: DayCardData[] | null;
  markdown: string | null;
  imperial: boolean;
  loading: boolean;
  error: string | null;
}

export function DayCardResultPane({
  data,
  markdown,
  imperial,
  loading,
  error,
}: DayCardResultPaneProps) {
  const baseName = (data && data.length > 0 && data[0].name) || "route";

  return (
    <div className="space-y-3">
      {data && data.length > 0 && (
        <div className="flex gap-2">
          <CopyButton testId="copy-daycard-md" label="Copy Markdown" text={markdown} />
        </div>
      )}

      {loading && (
        <div className="rounded-xl border border-slate-200 bg-white min-h-40 flex flex-col items-center justify-center gap-2 py-8 text-slate-400">
          <Spinner className="w-8 h-8" />
          <span className="text-sm">Building day cards…</span>
        </div>
      )}

      {!loading && error && (
        <div className="rounded-xl border border-slate-200 bg-white min-h-40 flex items-center justify-center">
          <p className="text-sm text-red-600 py-8 px-4 text-center">{error}</p>
        </div>
      )}

      {!loading && !error && data && data.length > 0 && (
        <div data-testid="daycard-output" className="space-y-4">
          {data.map((day) => (
            <DayCard key={day.index} day={day} imperial={imperial} />
          ))}
        </div>
      )}

      {!loading && !error && (!data || data.length === 0) && (
        <div className="rounded-xl border border-slate-200 bg-white min-h-40 flex items-center justify-center">
          <p className="text-sm text-slate-400 py-8">Drop a GPX file to build day cards</p>
        </div>
      )}

      {data && data.length > 0 && (
        <div className="flex gap-2">
          <DownloadButton
            testId="download-daycard-md"
            label="Download Markdown"
            text={markdown}
            filename={`${baseName}.md`}
            mime="text/markdown"
          />
          <DownloadButton
            testId="download-daycard-json"
            label="Download JSON"
            text={JSON.stringify(data, null, 2)}
            filename={`${baseName}.daycard.json`}
            mime="application/json"
          />
        </div>
      )}
    </div>
  );
}

function DayCard({ day, imperial }: { day: DayCardData; imperial: boolean }) {
  const title = `Day ${day.index + 1}${day.name ? `: ${day.name}` : ""}`;
  const dateLabel = day.date ? day.date.slice(0, 10) : null;

  const stats: string[] = [
    fmtDistance(day.miles, imperial),
    `moving ${fmtDuration(day.moving_minutes)}`,
  ];
  if (day.arrive) stats.push(`arrive ~${fmtClock(day.arrive)}`);

  return (
    <section
      data-testid={`daycard-day-${day.index}`}
      className="rounded-xl border border-slate-200 bg-white p-4 space-y-3"
    >
      <header className="flex items-baseline justify-between gap-3 border-b border-slate-100 pb-2">
        <h3 className="text-base font-semibold text-slate-800">{title}</h3>
        {dateLabel && <span className="text-sm text-slate-400">{dateLabel}</span>}
      </header>

      <p className="text-sm text-slate-600">{stats.join("  ·  ")}</p>

      {day.elevation_gain_ft != null && (
        <Line
          icon="⛰"
          text={
            `Climb: ${fmtElev(day.elevation_gain_ft, imperial)} gain` +
            (day.elevation_max_ft != null
              ? `, max ${fmtElev(day.elevation_max_ft, imperial)}`
              : "")
          }
        />
      )}

      {day.sun && <SunLine sun={day.sun} imperial={imperial} />}

      {day.passes.length > 0 && (
        <Line
          icon="🏔"
          text={`Passes: ${day.passes
            .map((p) =>
              p.elevation_ft != null
                ? `${p.name} (${fmtElev(p.elevation_ft, imperial)})`
                : p.name,
            )
            .join(", ")}`}
        />
      )}

      {day.scenic.length > 0 && (
        <Line icon="📷" text={`Scenic: ${day.scenic.map((p) => p.name).join(", ")}`} />
      )}

      {day.weather && <WeatherLine weather={day.weather} imperial={imperial} />}
      {day.air && <AirLine air={day.air} />}
      {day.fire.length > 0 && <FireLine fires={day.fire} imperial={imperial} />}

      {day.gravel.length > 0 && (
        <Line
          icon="🟫"
          text={`Gravel/unpaved: ${day.gravel
            .map(
              (g) =>
                `${fmtDistance(g.start_mile, imperial)}–${fmtDistance(g.end_mile, imperial)}`,
            )
            .join(", ")}`}
        />
      )}

      {day.construction.length > 0 && (
        <Line
          icon="🚧"
          text={`Construction: ${day.construction.map((p) => p.name).join(", ")}`}
        />
      )}

      {day.wildlife.length > 0 && (
        <Line icon="🦌" text={`Wildlife: ${day.wildlife.map((p) => p.name).join(", ")}`} />
      )}

      {day.no_services.length > 0 && (
        <Line
          icon="⛽"
          text={`No services: ${day.no_services
            .map(
              (g) =>
                `${fmtDistance(g.start_mile, imperial)}–${fmtDistance(g.end_mile, imperial)}` +
                ` (${fmtDistance(g.end_mile - g.start_mile, imperial)})`,
            )
            .join(", ")}`}
        />
      )}

      {!day.date && (
        <p className="text-xs text-slate-400 italic">
          Add a departure time for sun + weather.
        </p>
      )}

      {day.warnings.length > 0 && <Warnings warnings={day.warnings} />}
    </section>
  );
}

function Line({ icon, text }: { icon: string; text: string }) {
  return (
    <p className="text-sm text-slate-600 flex gap-2">
      <span aria-hidden className="shrink-0">
        {icon}
      </span>
      <span>{text}</span>
    </p>
  );
}

function SunLine({ sun, imperial }: { sun: DaySun; imperial: boolean }) {
  const parts: string[] = [];
  if (sun.sunrise) parts.push(`↑ ${fmtClock(sun.sunrise)}`);
  if (sun.sunset) parts.push(`↓ ${fmtClock(sun.sunset)}`);
  let text = `Sun: ${parts.join("  ")}`;
  if (sun.after_dark) {
    text +=
      sun.dark_from_mile != null
        ? ` — riding after dark from ${fmtDistance(sun.dark_from_mile, imperial)}`
        : " — finishes after dark";
  }
  if (parts.length === 0 && !sun.after_dark) return null;
  return <Line icon="☀" text={text} />;
}

function range(values: (number | null)[]): [number, number] | null {
  const nums = values.filter((v): v is number => v != null);
  if (nums.length === 0) return null;
  return [Math.min(...nums), Math.max(...nums)];
}

function WeatherLine({ weather, imperial }: { weather: DayWeather; imperial: boolean }) {
  if (weather.samples.length === 0) {
    return <Line icon="🌦" text={`Weather: ${weather.note ?? "unavailable"}`} />;
  }
  const parts: string[] = [];
  const temp = range(weather.samples.map((s) => s.temp_f));
  if (temp) {
    parts.push(
      temp[0] === temp[1]
        ? fmtTemp(temp[0], imperial)
        : `${fmtTemp(temp[0], imperial)}–${fmtTemp(temp[1], imperial)}`,
    );
  }
  const wind = range(weather.samples.map((s) => s.wind_mph));
  if (wind) parts.push(`wind ≤${fmtSpeed(wind[1], imperial)}`);
  const cross = range(weather.samples.map((s) => s.crosswind_mph));
  if (cross && cross[1] > 0) parts.push(`crosswind ≤${fmtSpeed(cross[1], imperial)}`);
  const precip = range(weather.samples.map((s) => s.precip_prob));
  if (precip && precip[1] > 0) parts.push(`precip ≤${Math.round(precip[1])}%`);
  return <Line icon="🌦" text={`Weather: ${parts.join(", ")}`} />;
}

function AirLine({ air }: { air: DayAir }) {
  const parts: string[] = [];
  if (air.max_aqi != null) parts.push(`AQI ${air.max_aqi}`);
  if (air.max_pm25 != null) parts.push(`PM2.5 ${Math.round(air.max_pm25)}`);
  if (air.smoke) parts.push("smoke");
  if (parts.length === 0) return null;
  return <Line icon="🌫" text={`Air: ${parts.join(", ")}`} />;
}

function FireLine({ fires, imperial }: { fires: DayFire[]; imperial: boolean }) {
  const text = fires
    .map(
      (f) =>
        `${f.name} (${fmtDistance(f.dist_mi, imperial)}${f.status ? `, ${f.status}` : ""})`,
    )
    .join(", ");
  return <Line icon="🔥" text={`Wildfire: ${text}`} />;
}

function Warnings({ warnings }: { warnings: DayWarning[] }) {
  return (
    <ul className="space-y-1 border-t border-slate-100 pt-2">
      {warnings.map((w, i) => (
        <li
          key={i}
          className={`text-sm flex gap-2 ${
            w.level === "warning" ? "text-amber-700" : "text-slate-500"
          }`}
        >
          <span aria-hidden className="shrink-0">
            {w.level === "warning" ? "⚠" : "·"}
          </span>
          <span>{w.message}</span>
        </li>
      ))}
    </ul>
  );
}

function DownloadButton({
  label,
  text,
  filename,
  mime,
  testId,
}: {
  label: string;
  text: string | null;
  filename: string;
  mime: string;
  testId: string;
}) {
  function download() {
    if (!text) return;
    const url = URL.createObjectURL(new Blob([text], { type: mime }));
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <button
      data-testid={testId}
      onClick={download}
      disabled={!text}
      className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
    >
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3"
        />
      </svg>
      {label}
    </button>
  );
}

function CopyButton({
  label,
  text,
  testId,
}: {
  label: string;
  text: string | null;
  testId: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked (e.g. insecure context) — leave the label unchanged.
    }
  }

  return (
    <button
      data-testid={testId}
      onClick={copy}
      disabled={!text}
      className="flex-1 rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
    >
      {copied ? "Copied!" : label}
    </button>
  );
}
