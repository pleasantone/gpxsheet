import { useEffect, useRef, useState } from "react";
import { fetchResultJson, submitAnalyze, submitDaycard, submitRender, submitTable } from "./api";
import { DayCardInfo } from "./components/DayCardInfo";
import { DayCardOptionsPanel } from "./components/DayCardOptionsPanel";
import { DayCardResultPane } from "./components/DayCardResultPane";
import { DropZone } from "./components/DropZone";
import { Footer } from "./components/Footer";
import { IntroGuide } from "./components/IntroGuide";
import { JobProgress, type ProgressPhase } from "./components/JobProgress";
import { OptionsPanel } from "./components/OptionsPanel";
import { ResultPane } from "./components/ResultPane";
import { RouteInfo } from "./components/RouteInfo";
import { SettingsPopover } from "./components/SettingsPopover";
import { Spinner } from "./components/Spinner";
import { TableInfo } from "./components/TableInfo";
import { TableOptionsPanel } from "./components/TableOptionsPanel";
import { TableResultPane } from "./components/TableResultPane";
import { gpxStartLocal } from "./gpxMeta";
import { useJobPoll } from "./hooks/useJobPoll";
import type {
  AnalyzeResult,
  DayCardData,
  DayCardOptions,
  Mode,
  RenderOptions,
  TableOptions,
} from "./types";
import { DEFAULT_DAYCARD_OPTIONS, DEFAULT_OPTIONS, DEFAULT_TABLE_OPTIONS } from "./types";

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
  // day card flow
  daycardJobId: string | null; // format=json (drives the cards)
  daycardMdJobId: string | null; // format=markdown (copy/download parity)
  daycardResult: DayCardData[] | null;
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [mode, setMode] = useState<Mode>("sheet");
  const [opts, setOpts] = useState<RenderOptions>(DEFAULT_OPTIONS);
  const [tableOpts, setTableOpts] = useState<TableOptions>(DEFAULT_TABLE_OPTIONS);
  const [daycardOpts, setDaycardOpts] = useState<DayCardOptions>(DEFAULT_DAYCARD_OPTIONS);
  const [ready, setReady] = useState<ReadyState | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  // True while a submit POST is in flight (uploading + waiting for the 202),
  // before a job id exists to poll — drives the "submitting…" feedback.
  const [renderSubmitting, setRenderSubmitting] = useState(false);
  const [tableSubmitting, setTableSubmitting] = useState(false);
  const [daycardSubmitting, setDaycardSubmitting] = useState(false);

  // Polling hooks
  const analyzeJobId = ready?.analyzeJobId ?? null;
  const previewJobId = ready?.previewJobId ?? null;
  const renderJobId = ready?.renderJobId ?? null;
  const tableHtmlJobId = ready?.tableHtmlJobId ?? null;
  const tableMdJobId = ready?.tableMdJobId ?? null;
  const daycardJobId = ready?.daycardJobId ?? null;
  const daycardMdJobId = ready?.daycardMdJobId ?? null;

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
  const {
    jobStatus: daycardStatus,
    isPolling: daycardPolling,
    error: daycardError,
  } = useJobPoll(daycardJobId);
  const { resultBlob: daycardMdBlob } = useJobPoll(daycardMdJobId, true);

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

  // Fetch the day-card JSON array once its job is done (mirrors the analyze effect).
  const daycardJobDone = daycardStatus?.status === "done";
  const daycardJobIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!daycardJobDone || !daycardJobId || daycardJobId === daycardJobIdRef.current) return;
    daycardJobIdRef.current = daycardJobId;
    fetchResultJson<DayCardData[]>(daycardJobId, daycardStatus?.result_url)
      .then((result) =>
        setReady((prev) => (prev ? { ...prev, daycardResult: result } : prev))
      )
      .catch(() => {});
  }, [daycardJobDone, daycardJobId, daycardStatus?.result_url]);

  // Blob URLs / text — derived from poll results
  const previewBlobUrl = useBlobUrl(previewBlob);
  const renderBlobUrl = useBlobUrl(renderBlob);
  const tableHtml = useBlobText(tableHtmlBlob);
  const tableMarkdown = useBlobText(tableMdBlob);
  const daycardMarkdown = useBlobText(daycardMdBlob);

  // Warm the (cached) analysis on upload so the first Generate is fast: the
  // backend caches analyze_core per (gpx, osm), so this OSM pass is reused by the
  // subsequent render/table. Fired in both modes.
  function warmAnalysis(file: File) {
    submitAnalyze(file, opts.profile, opts.fuel_range)
      .then((job) => setReady((prev) => (prev ? { ...prev, analyzeJobId: job.id } : prev)))
      .catch((e) => setSubmitError(e instanceof Error ? e.message : "analyze failed"));
  }

  // Sheet drop/switch: warm analysis + a live preview.
  function runSheet(file: File) {
    warmAnalysis(file);
    submitRender(file, { ...opts, layout: "preview", format: "png" })
      .then((job) => setReady((prev) => (prev ? { ...prev, previewJobId: job.id } : prev)))
      .catch(() => {});
  }

  function runTable(file: File, tblOpts: TableOptions) {
    setReady((prev) => (prev ? { ...prev, tableHtmlJobId: null, tableMdJobId: null } : prev));
    setTableSubmitting(true);
    submitTable(file, tblOpts, "html")
      .then((job) => setReady((prev) => (prev ? { ...prev, tableHtmlJobId: job.id } : prev)))
      .catch((e) => setSubmitError(e instanceof Error ? e.message : "table failed"))
      .finally(() => setTableSubmitting(false));
    submitTable(file, tblOpts, "markdown")
      .then((job) => setReady((prev) => (prev ? { ...prev, tableMdJobId: job.id } : prev)))
      .catch(() => {});
  }

  // Two jobs per run: json (drives the structured cards) + markdown (copy/download).
  function runDaycard(file: File, dcOpts: DayCardOptions) {
    setReady((prev) =>
      prev
        ? { ...prev, daycardJobId: null, daycardMdJobId: null, daycardResult: null }
        : prev,
    );
    daycardJobIdRef.current = null;
    setDaycardSubmitting(true);
    submitDaycard(file, dcOpts, "json")
      .then((job) => setReady((prev) => (prev ? { ...prev, daycardJobId: job.id } : prev)))
      .catch((e) => setSubmitError(e instanceof Error ? e.message : "day card failed"))
      .finally(() => setDaycardSubmitting(false));
    submitDaycard(file, dcOpts, "markdown")
      .then((job) => setReady((prev) => (prev ? { ...prev, daycardMdJobId: job.id } : prev)))
      .catch(() => {});
  }

  function handleFile(file: File) {
    setSubmitError(null);
    setIsGenerating(false);
    // Allow the analyze result to be refetched even if a re-upload dedupes to the
    // same job id (otherwise the ref guard would skip the refetch after the reset).
    analyzeJobIdRef.current = null;
    daycardJobIdRef.current = null;
    setReady({
      file,
      analyzeJobId: null,
      analyzeResult: null,
      previewJobId: null,
      renderJobId: null,
      renderFilename: null,
      tableHtmlJobId: null,
      tableMdJobId: null,
      daycardJobId: null,
      daycardMdJobId: null,
      daycardResult: null,
    });
    setPhase("ready");
    // Prefill the Table/Day-card departure from the GPX's start time (so the box
    // and the output agree), then auto-generate when dropping straight onto a tab.
    // Sheet kicks off its analyze + preview below.
    gpxStartLocal(file)
      .then((dep) => {
        const nextTable = dep ? { ...tableOpts, departure: dep } : tableOpts;
        const nextDaycard = dep ? { ...daycardOpts, departure: dep } : daycardOpts;
        if (dep) {
          setTableOpts(nextTable);
          setDaycardOpts(nextDaycard);
        }
        if (mode === "table") runTable(file, nextTable);
        else if (mode === "daycard") runDaycard(file, nextDaycard);
      })
      .catch(() => {
        if (mode === "table") runTable(file, tableOpts);
        else if (mode === "daycard") runDaycard(file, daycardOpts);
      });
    if (mode === "sheet") runSheet(file);
  }

  function switchMode(m: Mode) {
    if (m === mode) return;
    setMode(m);
    setSubmitError(null);
    // Entering a tab auto-produces its output once (Sheet: analyze + preview;
    // Table: the table). The Generate button re-runs after option changes. Backend
    // job + analysis caches keep the re-submits cheap.
    if (m === "sheet" && ready?.file && !ready.previewJobId) runSheet(ready.file);
    else if (m === "table" && ready?.file && !ready.tableHtmlJobId) {
      runTable(ready.file, tableOpts);
    } else if (m === "daycard" && ready?.file && !ready.daycardJobId) {
      runDaycard(ready.file, daycardOpts);
    }
  }

  // The Generate button: render the Sheet, or (re)generate the Table.
  function onGenerate() {
    if (!ready) return;
    if (mode === "table") {
      setSubmitError(null);
      runTable(ready.file, tableOpts);
    } else if (mode === "daycard") {
      setSubmitError(null);
      runDaycard(ready.file, daycardOpts);
    } else {
      void handleGenerate();
    }
  }

  async function handleGenerate() {
    if (!ready) return;
    setSubmitError(null);
    setIsGenerating(true);
    setRenderSubmitting(true);
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
    } finally {
      setRenderSubmitting(false);
    }
  }

  // Stop the sheet generating spinner once render is done or errored
  useEffect(() => {
    if (renderStatus?.status === "done" || renderStatus?.status === "error" || renderError) {
      setIsGenerating(false);
    }
  }, [renderStatus, renderError]);

  const sheetGenerating = isGenerating || renderSubmitting || renderPolling;
  const tableGenerating =
    tableSubmitting || tableHtmlPolling || (!!tableHtmlJobId && !tableHtml && !tableHtmlError);
  const daycardGenerating =
    daycardSubmitting ||
    daycardPolling ||
    (!!daycardJobId && !ready?.daycardResult && !daycardError);
  const generating =
    mode === "table"
      ? tableGenerating
      : mode === "daycard"
        ? daycardGenerating
        : sheetGenerating;

  // Progress phase per job line: a submit in flight, then processing (after the
  // 202), then done — so there's continuous spinner + status, never a dead gap.
  const previewPhase: ProgressPhase | null = previewError
    ? "error"
    : previewBlobUrl
      ? "done"
      : previewJobId
        ? "processing"
        : null;
  const renderPhase: ProgressPhase | null = renderError
    ? "error"
    : renderBlobUrl
      ? "done"
      : renderSubmitting
        ? "submitting"
        : renderJobId
          ? "processing"
          : null;
  const tablePhase: ProgressPhase | null = tableHtmlError
    ? "error"
    : tableHtml
      ? "done"
      : tableSubmitting
        ? "submitting"
        : tableHtmlJobId
          ? "processing"
          : null;
  const daycardPhase: ProgressPhase | null = daycardError
    ? "error"
    : ready?.daycardResult
      ? "done"
      : daycardSubmitting
        ? "submitting"
        : daycardJobId
          ? "processing"
          : null;

  if (phase === "idle") {
    return (
      <div className="min-h-screen flex flex-col overflow-x-hidden">
        <Header />
        <main className="flex-1 px-4 py-12">
          <div className="mx-auto w-full max-w-4xl">
            <div className="mx-auto max-w-lg">
              <DropZone onFile={handleFile} />
              {submitError && (
                <p className="mt-3 text-sm text-red-600 text-center">{submitError}</p>
              )}
            </div>
            <IntroGuide />
          </div>
        </main>
        <Footer />
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
                    phase={previewPhase}
                    queuePosition={previewStatus?.queue_position}
                    error={previewError}
                  />
                  <JobProgress
                    label="Sheet"
                    phase={renderPhase}
                    queuePosition={renderStatus?.queue_position}
                    error={renderError}
                  />
                  {submitError && <p className="text-sm text-red-600">{submitError}</p>}
                </div>
              </>
            ) : mode === "table" ? (
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
                  phase={tablePhase}
                  queuePosition={tableHtmlStatus?.queue_position}
                  error={tableHtmlError}
                />
                {submitError && <p className="text-sm text-red-600">{submitError}</p>}
              </>
            ) : (
              <>
                <DayCardInfo
                  data={ready?.daycardResult ?? null}
                  imperial={daycardOpts.units === "imperial"}
                  loading={daycardGenerating}
                />
                <DayCardResultPane
                  data={ready?.daycardResult ?? null}
                  markdown={daycardMarkdown}
                  imperial={daycardOpts.units === "imperial"}
                  loading={daycardGenerating}
                  error={daycardError}
                />
                <JobProgress
                  label="Day card"
                  phase={daycardPhase}
                  queuePosition={daycardStatus?.queue_position}
                  error={daycardError}
                />
                {submitError && <p className="text-sm text-red-600">{submitError}</p>}
              </>
            )}
          </div>

          {/* Right: options + generate */}
          <div className="space-y-4">
            {mode === "sheet" ? (
              <OptionsPanel opts={opts} onChange={setOpts} disabled={generating} />
            ) : mode === "table" ? (
              <TableOptionsPanel opts={tableOpts} onChange={setTableOpts} disabled={generating} />
            ) : (
              <DayCardOptionsPanel
                opts={daycardOpts}
                onChange={setDaycardOpts}
                disabled={generating}
              />
            )}
            {/* Both modes generate on demand via this button. */}
            <button
              data-testid="btn-generate"
              onClick={onGenerate}
              disabled={generating || !ready}
              className="w-full rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {generating ? (
                <span className="inline-flex items-center justify-center gap-2">
                  <Spinner className="w-4 h-4" />
                  {renderSubmitting || tableSubmitting || daycardSubmitting
                    ? "Submitting…"
                    : "Generating…"}
                </span>
              ) : (
                "Generate"
              )}
            </button>
          </div>
        </div>
      </main>
      <Footer />
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
    { value: "daycard", label: "Day card" },
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
        GPX → quick, simple, awareness
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
