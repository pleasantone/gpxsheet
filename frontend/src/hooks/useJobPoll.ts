import { useEffect, useRef, useState } from "react";
import { fetchResultBlob, pollJob } from "../api";
import type { JobStatus } from "../types";

interface PollResult {
  jobStatus: JobStatus | null;
  resultBlob: Blob | null;
  error: string | null;
  isPolling: boolean;
}

export function useJobPoll(jobId: string | null, fetchBlob = false): PollResult {
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [resultBlob, setResultBlob] = useState<Blob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intervalRef = useRef(500);
  const cancelledRef = useRef(false);

  useEffect(() => {
    if (!jobId) {
      setJobStatus(null);
      setResultBlob(null);
      setError(null);
      setIsPolling(false);
      return;
    }

    cancelledRef.current = false;
    intervalRef.current = 500;
    setJobStatus(null);
    setResultBlob(null);
    setError(null);
    setIsPolling(true);

    const poll = async () => {
      if (cancelledRef.current) return;
      try {
        const s = await pollJob(jobId);
        if (cancelledRef.current) return;
        setJobStatus(s);

        if (s.status === "done") {
          setIsPolling(false);
          if (fetchBlob) {
            try {
              const blob = await fetchResultBlob(jobId, s.result_url);
              if (!cancelledRef.current) setResultBlob(blob);
            } catch (e) {
              if (!cancelledRef.current)
                setError(e instanceof Error ? e.message : "fetch failed");
            }
          }
          return;
        }

        if (s.status === "error") {
          setIsPolling(false);
          setError(s.error ?? "job failed");
          return;
        }

        intervalRef.current = Math.min(intervalRef.current * 1.5, 4000);
        timerRef.current = setTimeout(poll, intervalRef.current);
      } catch (e) {
        if (!cancelledRef.current) {
          setIsPolling(false);
          setError(e instanceof Error ? e.message : "network error");
        }
      }
    };

    timerRef.current = setTimeout(poll, intervalRef.current);

    return () => {
      cancelledRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [jobId, fetchBlob]);

  return { jobStatus, resultBlob, error, isPolling };
}
