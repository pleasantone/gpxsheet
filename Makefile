.PHONY: frontend build dev-api dev-ui

frontend:
	cd frontend && npm ci && npm run build

build: frontend
	pip install -e ".[service]"

dev-api:
	uvicorn gpxsheet.service.asgi:app --reload --port 8000

dev-ui:
	cd frontend && npm run dev
