import { useEffect, useRef, useState } from "react";
import { fetchResultJson, submitAnalyze, submitRender } from "./api";
import { DropZone } from "./components/DropZone";
import { JobProgress } from "./components/JobProgress";
import { OptionsPanel } from "./components/OptionsPanel";
import { ResultPane } from "./components/ResultPane";
import { RouteInfo } from "./components/RouteInfo";
import { SettingsPopover } from "./components/SettingsPopover";
import { useJobPoll } from "./hooks/useJobPoll";
import type { AnalyzeResult, RenderOptions } from "./types";
import { DEFAULT_OPTIONS } from "./types";

type Phase = "idle" | "ready";

interface ReadyState {
  file: File;
  analyzeJobId: string | null;
  analyzeResult: AnalyzeResult | null;
  previewJobId: string | null;
  renderJobId: string | null;
  renderFilename: string | null;
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [opts, setOpts] = useState<RenderOptions>(DEFAULT_OPTIONS);
  const [ready, setReady] = useState<ReadyState | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  // Polling hooks
  const analyzeJobId = ready?.analyzeJobId ?? null;
  const previewJobId = ready?.previewJobId ?? null;
  const renderJobId = ready?.renderJobId ?? null;

  const { jobStatus: analyzeStatus, isPolling: analyzePolling, error: analyzeError } =
    useJobPoll(analyzeJobId);
  const { jobStatus: previewStatus, resultBlob: previewBlob, isPolling: previewPolling, error: previewError } =
    useJobPoll(previewJobId, true);
  const { jobStatus: renderStatus, resultBlob: renderBlob, isPolling: renderPolling, error: renderError } =
    useJobPoll(renderJobId, true);

  // Fetch analyze JSON once the analyze job is done
  const analyzeJobDone = analyzeStatus?.status === "done";
  const analyzeJobIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!analyzeJobDone || !analyzeJobId || analyzeJobId === analyzeJobIdRef.current) return;
    analyzeJobIdRef.current = analyzeJobId;
    fetchResultJson(analyzeJobId)
      .then((result) =>
        setReady((prev) => (prev ? { ...prev, analyzeResult: result } : prev))
      )
      .catch(() => {});
  }, [analyzeJobDone, analyzeJobId]);

  // Blob URLs — created once per blob, revoked on change
  const previewBlobUrl = useBlobUrl(previewBlob);
  const renderBlobUrl = useBlobUrl(renderBlob);

  function handleFile(file: File) {
    setSubmitError(null);
    setIsGenerating(false);
    // Seed ready state immediately so the UI transitions to the ready phase.
    // analyzeJobId and previewJobId are filled in as each request completes.
    setReady({
      file,
      analyzeJobId: null,
      analyzeResult: null,
      previewJobId: null,
      renderJobId: null,
      renderFilename: null,
    });
    setPhase("ready");

    submitAnalyze(file, opts.profile, opts.fuel_range)
      .then((job) =>
        setReady((prev) => (prev ? { ...prev, analyzeJobId: job.id } : prev))
      )
      .catch((e) => setSubmitError(e instanceof Error ? e.message : "analyze failed"));

    submitRender(file, { ...opts, layout: "preview", format: "png" })
      .then((job) =>
        setReady((prev) => (prev ? { ...prev, previewJobId: job.id } : prev))
      )
      .catch(() => {});
  }

  async function handleGenerate() {
    if (!ready) return;
    setIsGenerating(true);
    setSubmitError(null);
    setReady((prev) => (prev ? { ...prev, renderJobId: null, renderFilename: null } : prev));

    try {
      const job = await submitRender(ready.file, opts);
      const ext = opts.format === "pdf" ? "pdf" : "png";
      const baseName = ready.analyzeResult?.name ?? ready.file.name.replace(/\.gpx$/i, "");
      const filename = `${baseName}.${ext}`;
      setReady((prev) =>
        prev ? { ...prev, renderJobId: job.id, renderFilename: filename } : prev
      );
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "generate failed");
      setIsGenerating(false);
    }
  }

  // Stop generating spinner once render is done or errored
  useEffect(() => {
    if (renderStatus?.status === "done" || renderStatus?.status === "error" || renderError) {
      setIsGenerating(false);
    }
  }, [renderStatus, renderError]);

  const generating = isGenerating || renderPolling;

  if (phase === "idle") {
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 flex items-center justify-center px-4 py-12">
          <div className="w-full max-w-lg">
            <DropZone onFile={handleFile} />
            {submitError && (
              <p className="mt-3 text-sm text-red-600 text-center">{submitError}</p>
            )}
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header>
        {ready && <DropZone onFile={handleFile} compact />}
      </Header>
      <main className="flex-1 px-4 py-6 max-w-5xl mx-auto w-full">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-6">
          {/* Left: preview + progress */}
          <div className="space-y-4">
            <RouteInfo
              result={ready?.analyzeResult ?? null}
              isLoading={analyzePolling || (!!analyzeJobId && !ready?.analyzeResult)}
              error={analyzeError}
            />

            <ResultPane
              previewBlobUrl={previewBlobUrl}
              previewLoading={previewPolling}
              renderBlobUrl={renderBlobUrl}
              renderFilename={ready?.renderFilename ?? null}
              renderContentType={renderStatus?.content_type ?? null}
            />

            <div className="space-y-1">
              <JobProgress
                label="Preview"
                isPolling={previewPolling}
                jobStatus={previewStatus}
                error={previewError}
              />
              <JobProgress
                label="Generating"
                isPolling={renderPolling}
                jobStatus={renderStatus}
                error={renderError}
              />
              {submitError && (
                <p className="text-sm text-red-600">{submitError}</p>
              )}
            </div>
          </div>

          {/* Right: options + generate */}
          <div className="space-y-4">
            <OptionsPanel opts={opts} onChange={setOpts} disabled={generating} />
            <button
              data-testid="btn-generate"
              onClick={handleGenerate}
              disabled={generating || !ready}
              className="w-full rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {generating ? "Generating…" : "Generate"}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}

function Header({ children }: { children?: React.ReactNode }) {
  return (
    <header className="border-b border-slate-200 bg-white px-4 py-3 flex items-center gap-3">
      <span className="text-lg font-bold text-brand tracking-tight">GPXSheet</span>
      <span className="text-xs text-slate-400 hidden sm:block">
        GPX → motorcycle navigation PDFs
      </span>
      <div className="ml-auto flex items-center gap-3">
        {children}
        <SettingsPopover />
      </div>
    </header>
  );
}

function useBlobUrl(blob: Blob | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) { setUrl(null); return; }
    const u = URL.createObjectURL(blob);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [blob]);
  return url;
}
