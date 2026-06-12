import { Spinner } from "./Spinner";

// The lifecycle of one job line: the request is in flight ("submitting"), the
// server accepted it and is working ("processing", i.e. after the 202), it
// finished ("done"), or it failed ("error").
export type ProgressPhase = "submitting" | "processing" | "done" | "error";

interface JobProgressProps {
  label: string;
  phase: ProgressPhase | null;
  queuePosition?: number | null;
  error?: string | null;
}

export function JobProgress({ label, phase, queuePosition, error }: JobProgressProps) {
  if (!phase) return null;

  if (phase === "error") {
    return (
      <div className="flex items-center gap-2 text-sm text-red-600" data-testid="job-error">
        <span className="shrink-0">✗</span>
        <span>
          {label}: {error ?? "failed"}
        </span>
      </div>
    );
  }

  if (phase === "done") {
    return (
      <div className="flex items-center gap-2 text-sm text-green-600" data-testid="job-done">
        <span className="shrink-0">✓</span>
        <span>{label} ready</span>
      </div>
    );
  }

  const ahead = queuePosition ?? 0;
  const message = phase === "submitting" ? "submitting…" : "submitted — processing…";
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500" data-testid={`job-${phase}`}>
      <Spinner className="w-4 h-4 text-brand shrink-0" />
      <span>
        {label}: {message}
        {ahead > 0 && (
          <span className="text-slate-400">
            {" "}
            ({ahead} {ahead === 1 ? "job" : "jobs"} ahead)
          </span>
        )}
      </span>
    </div>
  );
}
