# Convenience wrapper around the Overpass docker compose stack.
# Run from the osm/ directory: `make up`, `make logs`, `make status`, ...

COMPOSE := docker compose
ENDPOINT ?= http://localhost:12345

.PHONY: help up down logs status query nuke ps

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Start Overpass (first run imports California — see logs)
	$(COMPOSE) up -d

down: ## Stop and remove the container (keeps the imported DB volume)
	$(COMPOSE) down

logs: ## Follow container logs (watch the import / update loop)
	$(COMPOSE) logs -f

ps: ## Show container status
	$(COMPOSE) ps

status: ## Hit the Overpass /api/status endpoint
	@curl -fsS $(ENDPOINT)/api/status || echo "not ready yet"

query: ## Run the sample query (fuel stations near Mt Hamilton)
	@./scripts/query.sh

nuke: ## Stop AND delete the imported DB volume (forces a full re-import)
	$(COMPOSE) down -v
