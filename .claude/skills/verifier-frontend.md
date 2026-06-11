# Frontend verifier

Use this skill when verifying frontend changes to the GPXSheet SPA.

## Modes and test depth

| Mode | Test file | Server setup | BASE_URL |
|---|---|---|---|
| Simple | `tests/smoke.spec.ts` | `make dev-api` + `make dev-ui` | `http://localhost:5173` |
| Full-stack | `tests/smoke.spec.ts` | `make infra` + `make dev-api-full` + `make dev-worker` + `make dev-ui` | `http://localhost:5173` |
| Full docker | `tests/comprehensive.spec.ts` | `make frontend && docker compose up --build -d` | `http://localhost:8000` |

## Quick start (simple mode — most common)

```bash
# Terminal 1
make dev-api

# Terminal 2
make dev-ui

# Terminal 3 — once both are up
cd frontend && npx wait-on http://localhost:8000/healthz http://localhost:5173 --timeout 30000
cd frontend && BASE_URL=http://localhost:5173 npx playwright test tests/smoke.spec.ts
```

Or use the Makefile targets (they start and stop servers automatically):

```bash
make test-simple          # smoke against simple mode
make test-full-docker     # comprehensive against full docker
make test-e2e             # run tests against already-running servers
```

## What counts as PASS

- **Smoke**: 1 test passes — upload, stats, preview, generate, download link
- **Comprehensive**: all tests in `tests/comprehensive.spec.ts` pass

## Artifacts on failure

Screenshots and videos saved to `frontend/test-results/` (gitignored).

## data-testid reference

| data-testid | Element |
|---|---|
| `drop-zone` | main upload div |
| `file-input` | hidden `<input type="file">` in compact variant |
| `upload-different` | compact "Upload different file" button |
| `route-name` | `<h2>` route name heading |
| `route-stats` | stats cards wrapper |
| `preview-image` | `<img>` in ResultPane |
| `download-link` | `<a download>` for PDF/PNG result |
| `opt-layout` | layout `<select>` |
| `opt-format` | format `<select>` |
| `opt-paper` | paper `<select>` |
| `opt-lanes` | lanes/page `<input>` |
| `btn-generate` | Generate button |
| `btn-settings` | gear/settings button |
| `input-api-key` | API key password input |
