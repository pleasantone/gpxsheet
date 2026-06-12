import type { AnalyzeResult, JobStatus, RenderOptions, TableFormat, TableOptions } from "./types";

const API_KEY_STORAGE = "gpxsheet-api-key";

// The path the SPA is served under (vite `base`, always trailing-slashed). Using it
// to build request URLs lets the app work when mounted under a sub-path behind a
// reverse proxy, not only at the web root.
const BASE = import.meta.env.BASE_URL;

export function getApiKey(): string {
  return localStorage.getItem(API_KEY_STORAGE) ?? "";
}

export function setApiKey(key: string): void {
  if (key) {
    localStorage.setItem(API_KEY_STORAGE, key);
  } else {
    localStorage.removeItem(API_KEY_STORAGE);
  }
}

function firstPartyToken(): string | null {
  // Server-signed token injected into this page as a <meta> tag (when the
  // deployment gates the API). A meta tag is used rather than an inline script so
  // it isn't blocked by the page's default-src 'self' CSP.
  return document.querySelector('meta[name="gpxsheet-fp"]')?.getAttribute("content") ?? null;
}

function authHeaders(): HeadersInit {
  const headers: Record<string, string> = {};
  const key = getApiKey();
  if (key) headers["X-API-Key"] = key;
  // Lets the bundled SPA call the API without a user-entered key.
  const fp = firstPartyToken();
  if (fp) headers["X-First-Party"] = fp;
  return headers;
}

/** True if `url` resolves to a different origin than the page (e.g. a presigned
 *  object-storage URL), which must be fetched without our API credentials. */
function isExternal(url: string): boolean {
  try {
    return new URL(url, location.href).origin !== location.origin;
  } catch {
    return false;
  }
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function checkResponse(res: Response): Promise<Response> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, text);
  }
  return res;
}

/** Submit a job: the GPX file plus string form fields, returning the job status. */
async function postJob(
  path: string,
  file: File,
  fields: Record<string, string>,
): Promise<JobStatus> {
  const fd = new FormData();
  fd.append("gpx", file);
  for (const [k, v] of Object.entries(fields)) fd.append(k, v);
  const res = await fetch(`${BASE}${path}`, { method: "POST", headers: authHeaders(), body: fd });
  return (await checkResponse(res)).json();
}

export function submitAnalyze(
  file: File,
  profile: string,
  fuelRange: number | null,
): Promise<JobStatus> {
  return postJob("v1/analyze", file, {
    profile,
    ...(fuelRange !== null ? { fuel_range: String(fuelRange) } : {}),
  });
}

export function submitRender(file: File, opts: RenderOptions): Promise<JobStatus> {
  return postJob("v1/render", file, {
    layout: opts.layout,
    format: opts.format,
    profile: opts.profile,
    turn_style: opts.turn_style,
    paper: opts.paper,
    lanes_per_page: String(opts.lanes_per_page),
    decisions_per_lane: String(opts.decisions_per_lane),
    show_branches: String(opts.show_branches),
    ...(opts.fuel_range !== null ? { fuel_range: String(opts.fuel_range) } : {}),
  });
}

export function submitTable(
  file: File,
  opts: TableOptions,
  format: TableFormat,
): Promise<JobStatus> {
  return postJob("v1/table", file, {
    format,
    units: opts.units,
    speed: String(opts.speed),
    coordinates: String(opts.coordinates),
    osm: String(opts.osm),
    cue: String(opts.cue),
    ...(opts.departure ? { departure: opts.departure } : {}),
    ...(opts.timezone ? { timezone: opts.timezone } : {}),
  });
}

export async function pollJob(id: string): Promise<JobStatus> {
  const res = await fetch(`${BASE}v1/jobs/${id}`, { headers: authHeaders() });
  return (await checkResponse(res)).json();
}

/** Fetch a finished job's artifact. Prefer the job's `result_url`: when it points
 *  at external (presigned) storage it is fetched WITHOUT our API key — sending the
 *  key cross-origin would both leak it and fail CORS. */
async function getResult(id: string, resultUrl?: string | null): Promise<Response> {
  const external = !!resultUrl && isExternal(resultUrl);
  const url = external ? resultUrl! : `${BASE}v1/jobs/${id}/result`;
  return checkResponse(await fetch(url, external ? undefined : { headers: authHeaders() }));
}

export async function fetchResultBlob(id: string, resultUrl?: string | null): Promise<Blob> {
  return (await getResult(id, resultUrl)).blob();
}

export async function fetchResultJson(
  id: string,
  resultUrl?: string | null,
): Promise<AnalyzeResult> {
  return JSON.parse(await (await getResult(id, resultUrl)).text()) as AnalyzeResult;
}
