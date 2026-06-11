import { useRef, useState } from "react";

interface DropZoneProps {
  onFile: (file: File) => void;
  compact?: boolean;
}

export function DropZone({ onFile, compact = false }: DropZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && isGpx(file)) onFile(file);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file && isGpx(file)) onFile(file);
    e.target.value = "";
  }

  if (compact) {
    return (
      <button
        data-testid="upload-different"
        onClick={() => inputRef.current?.click()}
        className="text-sm text-brand hover:text-brand-dark underline underline-offset-2 cursor-pointer"
      >
        Upload different file
        <input
          ref={inputRef}
          data-testid="file-input"
          type="file"
          accept=".gpx,application/gpx+xml"
          className="hidden"
          onChange={handleChange}
        />
      </button>
    );
  }

  return (
    <div
      data-testid="drop-zone"
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={[
        "flex flex-col items-center justify-center gap-4 cursor-pointer",
        "rounded-2xl border-2 border-dashed transition-colors select-none",
        "min-h-64 p-12 text-center",
        isDragging
          ? "border-brand bg-orange-50"
          : "border-slate-300 hover:border-brand hover:bg-slate-50",
      ].join(" ")}
    >
      <svg
        className={`w-14 h-14 ${isDragging ? "text-brand" : "text-slate-400"}`}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M9 6.75V15m6-6v8.25m.503 3.498 4.875-2.437c.381-.19.622-.58.622-1.006V4.82c0-.836-.88-1.318-1.548-.845l-4.125 2.75a1.125 1.125 0 0 1-1.254 0l-4.5-3A1.125 1.125 0 0 0 4.5 4.845v12.75c0 .436.241.826.622 1.006l4.875 2.437c.596.298 1.283-.13 1.283-.796V8.65c0-.425-.24-.814-.62-1.003L7.5 6.375M9 6.75l6 3.75"
        />
      </svg>
      <div>
        <p className="text-lg font-semibold text-slate-700">
          Drop a GPX file here
        </p>
        <p className="text-sm text-slate-500 mt-1">or click to browse</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".gpx,application/gpx+xml"
        className="hidden"
        onChange={handleChange}
      />
    </div>
  );
}

function isGpx(file: File): boolean {
  return file.name.toLowerCase().endsWith(".gpx") || file.type === "application/gpx+xml";
}
