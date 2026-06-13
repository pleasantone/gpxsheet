// Client-side formatters for the Table tab. The /v1/table JSON is ALWAYS
// imperial (miles / mph); the `units` toggle converts in-browser. Datetimes are
// ISO 8601 carrying their display-tz offset, so clocks are read from the string.

const KM_PER_MI = 1.609344;

/** Integer distance with unit (mirrors the old table's whole-mile rounding). */
export function fmtDist(miles: number, imperial: boolean): string {
  return imperial
    ? `${Math.round(miles)} mi`
    : `${Math.round(miles * KM_PER_MI)} km`;
}

/** Bare integer distance, no unit (for the Dist. column cells). */
export function fmtDistBare(miles: number, imperial: boolean): string {
  return String(Math.round(imperial ? miles : miles * KM_PER_MI));
}

/** Average speed, one decimal dropped to a clean integer ("avg 32 mph"). */
export function fmtSpeed(mph: number, imperial: boolean): string {
  return imperial
    ? `${Math.round(mph)} mph`
    : `${Math.round(mph * KM_PER_MI)} km/h`;
}

/** HH:MM from an ISO string, honoring the string's own offset; "" when null. */
export function fmtClock(iso: string | null): string {
  if (!iso) return "";
  const m = /T(\d{2}:\d{2})/.exec(iso);
  return m ? m[1] : "";
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** A friendly departure label like "9:00 AM, Jun 12" from an ISO string. */
export function fmtDeparture(iso: string | null): string | null {
  if (!iso) return null;
  const m = /(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  if (!m) return null;
  const [, , mo, d, hh, mm] = m;
  const hour = Number(hh);
  const ampm = hour < 12 ? "AM" : "PM";
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${h12}:${mm} ${ampm}, ${MONTHS[Number(mo) - 1]} ${Number(d)}`;
}

/** A layover suffix like " (+15m)" / " (+1h30m)", or "" when zero. */
export function fmtLayover(minutes: number): string {
  if (!minutes) return "";
  const h = Math.floor(minutes / 60);
  const mm = minutes % 60;
  const body = h > 0 ? `${h}h${mm ? `${mm}m` : ""}` : `${mm}m`;
  return ` (+${body})`;
}

/** The Dist. cell: cumulative mile, or "since-gas/total" on fuel/last rows
 *  (matches the old table's overloaded column). */
export function fmtDistCell(
  mileMi: number,
  sinceGasMi: number,
  imperial: boolean,
  split: boolean,
): string {
  if (split) {
    return `${fmtDistBare(sinceGasMi, imperial)}/${fmtDistBare(mileMi, imperial)}`;
  }
  return fmtDistBare(mileMi, imperial);
}

/** "37.4210,-122.0810" coordinate label (4 dp, mirrors the old Lat,Lon column). */
export function fmtLatLon(lat: number, lon: number): string {
  return `${lat.toFixed(4)},${lon.toFixed(4)}`;
}
