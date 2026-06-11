// Lightweight, offline GPX metadata helpers for the SPA (no backend round-trip).

/** Format a Date as a `datetime-local` input value in the browser's local zone. */
function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

/**
 * The GPX's start time as a `datetime-local` string, or null if no track/route
 * point carries a timestamp.
 *
 * Uses the first **track-point or route-point** `<time>` (the departure/arrival of
 * the first point) — NOT the file-level `<metadata><time>`, which is just when the
 * GPX was created. Returning null tells the caller to keep the box's current value.
 */
export async function gpxStartLocal(file: File): Promise<string | null> {
  let text: string;
  try {
    text = await file.text();
  } catch {
    return null;
  }
  const doc = new DOMParser().parseFromString(text, "application/xml");
  if (doc.getElementsByTagName("parsererror").length) return null;

  // getElementsByTagNameNS("*", …) matches by localName regardless of the GPX
  // default namespace. Track points first, then route points; first timed point wins.
  for (const tag of ["trkpt", "rtept"]) {
    const pts = doc.getElementsByTagNameNS("*", tag);
    for (let i = 0; i < pts.length; i++) {
      const t = pts[i].getElementsByTagNameNS("*", "time")[0]?.textContent?.trim();
      if (t) {
        const d = new Date(t);
        if (!Number.isNaN(d.getTime())) return toLocalInput(d);
      }
    }
  }
  return null;
}
