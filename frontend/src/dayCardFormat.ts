// Client-side unit formatters for the Day card tab. The /v1/daycard JSON is
// ALWAYS imperial (mi/ft/°F/mph) — the `units` param only affects the md/html
// render — so the structured cards convert here. Mirrors daycard.py `_fmt_*`.

const KM_PER_MI = 1.609344;
const M_PER_FT = 0.3048;

export function fmtDistance(miles: number, imperial: boolean): string {
  return imperial
    ? `${miles.toFixed(miles < 10 ? 1 : 0)} mi`
    : `${(miles * KM_PER_MI).toFixed(miles < 10 ? 1 : 0)} km`;
}

export function fmtElev(feet: number, imperial: boolean): string {
  return imperial
    ? `${Math.round(feet).toLocaleString()} ft`
    : `${Math.round(feet * M_PER_FT).toLocaleString()} m`;
}

export function fmtTemp(tempF: number, imperial: boolean): string {
  return imperial
    ? `${Math.round(tempF)}°F`
    : `${Math.round(((tempF - 32) * 5) / 9)}°C`;
}

export function fmtSpeed(mph: number, imperial: boolean): string {
  return imperial
    ? `${Math.round(mph)} mph`
    : `${Math.round(mph * KM_PER_MI)} kph`;
}

/**
 * HH:MM from an ISO string, honoring the string's OWN offset (the display tz the
 * backend serialized) rather than the browser's local zone — so the clock matches
 * the markdown render. Returns "" for null/unparseable input.
 */
export function fmtClock(iso: string | null): string {
  if (!iso) return "";
  const m = /T(\d{2}:\d{2})/.exec(iso);
  return m ? m[1] : "";
}

/** A duration in minutes as "2h 15m" / "45m" / "0m". */
export function fmtDuration(minutes: number | null): string {
  if (minutes == null) return "—";
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}
