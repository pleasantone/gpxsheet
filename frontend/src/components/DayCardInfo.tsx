// At-a-glance header for Day card mode (parity with RouteInfo / TableInfo).
// Derived from the structured /v1/daycard JSON: day count, total distance, and
// total warning count across all days.
import { fmtDistance } from "../dayCardFormat";
import type { DayCardData } from "../types";
import { SummaryCards } from "./SummaryCards";

interface DayCardInfoProps {
  data: DayCardData[] | null;
  imperial: boolean;
  loading: boolean;
}

export function DayCardInfo({ data, imperial, loading }: DayCardInfoProps) {
  const cards = data
    ? [
        { label: "Days", value: String(data.length) },
        {
          label: "Distance",
          value: fmtDistance(
            data.reduce((sum, d) => sum + d.miles, 0),
            imperial,
          ),
        },
        {
          label: "Warnings",
          value: String(data.reduce((sum, d) => sum + d.warnings.length, 0)),
        },
      ]
    : [];

  return (
    <SummaryCards
      testId="daycard"
      name={data && data.length > 0 ? data[0].name : null}
      cards={cards}
      loading={loading || !data}
      skeletonCount={3}
    />
  );
}
