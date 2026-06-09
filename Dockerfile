# GPXSheet web service image (API + Dramatiq worker share this image).
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    GPXSHEET_RESULTS_DIR=/tmp/gpxsheet-results

WORKDIR /app

# Install the package with the service + OSM extras. The geo wheels (shapely,
# pyproj, pyogrio) bundle their native libs, so no system GDAL/GEOS is needed.
# A BuildKit pip cache mount keeps rebuilds fast when only the source changes.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip pip install ".[service]"

RUN useradd --create-home app && mkdir -p "$GPXSHEET_RESULTS_DIR" \
    && chown -R app "$GPXSHEET_RESULTS_DIR"
USER app

EXPOSE 8000

# API by default; the worker service overrides command to:
#   dramatiq gpxsheet.service.jobs
CMD ["uvicorn", "gpxsheet.service.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
