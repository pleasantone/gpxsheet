// At-a-glance header for Table mode (parity with RouteInfo). Computed from the
// structured JSON — correct for multi-day routes (the old markdown-scraping
// summary showed no name/distance for multi-`<trk>` routes and overcounted stops
// by sweeping in cue rows + the double-counted day-boundary waypoint).
import { fmtDist } from "../tableFormat";
import type { TableDocData, Units } from "../types";
import { SummaryCards } from "./SummaryCards";

interface TableInfoProps {
  data: TableDocData | null;
  units: Units;
  loading: boolean;
}

export function TableInfo({ data, units, loading }: TableInfoProps) {
  const imperial = units === "imperial";
  const cards = data
    ? [
        ...(data.sections.length > 1
          ? [{ label: "Days", value: String(data.sections.length) }]
          : []),
        {
          label: "Distance",
          value: fmtDist(
            data.sections.reduce((sum, s) => sum + s.distance_mi, 0),
            imperial,
          ),
        },
        { label: "Stops", value: String(countStops(data)) },
      ]
    : [];

  return (
    <SummaryCards
      testId="table"
      name={data?.name ?? null}
      cards={cards}
      loading={loading || !data}
      skeletonCount={2}
    />
  );
}

// Total waypoint/fuel rows, not double-counting a stop that sits on a day
// boundary (it appears in both adjacent day sections by design).
function countStops(data: TableDocData): number {
  if (data.sections.length === 1) return data.sections[0].rows.length;
  const seen = new Set<string>();
  for (const sec of data.sections) {
    for (const r of sec.rows) seen.add(`${r.name}@${r.lat.toFixed(4)},${r.lon.toFixed(4)}`);
  }
  return seen.size;
}
