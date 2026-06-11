// An at-a-glance header for Table mode, mirroring RouteInfo in Sheet mode. It is
// derived entirely from GPXtable's own markdown (offline — no OSM/analyze), so it
// stays consistent with the table the user sees.

interface TableInfoProps {
  markdown: string | null;
  loading: boolean;
}

export interface TableSummary {
  name: string | null;
  distance: string | null; // e.g. "13 mi" — as GPXtable formatted it
  stops: number; // table data rows (waypoints/route points shown)
}

export function parseTableSummary(md: string): TableSummary {
  const name = /^##\s+(?:Route|Track):\s*(.+?)\s*$/m.exec(md)?.[1] ?? null;
  const distance = /^\*\s*Total distance:\s*(.+?)\s*$/m.exec(md)?.[1] ?? null;
  // Data rows are table lines that aren't the header ("Name …") or the "---" rule.
  const stops = md
    .split("\n")
    .filter((l) => l.startsWith("|") && !l.includes("---") && !/\|\s*Name\s*\|/.test(l))
    .length;
  return { name, distance, stops };
}

export function TableInfo({ markdown, loading }: TableInfoProps) {
  if (loading || !markdown) {
    return (
      <div className="flex gap-3 animate-pulse">
        <div className="h-16 flex-1 rounded-xl bg-slate-200" />
        <div className="h-16 flex-1 rounded-xl bg-slate-200" />
      </div>
    );
  }

  const { name, distance, stops } = parseTableSummary(markdown);
  const cards = [
    { label: "Distance", value: distance ?? "—" },
    { label: "Stops", value: String(stops) },
  ];

  return (
    <div className="space-y-2">
      {name && (
        <h2 data-testid="table-name" className="text-lg font-semibold text-slate-800 truncate">
          {name}
        </h2>
      )}
      <div data-testid="table-stats" className="flex gap-3">
        {cards.map((c) => (
          <div key={c.label} className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{c.label}</p>
            <p className="text-base font-bold text-slate-800 mt-0.5">{c.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
