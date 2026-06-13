import type { AnalyzeResult } from "../types";
import { SummaryCards } from "./SummaryCards";

// Below this gap, with no fuel range set, we don't even nudge — most bikes clear it.
const FUEL_GAP_NUDGE_MILES = 100;

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

  const cards = result
    ? [
        { label: "Distance", value: `${result.length_miles.toFixed(1)} mi` },
        // decision_points are turns + forks + roundabouts, not just turns.
        { label: "Decisions", value: String(result.decision_points.length) },
        {
          label: "Fuel stops",
          value: result.fuel_stops.length ? String(result.fuel_stops.length) : "none found",
        },
      ]
    : [];

  return (
    <SummaryCards
      testId="route"
      name={result?.name ?? null}
      cards={cards}
      loading={isLoading || !result}
      skeletonCount={3}
    >
      <FuelGapNotice gapMiles={result?.longest_fuel_gap_miles ?? null} fuelRange={fuelRange} />
    </SummaryCards>
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
  if (fuelRange == null && gapMiles > FUEL_GAP_NUDGE_MILES) {
    return (
      <p className="text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
        ℹ Longest fuel gap: {gapMiles.toFixed(0)} mi — consider setting your fuel range
      </p>
    );
  }

  return null;
}
