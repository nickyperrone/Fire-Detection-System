# The whole app in one image for Dokploy (docs/14-deploy.md): the web on port 3000, which forwards
# /api to FastAPI inside the container, and the worker. PostGIS runs apart, as a database service.

# The web, built once; only Next.js's standalone server and its files are kept.
FROM node:24-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build \
    && cp -r public .next/standalone/ \
    && cp -r .next/static .next/standalone/.next/

FROM python:3.12-slim
# rasterio's wheels bundle GDAL but not expat, which the slim image leaves out.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /usr/local/bin/uv
# Only the Node.js binary: the standalone server needs nothing else from npm.
COPY --from=node:24-slim /usr/local/bin/node /usr/local/bin/node

# The repository's layout, so paths relative to its root (config, data) work as in development.
WORKDIR /app/backend
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/backend/.venv/bin:$PATH"

COPY config/ /app/config/
COPY data/aoi/ /app/data/aoi/
COPY data/boundaries/ /app/data/boundaries/
COPY data/models/ /app/data/models/
COPY --from=web /web/.next/standalone/ /app/web/
COPY docker/start.sh /app/start.sh

# Field photos, the clouds and rain frames and the Sentinel-2 cache; mount a volume here to keep
# them across deploys.
VOLUME ["/app/data/snapshots", "/app/data/weather", "/app/data/cache"]

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/api/health', timeout=4)"
CMD ["/app/start.sh"]
