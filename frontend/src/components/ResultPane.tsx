interface ResultPaneProps {
  previewBlobUrl: string | null;
  previewLoading: boolean;
  renderBlobUrl: string | null;
  renderFilename: string | null;
  renderContentType: string | null;
}

export function ResultPane({
  previewBlobUrl,
  previewLoading,
  renderBlobUrl,
  renderFilename,
  renderContentType,
}: ResultPaneProps) {
  const isPng = renderContentType === "image/png";
  const imgSrc = isPng && renderBlobUrl ? renderBlobUrl : previewBlobUrl;

  return (
    <div className="space-y-3">
      {/* Image preview area */}
      <div className="relative rounded-xl overflow-hidden border border-slate-200 bg-slate-100 min-h-40 flex items-center justify-center">
        {previewLoading && !imgSrc && (
          <div className="flex flex-col items-center gap-2 py-8 text-slate-400">
            <svg className="w-8 h-8 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-sm">Rendering preview…</span>
          </div>
        )}
        {imgSrc && (
          <img
            src={imgSrc}
            alt="Route preview"
            className="w-full object-contain max-h-[60vh]"
          />
        )}
        {!previewLoading && !imgSrc && (
          <p className="text-sm text-slate-400 py-8">Preview unavailable</p>
        )}
      </div>

      {/* Download button — shown when a generate job is done */}
      {renderBlobUrl && renderFilename && (
        <a
          href={renderBlobUrl}
          download={renderFilename}
          className="flex items-center justify-center gap-2 w-full rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white hover:bg-brand-dark transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3"
            />
          </svg>
          Download {renderFilename}
        </a>
      )}
    </div>
  );
}
