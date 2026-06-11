# GPXSheet React Frontend — Implementation Plan

## Context

GPXSheet has a complete FastAPI service (job-queue-based render/analyze API) but no web UI. This plan adds a React+Vite SPA bundled into the FastAPI service: drag-drop a GPX, get an instant strip preview, configure options, generate and download the final PDF/PNG.

---

## Key Decisions

| Decision | Choice | Reason |
|---|---|---|
| Frontend location | Bundled into FastAPI at `/` | Single deployment, no CORS, one service |
| Tech stack | React 19 + TypeScript + Vite 6 + Tailwind v4 | Modern, minimal build config |
| Preview refresh | Re-render on Generate click only | Avoid burning server on every option tweak |
| PDF output | Download button only | Universal; no iframe/mobile quirks |
| API key UI | Optional key field in settings popover, stored in localStorage | Needed if server has auth enabled |

---

## Architecture

```
frontend/                          ← Vite+React project
  build → src/gpxsheet/service/static/   ← FastAPI serves at /
```

**Dev**: Vite on :5173 proxies `/v1/` to uvicorn on :8000 — no CORS config needed.  
**Prod**: `npm run build` outputs to `service/static/`; `StaticFiles(html=True)` gives SPA catch-all.

---

## UX Flow

1. **Full-page drop zone** on load (drop GPX or click to browse)
2. **On drop** → fire two parallel jobs:
   - `POST /v1/analyze` → route name, distance, decision count, fuel stops (shown as info cards)
   - `POST /v1/render` with `layout=preview&format=png` → strip thumbnail shown inline
3. **Options panel** (below/beside preview): profile, layout, format, paper, fuel_range, turn_style, show_branches, lanes_per_page, decisions_per_lane
4. **"Generate" button** → `POST /v1/render` with chosen params → poll → **download button** (PDF or PNG)
5. **Settings popover** (gear icon, top-right) → optional API key field (saved to localStorage, sent as `X-API-Key` header on every request)

### Smart options behavior
- `paper` + `lanes_per_page`: hidden when layout is `preview` or `strip`
- `format`: locked to `png` and disabled when layout is `preview` or `strip`
- Switching layout to `preview`/`strip` auto-sets `format = "png"` in state
- `decisions_per_lane`: label reads "0 = auto-fit"

---

## File Structure

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── src/
    ├── main.tsx
    ├── App.tsx                 ← top-level state machine
    ├── api.ts                  ← all /v1/ calls, injects X-API-Key from localStorage
    ├── types.ts                ← JobStatus, AnalyzeResult, RenderOptions, etc.
    ├── index.css               ← @import "tailwindcss"; @theme { --color-brand: #e85d04 }
    ├── hooks/
    │   └── useJobPoll.ts       ← exponential-backoff poller (500ms → 4000ms)
    └── components/
        ├── DropZone.tsx        ← drag/drop + file input (fullscreen or compact)
        ├── RouteInfo.tsx       ← analyze result cards + skeleton loaders
        ├── OptionsPanel.tsx    ← all render params, smart show/hide
        ├── JobProgress.tsx     ← spinner/checkmark/error for any job
        ├── ResultPane.tsx      ← preview PNG + download button after Generate
        └── SettingsPopover.tsx ← API key input, persisted to localStorage
```

### `App.tsx` state

Discriminated union (not a bag of booleans):
```typescript
type AppState =
  | { phase: "idle" }
  | {
      phase: "ready";
      file: File;
      opts: RenderOptions;
      analyzeJobId: string | null;
      analyzeResult: AnalyzeResult | null;
      previewJobId: string | null;    // always layout=preview, format=png
      previewBlobUrl: string | null;
      renderJobId: string | null;     // active generate job
      renderDone: { blobUrl: string; filename: string } | null;
    };
```

### `useJobPoll.ts`

Exponential backoff: 500ms → ×1.5 each miss → cap 4000ms. Self-cancels on unmount.
When `fetchBlob=true`, fetches the result blob when job reaches `done` and returns it.
Cache hits (POST returns `status: "done"` immediately) skip the poll loop entirely.

### `api.ts`

All requests read `localStorage.getItem("gpxsheet-api-key")` and inject it as `X-API-Key` if present. Functions: `submitAnalyze`, `submitRender`, `pollJob`, `fetchResult`. All return typed promises; `ApiError` carries the HTTP status.

---

## FastAPI Changes

### `src/gpxsheet/service/app.py`

**1. StaticFiles mount** — add just before `return app` in `create_app()`:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_static = Path(__file__).parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=_static, html=True), name="static")
```

Guard means the app boots cleanly in CI/dev without a built frontend.

**2. CSP split** — update `_SecurityHeadersMiddleware.dispatch`. Currently `default-src 'none'` blocks the React bundle. Split by path:

```python
is_api = request.url.path.startswith("/v1/") or request.url.path in ("/healthz", "/readyz")
csp = (
    "default-src 'none'; frame-ancestors 'none'"
    if is_api
    else "default-src 'self'; img-src 'self' blob: data:; frame-ancestors 'none'"
)
response.headers.setdefault("Content-Security-Policy", csp)
```

`blob:` in `img-src` is required because preview PNGs are displayed via `URL.createObjectURL()`.

### `pyproject.toml`

1. Add `aiofiles>=23.0` to `[project.optional-dependencies] service` (Starlette's `StaticFiles` requires it)
2. Add `"service/static/**/*"` to `[tool.setuptools.package-data] gpxsheet`

---

## Build Integration

**`Makefile`** (new, at repo root):
```makefile
.PHONY: frontend build dev-api dev-ui
frontend:
	cd frontend && npm ci && npm run build
build: frontend
	pip install -e ".[service]"
dev-api:
	uvicorn gpxsheet.service.asgi:app --reload --port 8000
dev-ui:
	cd frontend && npm run dev
```

**`.gitignore`** additions:
```
src/gpxsheet/service/static/
frontend/node_modules/
```
Built files are reproducible from source; committing them creates noisy diffs.

**Docker** (multi-stage):
```dockerfile
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
# ... existing pip install ...
COPY --from=frontend /app/src/gpxsheet/service/static ./src/gpxsheet/service/static
```

---

## Implementation Order

1. `pyproject.toml` — add `aiofiles`, add `service/static/**/*` package-data
2. `app.py` — CSP split + StaticFiles mount
3. `frontend/` scaffold — `package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, `index.css`
4. `types.ts` + `api.ts` (with API key injection)
5. `hooks/useJobPoll.ts`
6. Components in order: `DropZone` → `SettingsPopover` → `RouteInfo` → `OptionsPanel` → `JobProgress` → `ResultPane`
7. `App.tsx` wiring
8. `Makefile` + `.gitignore` update
9. `npm run build` + smoke test

---

## Verification

```bash
# Build frontend
cd frontend && npm ci && npm run build

# Start service (dev mode — no Redis/MinIO needed)
source .venv/bin/activate
uvicorn gpxsheet.service.asgi:app --port 8000

# Manual checks at http://localhost:8000:
# 1. React SPA loads (not Swagger UI or 404)
# 2. Drop a GPX from gpxsamples/ — analyze info cards appear
# 3. Preview strip PNG renders inline
# 4. Change layout to "landscape" — paper/lanes options hide
# 5. Click Generate — PDF downloads
# 6. Change layout to "preview" — format locks to PNG
# 7. Settings popover — enter a fake API key, verify X-API-Key header in network tab
# 8. /v1/render still works via /docs Swagger UI (API not broken)
# 9. /healthz returns 200

# CI gates
ruff check .
mypy src tests docs
pytest -q
```
