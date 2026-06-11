import type { JobStatus } from "../types";

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
    return (
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Spinner />
        <span>{label}…</span>
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

function Spinner() {
  return (
    <svg
      className="w-4 h-4 animate-spin text-brand shrink-0"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}
