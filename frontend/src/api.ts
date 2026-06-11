import type { AnalyzeResult, JobStatus, RenderOptions } from "./types";

const API_KEY_STORAGE = "gpxsheet-api-key";

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

function authHeaders(): HeadersInit {
  const key = getApiKey();
  return key ? { "X-API-Key": key } : {};
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

export async function submitAnalyze(
  file: File,
  profile: string,
  fuelRange: number | null,
): Promise<JobStatus> {
  const fd = new FormData();
  fd.append("gpx", file);
  fd.append("profile", profile);
  if (fuelRange !== null) fd.append("fuel_range", String(fuelRange));
  const res = await fetch("/v1/analyze", {
    method: "POST",
    headers: authHeaders(),
    body: fd,
  });
  return (await checkResponse(res)).json();
}

export async function submitRender(
  file: File,
  opts: RenderOptions,
): Promise<JobStatus> {
  const fd = new FormData();
  fd.append("gpx", file);
  fd.append("layout", opts.layout);
  fd.append("format", opts.format);
  fd.append("profile", opts.profile);
  fd.append("turn_style", opts.turn_style);
  fd.append("paper", opts.paper);
  fd.append("lanes_per_page", String(opts.lanes_per_page));
  fd.append("decisions_per_lane", String(opts.decisions_per_lane));
  fd.append("show_branches", String(opts.show_branches));
  if (opts.fuel_range !== null) fd.append("fuel_range", String(opts.fuel_range));
  const res = await fetch("/v1/render", {
    method: "POST",
    headers: authHeaders(),
    body: fd,
  });
  return (await checkResponse(res)).json();
}

export async function pollJob(id: string): Promise<JobStatus> {
  const res = await fetch(`/v1/jobs/${id}`, { headers: authHeaders() });
  return (await checkResponse(res)).json();
}

export async function fetchResultBlob(id: string): Promise<Blob> {
  const res = await fetch(`/v1/jobs/${id}/result`, { headers: authHeaders() });
  return (await checkResponse(res)).blob();
}

export async function fetchResultJson(id: string): Promise<AnalyzeResult> {
  const blob = await fetchResultBlob(id);
  return JSON.parse(await blob.text()) as AnalyzeResult;
}
