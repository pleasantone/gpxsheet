import type { AnalyzeResult } from "../types";

interface RouteInfoProps {
  result: AnalyzeResult | null;
  isLoading: boolean;
  error: string | null;
  fuelRange: number | null;
}

export function RouteInfo({ result, isLoading, error, fuelRange }: RouteInfoProps) {
  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        Analysis failed: {error}
      </div>
    );
  }

  if (isLoading || !result) {
    return (
      <div className="flex gap-3 animate-pulse">
        <div className="h-16 flex-1 rounded-xl bg-slate-200" />
        <div className="h-16 flex-1 rounded-xl bg-slate-200" />
        <div className="h-16 flex-1 rounded-xl bg-slate-200" />
      </div>
    );
  }

  const cards = [
    { label: "Distance", value: `${result.length_miles.toFixed(1)} mi` },
    { label: "Turns", value: String(result.decision_points.length) },
    {
      label: "Fuel stops",
      value: result.fuel_stops.length
        ? String(result.fuel_stops.length)
        : "none found",
    },
  ];

  return (
    <div className="space-y-2">
      <h2 data-testid="route-name" className="text-lg font-semibold text-slate-800 truncate">{result.name}</h2>
      <div data-testid="route-stats" className="flex gap-3">
        {cards.map((c) => (
          <div key={c.label} className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{c.label}</p>
            <p className="text-base font-bold text-slate-800 mt-0.5">{c.value}</p>
          </div>
        ))}
      </div>
      <FuelGapNotice gapMiles={result.longest_fuel_gap_miles} fuelRange={fuelRange} />
    </div>
  );
}

function FuelGapNotice({
  gapMiles,
  fuelRange,
}: {
  gapMiles: number | null;
  fuelRange: number | null;
}) {
  if (gapMiles == null) return null;

  // Fuel range set and exceeded → a real warning.
  if (fuelRange != null && gapMiles > fuelRange) {
    return (
      <p className="text-xs text-amber-800 bg-amber-50 border border-amber-300 rounded-lg px-3 py-2">
        ⚠ Longest fuel gap {gapMiles.toFixed(0)} mi exceeds your fuel range of{" "}
        {fuelRange.toFixed(0)} mi
      </p>
    );
  }

  // No fuel range set and the gap is notable → informational nudge (not a warning).
  if (fuelRange == null && gapMiles > 100) {
    return (
      <p className="text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
        ℹ Longest fuel gap: {gapMiles.toFixed(0)} mi — consider setting your fuel range
      </p>
    );
  }

  return null;
}
