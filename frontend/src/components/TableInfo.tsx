// At-a-glance header for Table mode (parity with RouteInfo). Derived entirely from
// GPXtable's own markdown — offline, no OSM/analyze — so it matches the table shown.
import { parseTableSummary } from "../tableSummary";
import { SummaryCards } from "./SummaryCards";

interface TableInfoProps {
  markdown: string | null;
  loading: boolean;
}

export function TableInfo({ markdown, loading }: TableInfoProps) {
  const summary = markdown ? parseTableSummary(markdown) : null;
  const cards = summary
    ? [
        { label: "Distance", value: summary.distance ?? "—" },
        { label: "Stops", value: String(summary.stops) },
      ]
    : [];

  return (
    <SummaryCards
      testId="table"
      name={summary?.name ?? null}
      cards={cards}
      loading={loading || !markdown}
      skeletonCount={2}
    />
  );
}
