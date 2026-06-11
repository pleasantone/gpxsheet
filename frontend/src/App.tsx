import { useEffect, useRef, useState } from "react";
import { fetchResultJson, submitAnalyze, submitRender, submitTable } from "./api";
import { DropZone } from "./components/DropZone";
import { JobProgress } from "./components/JobProgress";
import { OptionsPanel } from "./components/OptionsPanel";
import { ResultPane } from "./components/ResultPane";
import { RouteInfo } from "./components/RouteInfo";
import { SettingsPopover } from "./components/SettingsPopover";
import { TableInfo } from "./components/TableInfo";
import { TableOptionsPanel } from "./components/TableOptionsPanel";
import { TableResultPane } from "./components/TableResultPane";
import { gpxStartLocal } from "./gpxMeta";
import { useJobPoll } from "./hooks/useJobPoll";
import type { AnalyzeResult, Mode, RenderOptions, TableOptions } from "./types";
import { DEFAULT_OPTIONS, DEFAULT_TABLE_OPTIONS } from "./types";

type Phase = "idle" | "ready";

interface ReadyState {
  file: File;
  // sheet flow
  analyzeJobId: string | null;
  analyzeResult: AnalyzeResult | null;
  previewJobId: string | null;
  renderJobId: string | null;
  renderFilename: string | null;
  // table flow
  tableHtmlJobId: string | null;
  tableMdJobId: string | null;
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [mode, setMode] = useState<Mode>("sheet");
  const [opts, setOpts] = useState<RenderOptions>(DEFAULT_OPTIONS);
  const [tableOpts, setTableOpts] = useState<TableOptions>(DEFAULT_TABLE_OPTIONS);
  const [ready, setReady] = useState<ReadyState | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  // Polling hooks
  const analyzeJobId = ready?.analyzeJobId ?? null;
  const previewJobId = ready?.previewJobId ?? null;
  const renderJobId = ready?.renderJobId ?? null;
  const tableHtmlJobId = ready?.tableHtmlJobId ?? null;
  const tableMdJobId = ready?.tableMdJobId ?? null;

  const { jobStatus: analyzeStatus, isPolling: analyzePolling, error: analyzeError } =
    useJobPoll(analyzeJobId);
  const { resultBlob: previewBlob, isPolling: previewPolling, jobStatus: previewStatus, error: previewError } =
    useJobPoll(previewJobId, true);
  const { jobStatus: renderStatus, resultBlob: renderBlob, isPolling: renderPolling, error: renderError } =
    useJobPoll(renderJobId, true);
  const {
    resultBlob: tableHtmlBlob,
    isPolling: tableHtmlPolling,
    jobStatus: tableHtmlStatus,
    error: tableHtmlError,
  } = useJobPoll(tableHtmlJobId, true);
  const { resultBlob: tableMdBlob } = useJobPoll(tableMdJobId, true);

  // Fetch analyze JSON once the analyze job is done
  const analyzeJobDone = analyzeStatus?.status === "done";
  const analyzeJobIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!analyzeJobDone || !analyzeJobId || analyzeJobId === analyzeJobIdRef.current) return;
    analyzeJobIdRef.current = analyzeJobId;
    fetchResultJson(analyzeJobId, analyzeStatus?.result_url)
      .then((result) =>
        setReady((prev) => (prev ? { ...prev, analyzeResult: result } : prev))
      )
      .catch(() => {});
  }, [analyzeJobDone, analyzeJobId, analyzeStatus?.result_url]);

  // Blob URLs / text — derived from poll results
  const previewBlobUrl = useBlobUrl(previewBlob);
  const renderBlobUrl = useBlobUrl(renderBlob);
  const tableHtml = useBlobText(tableHtmlBlob);
  const tableMarkdown = useBlobText(tableMdBlob);

  // Kick off the jobs for a given mode (used on file drop, tab switch, generate).
  function runSheet(file: File) {
    submitAnalyze(file, opts.profile, opts.fuel_range)
      .then((job) => setReady((prev) => (prev ? { ...prev, analyzeJobId: job.id } : prev)))
      .catch((e) => setSubmitError(e instanceof Error ? e.message : "analyze failed"));
    submitRender(file, { ...opts, layout: "preview", format: "png" })
      .then((job) => setReady((prev) => (prev ? { ...prev, previewJobId: job.id } : prev)))
      .catch(() => {});
  }

  function runTable(file: File, tblOpts: TableOptions) {
    setReady((prev) => (prev ? { ...prev, tableHtmlJobId: null, tableMdJobId: null } : prev));
    submitTable(file, tblOpts, "html")
      .then((job) => setReady((prev) => (prev ? { ...prev, tableHtmlJobId: job.id } : prev)))
      .catch((e) => setSubmitError(e instanceof Error ? e.message : "table failed"));
    submitTable(file, tblOpts, "markdown")
      .then((job) => setReady((prev) => (prev ? { ...prev, tableMdJobId: job.id } : prev)))
      .catch(() => {});
  }

  // Table mode is cheap + offline, so it regenerates live (debounced) whenever the
  // file or any table option changes — no need to press Generate to see e.g. a new
  // departure time. (Sheet rendering stays manual; it's matplotlib/OSM heavy.)
  useEffect(() => {
    if (mode !== "table" || !ready?.file) return;
    const file = ready.file;
    const id = setTimeout(() => runTable(file, tableOpts), 400);
    return () => clearTimeout(id);
  }, [mode, ready?.file, tableOpts]);

  function handleFile(file: File) {
    setSubmitError(null);
    setIsGenerating(false);
    // Allow the analyze result to be refetched even if a re-upload dedupes to the
    // same job id (otherwise the ref guard would skip the refetch after the reset).
    analyzeJobIdRef.current = null;
    setReady({
      file,
      analyzeJobId: null,
      analyzeResult: null,
      previewJobId: null,
      renderJobId: null,
      renderFilename: null,
      tableHtmlJobId: null,
      tableMdJobId: null,
    });
    setPhase("ready");
    // Prefill the Table departure from the GPX's first track/route point time so the
    // box and the rendered table agree. If the GPX has no point times, keep whatever
    // is already in the box (don't clear it).
    gpxStartLocal(file).then((dep) => {
      if (dep) setTableOpts((prev) => ({ ...prev, departure: dep }));
    });
    if (mode === "sheet") runSheet(file); // table mode regenerates via the effect
  }

  function switchMode(m: Mode) {
    if (m === mode) return;
    setMode(m);
    setSubmitError(null);
    // Sheet needs its analyze + preview kicked off; table regenerates via the effect.
    if (m === "sheet" && ready?.file && !ready.analyzeJobId) runSheet(ready.file);
  }

  async function handleGenerate() {
    if (!ready) return; // sheet-only: the table view regenerates live (no button)
    setSubmitError(null);
    setIsGenerating(true);
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

  // Stop the sheet generating spinner once render is done or errored
  useEffect(() => {
    if (renderStatus?.status === "done" || renderStatus?.status === "error" || renderError) {
      setIsGenerating(false);
    }
  }, [renderStatus, renderError]);

  const sheetGenerating = isGenerating || renderPolling;
  const tableGenerating = tableHtmlPolling || (!!tableHtmlJobId && !tableHtml && !tableHtmlError);
  const generating = mode === "table" ? tableGenerating : sheetGenerating;

  if (phase === "idle") {
    return (
      <div className="min-h-screen flex flex-col overflow-x-hidden">
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
    <div className="min-h-screen flex flex-col overflow-x-hidden">
      <Header />
      <main className="flex-1 px-4 py-6 max-w-5xl mx-auto w-full space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <ModeTabs mode={mode} onChange={switchMode} disabled={generating} />
          <div className="w-full sm:w-auto sm:min-w-[280px]">
            <DropZone onFile={handleFile} compact />
          </div>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-6">
          {/* Left: result + progress */}
          <div className="space-y-4">
            {mode === "sheet" ? (
              <>
                <RouteInfo
                  result={ready?.analyzeResult ?? null}
                  isLoading={analyzePolling || (!!analyzeJobId && !ready?.analyzeResult)}
                  error={analyzeError}
                  fuelRange={opts.fuel_range}
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
                  {submitError && <p className="text-sm text-red-600">{submitError}</p>}
                </div>
              </>
            ) : (
              <>
                <TableInfo markdown={tableMarkdown} loading={tableGenerating} />
                <TableResultPane
                  html={tableHtml}
                  markdown={tableMarkdown}
                  loading={tableGenerating}
                  error={tableHtmlError}
                />
                <JobProgress
                  label="Table"
                  isPolling={tableHtmlPolling}
                  jobStatus={tableHtmlStatus}
                  error={tableHtmlError}
                />
                {submitError && <p className="text-sm text-red-600">{submitError}</p>}
              </>
            )}
          </div>

          {/* Right: options + generate */}
          <div className="space-y-4">
            {mode === "sheet" ? (
              <OptionsPanel opts={opts} onChange={setOpts} disabled={generating} />
            ) : (
              <TableOptionsPanel opts={tableOpts} onChange={setTableOpts} disabled={generating} />
            )}
            {/* Sheet rendering is manual; the table regenerates live, so it has no button. */}
            {mode === "sheet" && (
              <button
                data-testid="btn-generate"
                onClick={handleGenerate}
                disabled={generating || !ready}
                className="w-full rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {generating ? "Generating…" : "Generate"}
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

function ModeTabs({
  mode,
  onChange,
  disabled,
}: {
  mode: Mode;
  onChange: (m: Mode) => void;
  disabled: boolean;
}) {
  const tabs: { value: Mode; label: string }[] = [
    { value: "sheet", label: "Sheet" },
    { value: "table", label: "Table" },
  ];
  return (
    <div className="inline-flex rounded-xl border border-slate-200 bg-slate-100 p-1">
      {tabs.map((t) => (
        <button
          key={t.value}
          data-testid={`tab-${t.value}`}
          onClick={() => onChange(t.value)}
          disabled={disabled}
          className={`px-4 py-1.5 text-sm font-semibold rounded-lg transition-colors disabled:cursor-not-allowed ${
            mode === t.value
              ? "bg-white text-brand shadow-sm"
              : "text-slate-500 hover:text-slate-700"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

function Header({ children }: { children?: React.ReactNode }) {
  return (
    <header className="border-b border-slate-200 bg-white px-4 py-3 flex items-center gap-3">
      <img src={`${import.meta.env.BASE_URL}icon.svg`} alt="" className="w-7 h-7 rounded" />
      <span className="text-lg font-bold text-brand tracking-tight">GPXSheet</span>
      <span className="text-xs text-slate-400 hidden sm:block">
        GPX → your navigation buddy
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

function useBlobText(blob: Blob | null): string | null {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) { setText(null); return; }
    let cancelled = false;
    blob.text().then((t) => { if (!cancelled) setText(t); });
    return () => { cancelled = true; };
  }, [blob]);
  return text;
}
