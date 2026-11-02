# ---------- frontend build ----------
# static output -> build natively on the build host, also for multi-arch images
FROM --platform=$BUILDPLATFORM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- runtime ----------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MEDIACRAFT_CONFIG_DIR=/config \
    MEDIACRAFT_STATIC_DIR=/app/static \
    MEDIACRAFT_PORT=7979 \
    PUID=1000 \
    PGID=1000 \
    UMASK=002 \
    TZ=Europe/Berlin

RUN apt-get update \
    && apt-get install -y --no-install-recommends tini tzdata curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /src/dist ./static
COPY docker/entrypoint.sh /entrypoint.sh
# strip Windows line endings in case the repo was checked out with CRLF
RUN tr -d '\015' < /entrypoint.sh > /tmp/ep && mv /tmp/ep /entrypoint.sh \
    && chmod +x /entrypoint.sh && mkdir -p /config /data

VOLUME ["/config"]
EXPOSE 7979
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${MEDIACRAFT_PORT}${MEDIACRAFT_URL_BASE}/ping" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
CMD ["python", "-m", "app.main"]
