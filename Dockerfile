# GPXSheet web service image (API + Dramatiq worker share the runtime stage).
# Self-contained: the SPA is built here, so no `make frontend` is needed before
# `docker compose up --build` or a Hugging Face Space build.

# Stage 1: build the React/Vite SPA. Vite's outDir is ../src/gpxsheet/service/
# static (see frontend/vite.config.ts), so the build lands at /build/src/....
FROM node:22-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the Python service.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    GPXSHEET_RESULTS_DIR=/tmp/gpxsheet-results \
    GPXSHEET_OSM_CACHE_DIR=/tmp/gpxsheet-osm-cache

WORKDIR /app

# Install the package with the service + OSM extras. The geo wheels (shapely,
# pyproj, pyogrio) bundle their native libs, so no system GDAL/GEOS is needed.
# The built SPA must be in place BEFORE the install so package-data picks it up
# (pyproject ships service/static/**/*). A BuildKit pip cache mount keeps
# rebuilds fast when only the source changes.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY --from=frontend /build/src/gpxsheet/service/static ./src/gpxsheet/service/static
RUN --mount=type=cache,target=/root/.cache/pip pip install ".[service]"

RUN useradd --create-home app && mkdir -p "$GPXSHEET_RESULTS_DIR" \
    && chown -R app "$GPXSHEET_RESULTS_DIR"
USER app

EXPOSE 8000

# API by default; the worker service overrides command to:
#   dramatiq gpxsheet.service.jobs
CMD ["uvicorn", "gpxsheet.service.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
