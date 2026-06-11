import type { Format, Layout, Paper, Profile, RenderOptions, TurnStyle } from "../types";
import { NumberInput, Row, Select } from "./controls";

interface OptionsPanelProps {
  opts: RenderOptions;
  onChange: (opts: RenderOptions) => void;
  disabled: boolean;
}

export function OptionsPanel({ opts, onChange, disabled }: OptionsPanelProps) {
  const isPaginated = opts.layout === "portrait" || opts.layout === "landscape";
  const isFixed = opts.layout === "preview" || opts.layout === "strip";

  function set<K extends keyof RenderOptions>(key: K, value: RenderOptions[K]) {
    let next = { ...opts, [key]: value };
    if (key === "layout") {
      const layout = value as Layout;
      if (layout === "preview" || layout === "strip") next = { ...next, format: "png" };
      if (layout !== "portrait") next = { ...next, lanes_per_page: 4 };
    }
    onChange(next);
  }

  return (
    <div className="space-y-4">
      <Row label="Profile">
        <Select
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

      <Row label="Layout">
        <Select
          testId="opt-layout"
          value={opts.layout}
          onChange={(v) => set("layout", v as Layout)}
          disabled={disabled}
          options={[
            { value: "portrait", label: "Portrait (roadbook)" },
            { value: "landscape", label: "Landscape" },
            { value: "preview", label: "Preview (full route)" },
            { value: "strip", label: "Strip (schematic)" },
          ]}
        />
      </Row>

      <Row label="Format">
        <Select
          testId="opt-format"
          value={opts.format}
          onChange={(v) => set("format", v as Format)}
          disabled={disabled || isFixed}
          options={[
            { value: "pdf", label: "PDF" },
            { value: "png", label: "PNG" },
          ]}
        />
        {isFixed && (
          <p className="text-xs text-slate-400 mt-1">PNG only for this layout</p>
        )}
      </Row>

      {isPaginated && (
        <Row label="Paper">
          <Select
            testId="opt-paper"
            value={opts.paper}
            onChange={(v) => set("paper", v as Paper)}
            disabled={disabled}
            options={[
              { value: "letter", label: "Letter (8.5 × 11)" },
              { value: "a4", label: "A4" },
            ]}
          />
        </Row>
      )}

      {isPaginated && opts.layout === "portrait" && (
        <Row label="Lanes / page">
          <NumberInput
            testId="opt-lanes"
            value={opts.lanes_per_page}
            min={1}
            max={8}
            onChange={(v) => set("lanes_per_page", v)}
            disabled={disabled}
          />
        </Row>
      )}

      <Row label="Decisions / lane">
        <NumberInput
          value={opts.decisions_per_lane}
          min={0}
          max={99}
          onChange={(v) => set("decisions_per_lane", v)}
          disabled={disabled}
        />
        <p className="text-xs text-slate-400 mt-1">0 = auto-fit</p>
      </Row>

      <Row label="Turn style">
        <Select
          value={opts.turn_style}
          onChange={(v) => set("turn_style", v as TurnStyle)}
          disabled={disabled}
          options={[
            { value: "stylized", label: "Stylized (clearer)" },
            { value: "faithful", label: "Faithful (accurate)" },
          ]}
        />
      </Row>

      <Row label="Fuel range">
        <input
          type="number"
          min={0}
          step={10}
          value={opts.fuel_range ?? ""}
          onChange={(e) =>
            set("fuel_range", e.target.value === "" ? null : Number(e.target.value))
          }
          disabled={disabled}
          placeholder="optional (miles)"
          className="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm disabled:bg-slate-100 disabled:text-slate-400 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        />
      </Row>

      <Row label="Show branches">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={opts.show_branches}
            onChange={(e) => set("show_branches", e.target.checked)}
            disabled={disabled}
            className="w-4 h-4 accent-brand disabled:opacity-50"
          />
          <span className="text-sm text-slate-600">Show unselected turn options</span>
        </label>
      </Row>
    </div>
  );
}
