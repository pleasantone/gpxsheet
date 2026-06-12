import type { DayCardOptions, Profile, Units } from "../types";
import { Checkbox, NumberInput, Row, Select } from "./controls";

interface DayCardOptionsPanelProps {
  opts: DayCardOptions;
  onChange: (opts: DayCardOptions) => void;
  disabled: boolean;
}

// A small, common set of IANA zones; empty = let the backend use the GPX/local default.
const TIMEZONES = [
  { value: "", label: "Default (GPX / local)" },
  { value: "US/Pacific", label: "US/Pacific" },
  { value: "US/Mountain", label: "US/Mountain" },
  { value: "US/Central", label: "US/Central" },
  { value: "US/Eastern", label: "US/Eastern" },
  { value: "UTC", label: "UTC" },
  { value: "Europe/London", label: "Europe/London" },
  { value: "Europe/Paris", label: "Europe/Paris" },
];

export function DayCardOptionsPanel({ opts, onChange, disabled }: DayCardOptionsPanelProps) {
  function set<K extends keyof DayCardOptions>(key: K, value: DayCardOptions[K]) {
    onChange({ ...opts, [key]: value });
  }

  return (
    <div className="space-y-4">
      <Row label="Departure">
        <input
          data-testid="dc-departure"
          type="datetime-local"
          value={opts.departure ?? ""}
          onChange={(e) => set("departure", e.target.value === "" ? null : e.target.value)}
          disabled={disabled}
          className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        />
        <p className="text-xs text-slate-400 mt-1">Blank = no sun / weather</p>
      </Row>

      <Row label="Units">
        <Select
          testId="dc-units"
          value={opts.units}
          onChange={(v) => set("units", v as Units)}
          disabled={disabled}
          options={[
            { value: "imperial", label: "Imperial (mi / °F)" },
            { value: "metric", label: "Metric (km / °C)" },
          ]}
        />
      </Row>

      <Row label={`Speed (${opts.units === "metric" ? "kph" : "mph"})`}>
        <NumberInput
          testId="dc-speed"
          value={opts.speed}
          min={0}
          max={200}
          onChange={(v) => set("speed", v)}
          disabled={disabled}
        />
        <p className="text-xs text-slate-400 mt-1">0 = auto</p>
      </Row>

      <Row label="Profile">
        <Select
          testId="dc-profile"
          value={opts.profile}
          onChange={(v) => set("profile", v as Profile)}
          disabled={disabled}
          options={[
            { value: "minimalist", label: "Minimalist" },
            { value: "sport-touring", label: "Sport-touring" },
            { value: "rally", label: "Rally" },
          ]}
        />
      </Row>

      <Row label="Fuel range (mi)">
        <NumberInput
          testId="dc-fuel-range"
          value={opts.fuel_range ?? 0}
          min={0}
          max={1000}
          onChange={(v) => set("fuel_range", v > 0 ? v : null)}
          disabled={disabled}
        />
        <p className="text-xs text-slate-400 mt-1">0 = profile default</p>
      </Row>

      <Row label="Timezone">
        <Select
          testId="dc-timezone"
          value={opts.timezone ?? ""}
          onChange={(v) => set("timezone", v === "" ? null : v)}
          disabled={disabled}
          options={TIMEZONES}
        />
      </Row>

      <Row label="Options">
        <div className="space-y-2">
          <Checkbox
            testId="dc-osm"
            checked={opts.osm}
            onChange={(v) => set("osm", v)}
            label="OSM enrichment (auto fuel, road names)"
            disabled={disabled}
          />
          <Checkbox
            testId="dc-live"
            checked={opts.live}
            onChange={(v) => set("live", v)}
            label="Live conditions (weather, smoke, wildfire)"
            disabled={disabled}
          />
        </div>
      </Row>
    </div>
  );
}
