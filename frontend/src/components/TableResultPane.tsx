import { useMemo, useState } from "react";
import { buildHtml, buildJson, buildMarkdown } from "../tableExport";
import { buildDisplayModel, type DisplayModel, type DisplaySection } from "../tableModel";
import type { TableDocData, TableOptions } from "../types";
import { Spinner } from "./Spinner";

interface TableResultPaneProps {
  data: TableDocData | null;
  opts: TableOptions;
  loading: boolean;
  error: string | null;
}

export function TableResultPane({ data, opts, loading, error }: TableResultPaneProps) {
  // Rebuilds when the JSON OR the display toggles (units/coords/cue) change —
  // those toggles are instant, no backend round-trip.
  const model = useMemo(() => (data ? buildDisplayModel(data, opts) : null), [data, opts]);
  const baseName = model?.name || "route";

  return (
    <div className="space-y-3">
      {model && (
        <div className="flex gap-2">
          <CopyButton testId="copy-markdown" label="Copy Markdown" build={() => buildMarkdown(model)} />
          <CopyButton testId="copy-html" label="Copy HTML" build={() => buildHtml(model)} />
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white min-h-40 flex items-center justify-center overflow-x-auto">
        {loading && (
          <div className="flex flex-col items-center gap-2 py-8 text-slate-400">
            <Spinner className="w-8 h-8" />
            <span className="text-sm">Building table…</span>
          </div>
        )}
        {!loading && error && (
          <p className="text-sm text-red-600 py-8 px-4 text-center">{error}</p>
        )}
        {!loading && !error && model && (
          <div data-testid="table-output" className="table-output w-full p-4 space-y-6">
            {model.sections.map((sec, i) => (
              <Section key={i} model={model} sec={sec} />
            ))}
          </div>
        )}
        {!loading && !error && !model && (
          <p className="text-sm text-slate-400 py-8">Drop a GPX file to build a table</p>
        )}
      </div>

      {model && (
        <div className="flex gap-2">
          <DownloadButton
            testId="download-markdown"
            label="Download Markdown"
            build={() => buildMarkdown(model)}
            filename={`${baseName}.md`}
            mime="text/markdown"
          />
          <DownloadButton
            testId="download-html"
            label="Download HTML"
            build={() => buildHtml(model)}
            filename={`${baseName}.html`}
            mime="text/html"
          />
          <DownloadButton
            testId="download-json"
            label="Download JSON"
            build={() => (data ? buildJson(data) : "")}
            filename={`${baseName}.json`}
            mime="application/json"
          />
        </div>
      )}
    </div>
  );
}

function Section({ model, sec }: { model: DisplayModel; sec: DisplaySection }) {
  const cols = [
    "Name",
    ...(model.showCoords ? ["Lat,Lon"] : []),
    "Dist.",
    "GL",
    "ETA",
    ...(sec.showRoad ? ["Road"] : []),
    "Notes",
  ];
  const meta = [sec.departure ? `Departs ${sec.departure}` : null, sec.distance, sec.speed]
    .filter(Boolean)
    .join("  ·  ");

  return (
    <section className="space-y-2">
      <div>
        <h2>{sec.title}</h2>
        <p className="text-xs text-slate-500">{meta}</p>
        {sec.sun && (
          <p className="text-xs text-slate-500">
            ☀ sunrise {sec.sun.sunrise} · sunset {sec.sun.sunset}
          </p>
        )}
      </div>

      <table className="gpxtable">
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sec.rows.map((r, i) => (
            <tr key={i}>
              <td>{r.name}</td>
              {model.showCoords && <td className="tabular-nums">{r.latlon}</td>}
              <td className="tabular-nums">{r.dist}</td>
              <td>{r.marker}</td>
              <td className="tabular-nums">{r.eta}</td>
              {sec.showRoad && <td>{r.road}</td>}
              <td>{r.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {sec.cue.length > 0 && <CueTable sec={sec} />}
    </section>
  );
}

function CueTable({ sec }: { sec: DisplaySection }) {
  const etaOn = sec.cue.some((c) => c.eta);
  return (
    <div data-testid="cue-output" className="space-y-1">
      <h3 className="text-sm font-semibold text-slate-700">Turn-by-turn</h3>
      <table className="gpxtable">
        <thead>
          <tr>
            <th>Mile</th>
            {etaOn && <th>ETA</th>}
            <th>Cue</th>
          </tr>
        </thead>
        <tbody>
          {sec.cue.map((c, i) => (
            <tr key={i}>
              <td className="tabular-nums">{c.mile}</td>
              {etaOn && <td className="tabular-nums">{c.eta}</td>}
              <td>{c.cue}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
