import type { ReactNode } from "react";

export interface StatCard {
  label: string;
  value: string;
}

// At-a-glance route header shared by Sheet (RouteInfo) and Table (TableInfo) modes:
// a route name plus a row of stat cards, with a pulse skeleton while loading.
export function SummaryCards({
  testId,
  name,
  cards,
  loading,
  skeletonCount = 3,
  children,
}: {
  testId: string;
  name: string | null;
  cards: StatCard[];
  loading: boolean;
  skeletonCount?: number;
  children?: ReactNode;
}) {
  if (loading) {
    return (
      <div className="flex gap-3 animate-pulse">
        {Array.from({ length: skeletonCount }).map((_, i) => (
          <div key={i} className="h-16 flex-1 rounded-xl bg-slate-200" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {name && (
        <h2
          data-testid={`${testId}-name`}
          className="text-lg font-semibold text-slate-800 truncate"
        >
          {name}
        </h2>
      )}
      <div data-testid={`${testId}-stats`} className="flex gap-3">
        {cards.map((c) => (
          <div
            key={c.label}
            className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"
          >
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">{c.label}</p>
            <p className="text-base font-bold text-slate-800 mt-0.5">{c.value}</p>
          </div>
        ))}
      </div>
      {children}
    </div>
  );
}
