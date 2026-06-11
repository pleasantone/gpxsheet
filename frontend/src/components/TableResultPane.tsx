import DOMPurify from "dompurify";
import { useMemo, useState } from "react";
import { parseTableSummary } from "./TableInfo";

interface TableResultPaneProps {
  html: string | null;
  markdown: string | null;
  loading: boolean;
  error: string | null;
}

export function TableResultPane({ html, markdown, loading, error }: TableResultPaneProps) {
  // The backend already escapes user content (markdown2 safe_mode="escape"); sanitize
  // again client-side as defense-in-depth before injecting. Keep inline `style` so the
  // table's column alignment survives.
  const safeHtml = useMemo(
    () => (html ? DOMPurify.sanitize(html, { ADD_ATTR: ["style"] }) : ""),
    [html],
  );

  const baseName = (markdown && parseTableSummary(markdown).name) || "route";

  return (
    <div className="space-y-3">
      {(markdown || html) && (
        <div className="flex gap-2">
          <CopyButton testId="copy-markdown" label="Copy Markdown" text={markdown} />
          <CopyButton testId="copy-html" label="Copy HTML" text={html} />
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white min-h-40 flex items-center justify-center overflow-x-auto">
        {loading && (
          <div className="flex flex-col items-center gap-2 py-8 text-slate-400">
            <svg className="w-8 h-8 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-sm">Building table…</span>
          </div>
        )}
        {!loading && error && (
          <p className="text-sm text-red-600 py-8 px-4 text-center">{error}</p>
        )}
        {!loading && !error && html && (
          // The HTML is produced by our own backend (markdown2 with safe_mode=
          // "escape", so any raw HTML in waypoint names is escaped) — safe to
          // render inline, styled by .table-output in index.css to match the app.
          <div
            data-testid="table-output"
            className="table-output w-full p-4"
            dangerouslySetInnerHTML={{ __html: safeHtml }}
          />
        )}
        {!loading && !error && !html && (
          <p className="text-sm text-slate-400 py-8">Drop a GPX file to build a table</p>
        )}
      </div>

      {(markdown || html) && (
        <div className="flex gap-2">
          <DownloadButton
            testId="download-markdown"
            label="Download Markdown"
            text={markdown}
            filename={`${baseName}.md`}
            mime="text/markdown"
          />
          <DownloadButton
            testId="download-html"
            label="Download HTML"
            text={html}
            filename={`${baseName}.html`}
            mime="text/html"
          />
        </div>
      )}
    </div>
  );
}

function DownloadButton({
  label,
  text,
  filename,
  mime,
  testId,
}: {
  label: string;
  text: string | null;
  filename: string;
  mime: string;
  testId: string;
}) {
  function download() {
    if (!text) return;
    const url = URL.createObjectURL(new Blob([text], { type: mime }));
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
      disabled={!text}
      className="flex-1 rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
    >
      {label}
    </button>
  );
}

function CopyButton({
  label,
  text,
  testId,
}: {
  label: string;
  text: string | null;
  testId: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
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
      disabled={!text}
      className="flex-1 rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
    >
      {copied ? "Copied!" : label}
    </button>
  );
}
