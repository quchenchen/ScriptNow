# Build registries default to their upstream services. Operators in restricted
# networks can override them through Docker build arguments without baking a
# region-specific mirror into the application image.
ARG NODE_IMAGE=node:22-alpine
ARG PYTHON_IMAGE=python:3.12-slim

# ── Stage 1: Frontend build ──────────────────────────────────
FROM ${NODE_IMAGE} AS frontend-build

ARG NPM_REGISTRY=https://registry.npmjs.org

WORKDIR /src/frontend

RUN npm config set registry "${NPM_REGISTRY}"

# Install the complete workspace graph from the reproducible lockfile. Workspace
# manifests must exist before npm ci or their build-time dependencies are skipped.
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/apps/admin/package.json apps/admin/
COPY frontend/apps/creator/package.json apps/creator/
COPY frontend/packages/shared/package.json packages/shared/
RUN npm ci --include=dev

# Build admin + creator
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Production runtime ──────────────────────────────
FROM ${PYTHON_IMAGE}

ARG DEBIAN_MIRROR=
ARG PIP_INDEX_URL=https://pypi.org/simple

# DEBIAN_MIRROR is optional because not every mirror supports every Debian
# release. The official repository remains the safe default.
RUN if [ -n "${DEBIAN_MIRROR}" ]; then \
        sed -i \
          -e "s|https://deb.debian.org/debian|${DEBIAN_MIRROR}|g" \
          -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" \
          /etc/apt/sources.list.d/debian.sources; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        nginx supervisor curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps and source
COPY backend/pyproject.toml ./
COPY backend/src/    src/
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" .

# Backend skills + migrations
COPY backend/skills/ skills/
COPY backend/migrations/ migrations/
COPY backend/alembic.ini alembic.ini

# Frontend static assets from build stage
COPY --from=frontend-build /src/frontend/apps/creator/dist/ /app/static/creator/
COPY --from=frontend-build /src/frontend/apps/admin/dist/    /app/static/admin/

# Runtime configs
COPY nginx.conf       /etc/nginx/sites-available/default
COPY supervisord.conf /etc/supervisor/conf.d/scriptnow.conf

# Ensure nginx can read static files
RUN chmod -R 755 /app/static && \
    rm -f /etc/nginx/sites-enabled/default && \
    ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

ENV SCRIPTNOW_ENVIRONMENT=production
ENV PYTHONUNBUFFERED=1

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://127.0.0.1:8000/health || exit 1

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/scriptnow.conf"]
