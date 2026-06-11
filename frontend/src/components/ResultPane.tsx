import { useCallback, useEffect, useRef, useState } from "react";
import { Spinner } from "./Spinner";

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
            <Spinner className="w-8 h-8" />
            <span className="text-sm">Rendering preview…</span>
          </div>
        )}
        {imgSrc && <PanZoomImage src={imgSrc} />}
        {!previewLoading && !imgSrc && (
          <p className="text-sm text-slate-400 py-8">Preview unavailable</p>
        )}
      </div>

      {/* Download button — shown when a generate job is done */}
      {renderBlobUrl && renderFilename && (
        <a
          data-testid="download-link"
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

const MAX_ZOOM = 8;
const clampZoom = (s: number) => Math.min(MAX_ZOOM, Math.max(1, s));

type Pt = { x: number; y: number };
const dist = (a: Touch, b: Touch) => Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
const mid = (a: Touch, b: Touch): Pt => ({
  x: (a.clientX + b.clientX) / 2,
  y: (a.clientY + b.clientY) / 2,
});

// Pan + zoom for the preview. Desktop: scroll to zoom, drag to pan, double-click to
// reset. Touch: pinch to zoom, one-finger drag to pan. Wheel/touch listeners are
// attached non-passively so gestures over the image don't also scroll/zoom the page.
function PanZoomImage({ src }: { src: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [pos, setPos] = useState<Pt>({ x: 0, y: 0 });

  // Mirror of live transform, read inside the imperative gesture listeners.
  const view = useRef({ scale: 1, pos: { x: 0, y: 0 } as Pt });
  useEffect(() => {
    view.current = { scale, pos };
  }, [scale, pos]);

  const reset = useCallback(() => {
    setScale(1);
    setPos({ x: 0, y: 0 });
  }, []);
  const apply = useCallback((s: number, p: Pt) => {
    const ns = clampZoom(s);
    setScale(ns);
    setPos(ns === 1 ? { x: 0, y: 0 } : p); // snap to centre at 1x
  }, []);

  // Reset whenever a new image is shown.
  useEffect(reset, [reset, src]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const { scale: s, pos: p } = view.current;
      apply(s * (e.deltaY < 0 ? 1.15 : 1 / 1.15), p);
    };

    // Gesture start state for touch.
    let pinchDist = 0;
    let startScale = 1;
    let startPos: Pt = { x: 0, y: 0 };
    let startMid: Pt = { x: 0, y: 0 };
    let panFrom: Pt | null = null;

    const onTouchStart = (e: TouchEvent) => {
      const t = e.touches;
      if (t.length === 2) {
        pinchDist = dist(t[0], t[1]);
        startScale = view.current.scale;
        startPos = view.current.pos;
        startMid = mid(t[0], t[1]);
        panFrom = null;
      } else if (t.length === 1 && view.current.scale > 1) {
        panFrom = { x: t[0].clientX - view.current.pos.x, y: t[0].clientY - view.current.pos.y };
      }
    };
    const onTouchMove = (e: TouchEvent) => {
      const t = e.touches;
      if (t.length === 2 && pinchDist > 0) {
        e.preventDefault();
        const m = mid(t[0], t[1]);
        apply(startScale * (dist(t[0], t[1]) / pinchDist), {
          x: startPos.x + (m.x - startMid.x),
          y: startPos.y + (m.y - startMid.y),
        });
      } else if (t.length === 1 && panFrom) {
        e.preventDefault();
        setPos({ x: t[0].clientX - panFrom.x, y: t[0].clientY - panFrom.y });
      }
    };
    const onTouchEnd = (e: TouchEvent) => {
      if (e.touches.length < 2) pinchDist = 0;
      if (e.touches.length === 1 && view.current.scale > 1) {
        panFrom = {
          x: e.touches[0].clientX - view.current.pos.x,
          y: e.touches[0].clientY - view.current.pos.y,
        };
      } else if (e.touches.length === 0) {
        panFrom = null;
      }
    };

    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("touchstart", onTouchStart, { passive: false });
    el.addEventListener("touchmove", onTouchMove, { passive: false });
    el.addEventListener("touchend", onTouchEnd);
    return () => {
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove", onTouchMove);
      el.removeEventListener("touchend", onTouchEnd);
    };
  }, [apply]);

  // Mouse drag (desktop).
  const drag = useRef<Pt | null>(null);
  function onMouseDown(e: React.MouseEvent) {
    if (scale === 1) return;
    drag.current = { x: e.clientX - pos.x, y: e.clientY - pos.y };
  }
  function onMouseMove(e: React.MouseEvent) {
    if (!drag.current) return;
    setPos({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y });
  }
  const endDrag = () => {
    drag.current = null;
  };

  const zoomed = scale > 1;

  return (
    <div
      ref={ref}
      className={`relative w-full max-h-[60vh] overflow-hidden ${
        zoomed ? "cursor-grab active:cursor-grabbing" : ""
      }`}
      // Let the page scroll vertically at 1x; take full gesture control when zoomed.
      style={{ touchAction: zoomed ? "none" : "pan-y" }}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={endDrag}
      onMouseLeave={endDrag}
      onDoubleClick={reset}
    >
      <img
        data-testid="preview-image"
        src={src}
        alt="Route preview"
        draggable={false}
        style={{
          transform: `translate(${pos.x}px, ${pos.y}px) scale(${scale})`,
          transformOrigin: "center center",
        }}
        className="w-full object-contain max-h-[60vh] select-none"
      />
      {zoomed && (
        <button
          onClick={reset}
          className="absolute top-2 right-2 rounded-lg bg-white/90 border border-slate-300 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-white shadow-sm"
        >
          Reset
        </button>
      )}
      <span className="pointer-events-none absolute bottom-2 left-2 rounded bg-white/80 px-2 py-0.5 text-[10px] text-slate-500">
        pinch / scroll to zoom · drag to pan · double-tap to reset
      </span>
    </div>
  );
}
