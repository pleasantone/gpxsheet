export interface TableSummary {
  name: string | null;
  distance: string | null; // e.g. "13 mi" — as GPXtable formatted it
  stops: number; // table data rows (waypoints/route points shown)
}

/** Parse GPXtable's markdown header/table into an at-a-glance summary (offline). */
export function parseTableSummary(md: string): TableSummary {
  const name = /^##\s+(?:Route|Track):\s*(.+?)\s*$/m.exec(md)?.[1] ?? null;
  const distance = /^\*\s*Total distance:\s*(.+?)\s*$/m.exec(md)?.[1] ?? null;
  // Data rows are table lines that aren't the header ("Name …") or the "---" rule.
  const stops = md
    .split("\n")
    .filter((l) => l.startsWith("|") && !l.includes("---") && !/\|\s*Name\s*\|/.test(l)).length;
  return { name, distance, stops };
}
