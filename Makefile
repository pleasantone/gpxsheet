.PHONY: frontend build dev-api dev-api-full dev-worker dev-ui infra infra-down test-e2e test-simple test-full-docker

frontend:
	cd frontend && npm ci && npm run build

build: frontend
	pip install -e ".[service]"

# Simple dev mode: in-memory EagerRunner, no Redis/MinIO needed.
dev-api:
	uvicorn gpxsheet.service.asgi:app --reload --port 8000

# Full-stack dev mode: uses docker-compose.infra.yml for Redis + MinIO.
# Run 'make infra' first, then open two terminals for dev-api-full + dev-worker.
dev-api-full:
	@(set -a; . .env.dev; set +a; exec uvicorn gpxsheet.service.asgi:app --reload --port 8000)

dev-worker:
	@(set -a; . .env.dev; set +a; exec dramatiq gpxsheet.service.jobs)

dev-ui:
	cd frontend && npm run dev

# Run Playwright tests against already-running servers (interactive dev).
test-e2e:
	cd frontend && npx playwright test

# Start simple-mode servers, run smoke tests, then tear down.
test-simple:
	uvicorn gpxsheet.service.asgi:app --port 8000 &
	cd frontend && npm run dev -- --port 5173 &
	cd frontend && npx wait-on http-get://localhost:8000/healthz http://localhost:5173 --timeout 30000
	cd frontend && BASE_URL=http://localhost:5173 npx playwright test tests/smoke.spec.ts; \
	  EXIT=$$?; kill $$(lsof -ti:8000,5173) 2>/dev/null || true; exit $$EXIT

# Full docker: build frontend, compose up, run comprehensive tests, compose down.
test-full-docker:
	$(MAKE) frontend
	docker compose up --build -d
	cd frontend && npx wait-on http-get://localhost:8000/healthz --timeout 60000
	cd frontend && BASE_URL=http://localhost:8000 npx playwright test; \
	  EXIT=$$?; docker compose down; exit $$EXIT

# Start/stop the infrastructure containers (Redis + MinIO) for full-stack dev.
infra:
	docker compose -f docker-compose.infra.yml up -d

infra-down:
	docker compose -f docker-compose.infra.yml down
