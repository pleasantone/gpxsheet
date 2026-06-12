import type { TableOptions, Units } from "../types";
import { Checkbox, NumberInput, Row, Select } from "./controls";

interface TableOptionsPanelProps {
  opts: TableOptions;
  onChange: (opts: TableOptions) => void;
  disabled: boolean;
}

// A small, common set of IANA zones; empty = let GPXtable use the GPX/local default.
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

export function TableOptionsPanel({ opts, onChange, disabled }: TableOptionsPanelProps) {
  function set<K extends keyof TableOptions>(key: K, value: TableOptions[K]) {
    onChange({ ...opts, [key]: value });
  }

  return (
    <div className="space-y-4">
      <Row label="Departure">
        <input
          data-testid="tbl-departure"
          type="datetime-local"
          value={opts.departure ?? ""}
          onChange={(e) => set("departure", e.target.value === "" ? null : e.target.value)}
          disabled={disabled}
          className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        />
        <p className="text-xs text-slate-400 mt-1">Blank = no ETA column</p>
      </Row>

      <Row label="Units">
        <Select
          testId="tbl-units"
          value={opts.units}
          onChange={(v) => set("units", v as Units)}
          disabled={disabled}
          options={[
            { value: "imperial", label: "Imperial (mi / mph)" },
            { value: "metric", label: "Metric (km / kph)" },
          ]}
        />
      </Row>

      <Row label={`Speed (${opts.units === "metric" ? "kph" : "mph"})`}>
        <NumberInput
          testId="tbl-speed"
          value={opts.speed}
          min={0}
          max={200}
          onChange={(v) => set("speed", v)}
          disabled={disabled}
        />
        <p className="text-xs text-slate-400 mt-1">0 = auto</p>
      </Row>

      <Row label="Timezone">
        <Select
          testId="tbl-timezone"
          value={opts.timezone ?? ""}
          onChange={(v) => set("timezone", v === "" ? null : v)}
          disabled={disabled}
          options={TIMEZONES}
        />
      </Row>

      <Row label="Options">
        <div className="space-y-2">
          <Checkbox
            testId="tbl-coordinates"
            checked={opts.coordinates}
            onChange={(v) => set("coordinates", v)}
            label="Show coordinates"
            disabled={disabled}
          />
        </div>
      </Row>
    </div>
  );
}
