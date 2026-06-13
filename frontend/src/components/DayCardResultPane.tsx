import { useMemo, useState } from "react";
import { buildHtml, buildJson, buildMarkdown } from "../dayCardExport";
import { buildDayCardModel, type DayCardView } from "../dayCardModel";
import type { DayCardData } from "../types";
import { Spinner } from "./Spinner";

interface DayCardResultPaneProps {
  data: DayCardData[] | null;
  imperial: boolean;
  loading: boolean;
  error: string | null;
}

export function DayCardResultPane({ data, imperial, loading, error }: DayCardResultPaneProps) {
  // Rebuilds when the JSON OR the units toggle changes — units is instant, no
  // backend round-trip. Exports below are built from this same model.
  const views = useMemo(
    () => (data && data.length ? buildDayCardModel(data, imperial) : null),
    [data, imperial],
  );
  const baseName = (views && views[0]?.title.replace(/^Day \d+: ?/, "")) || "route";

  return (
    <div className="space-y-3">
      {views && (
        <div className="flex gap-2">
          <CopyButton testId="copy-daycard-md" label="Copy Markdown" build={() => buildMarkdown(views)} />
          <CopyButton testId="copy-daycard-html" label="Copy HTML" build={() => buildHtml(views)} />
        </div>
      )}

      {loading && (
        <div className="rounded-xl border border-slate-200 bg-white min-h-40 flex flex-col items-center justify-center gap-2 py-8 text-slate-400">
          <Spinner className="w-8 h-8" />
          <span className="text-sm">Building day cards…</span>
        </div>
      )}

      {!loading && error && (
        <div className="rounded-xl border border-slate-200 bg-white min-h-40 flex items-center justify-center">
          <p className="text-sm text-red-600 py-8 px-4 text-center">{error}</p>
        </div>
      )}

      {!loading && !error && views && (
        <div data-testid="daycard-output" className="space-y-4">
          {views.map((v) => (
            <DayCard key={v.index} view={v} />
          ))}
        </div>
      )}

      {!loading && !error && !views && (
        <div className="rounded-xl border border-slate-200 bg-white min-h-40 flex items-center justify-center">
          <p className="text-sm text-slate-400 py-8">Drop a GPX file to build day cards</p>
        </div>
      )}

      {views && (
        <div className="flex gap-2">
          <DownloadButton
            testId="download-daycard-md"
            label="Download MD"
            build={() => buildMarkdown(views)}
            filename={`${baseName}.md`}
            mime="text/markdown"
          />
          <DownloadButton
            testId="download-daycard-html"
            label="Download HTML"
            build={() => buildHtml(views)}
            filename={`${baseName}.html`}
            mime="text/html"
          />
          <DownloadButton
            testId="download-daycard-json"
            label="Download JSON"
            build={() => (data ? buildJson(data) : "")}
            filename={`${baseName}.daycard.json`}
            mime="application/json"
          />
        </div>
      )}
    </div>
  );
}

function DayCard({ view }: { view: DayCardView }) {
  return (
    <section
      data-testid={`daycard-day-${view.index}`}
      className="rounded-xl border border-slate-200 bg-white p-4 space-y-3"
    >
      <header className="flex items-baseline justify-between gap-3 border-b border-slate-100 pb-2">
        <h3 className="text-base font-semibold text-slate-800">{view.title}</h3>
        {view.date && <span className="text-sm text-slate-400">{view.date}</span>}
      </header>

      <p className="text-sm text-slate-600">{view.stats}</p>

      {view.lines.map((line, i) => (
        <p key={i} className="text-sm text-slate-600 flex gap-2">
          <span aria-hidden className="shrink-0">
            {line.icon}
          </span>
          <span>{line.text}</span>
        </p>
      ))}

      {view.hint && <p className="text-xs text-slate-400 italic">{view.hint}</p>}

      {view.warnings.length > 0 && (
        <ul className="space-y-1 border-t border-slate-100 pt-2">
          {view.warnings.map((w, i) => (
            <li
              key={i}
              className={`text-sm flex gap-2 ${
                w.level === "warning" ? "text-amber-700" : "text-slate-500"
              }`}
            >
              <span aria-hidden className="shrink-0">
                {w.level === "warning" ? "⚠" : "·"}
              </span>
              <span>{w.message}</span>
            </li>
          ))}
        </ul>
      )}

      {view.attributions.length > 0 && (
        <p data-testid="daycard-sources" className="text-xs text-slate-400 border-t border-slate-100 pt-2">
          Sources: {view.attributions.join(" · ")}
        </p>
      )}
    </section>
  );
}

function DownloadButton({
  label,
  build,
  filename,
  mime,
  testId,
}: {
  label: string;
  build: () => string;
  filename: string;
  mime: string;
  testId: string;
}) {
  function download() {
    const url = URL.createObjectURL(new Blob([build()], { type: mime }));
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <button
      data-testid={testId}
      onClick={download}
      className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white hover:bg-brand-dark transition-colors"
    >
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3"
        />
      </svg>
      {label}
    </button>
  );
}

function CopyButton({
  label,
  build,
  testId,
}: {
  label: string;
  build: () => string;
  testId: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(build());
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked (e.g. insecure context) — leave the label unchanged.
    }
  }

  return (
    <button
      data-testid={testId}
      onClick={copy}
      className="flex-1 rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
    >
      {copied ? "Copied!" : label}
    </button>
  );
}
