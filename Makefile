.PHONY: frontend build dev-api dev-api-full dev-worker dev-ui infra infra-down

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

# Start/stop the infrastructure containers (Redis + MinIO) for full-stack dev.
infra:
	docker compose -f docker-compose.infra.yml up -d

infra-down:
	docker compose -f docker-compose.infra.yml down
