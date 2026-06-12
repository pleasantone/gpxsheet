import type { JobStatus } from "../types";
import { Spinner } from "./Spinner";

interface JobProgressProps {
  label: string;
  isPolling: boolean;
  jobStatus: JobStatus | null;
  error: string | null;
}

export function JobProgress({ label, isPolling, jobStatus, error }: JobProgressProps) {
  if (!isPolling && !jobStatus && !error) return null;

  if (error) {
    return (
      <div className="flex items-center gap-2 text-sm text-red-600">
        <span className="shrink-0">✗</span>
        <span>
          {label}: {error}
        </span>
      </div>
    );
  }

  if (isPolling || jobStatus?.status === "queued" || jobStatus?.status === "running") {
    const ahead = jobStatus?.queue_position ?? 0;
    const queued = jobStatus?.status === "queued" && ahead > 0;
    return (
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Spinner className="w-4 h-4 text-brand shrink-0" />
        <span>
          {label}…
          {queued && (
            <span className="text-slate-400">
              {" "}
              waiting — {ahead} {ahead === 1 ? "job" : "jobs"} ahead
            </span>
          )}
        </span>
      </div>
    );
  }

  if (jobStatus?.status === "done") {
    return (
      <div className="flex items-center gap-2 text-sm text-green-600">
        <span className="shrink-0">✓</span>
        <span>{label} ready</span>
      </div>
    );
  }

  return null;
}
