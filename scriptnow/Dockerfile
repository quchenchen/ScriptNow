# ── Stage 1: Frontend build ──────────────────────────────────
FROM node:22-alpine AS frontend-build

WORKDIR /src/frontend

# Use npmmirror (Tsinghua does not provide npm registry; npmmirror is the CN standard)
RUN npm config set registry https://registry.npmmirror.com

# Install deps (package-lock.json for reproducible builds)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Build admin + creator
COPY frontend/apps/admin/package.json apps/admin/
COPY frontend/apps/creator/package.json apps/creator/
COPY frontend/packages/shared/package.json packages/shared/
RUN npm ci --workspaces

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Production runtime ──────────────────────────────
FROM python:3.12-slim

# Use Debian CN mirrors for apt
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        nginx supervisor curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Use PyPI CN mirror
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# Python deps and source
COPY backend/pyproject.toml ./
COPY backend/src/    src/
RUN pip install --no-cache-dir . \
    && pip install --no-cache-dir supervisor

# Backend skills + migrations
COPY backend/skills/ skills/
COPY backend/migrations/ migrations/

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

ENV SCRIPTNOW_ENVIRONMENT=development
ENV PYTHONUNBUFFERED=1

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://127.0.0.1:8000/health || exit 1

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/scriptnow.conf"]
