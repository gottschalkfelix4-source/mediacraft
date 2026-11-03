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

# mediainfo: real audio languages/codecs of imported files; unrar (non-free) + 7zip: packed downloads
RUN sed -i 's/^Components: main$/Components: main non-free/' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends tini tzdata curl mediainfo 7zip \
    && (apt-get install -y --no-install-recommends unrar || echo "unrar nicht verfügbar – RAR über 7zip") \
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

# build info changes on every CI run: keep it below all cached layers (apt/pip under arm64
# emulation take ~3 minutes whenever they have to run again)
ARG MEDIACRAFT_BUILD=""
ARG MEDIACRAFT_COMMIT=""
ARG MEDIACRAFT_BUILD_DATE=""
ENV MEDIACRAFT_BUILD=$MEDIACRAFT_BUILD \
    MEDIACRAFT_COMMIT=$MEDIACRAFT_COMMIT \
    MEDIACRAFT_BUILD_DATE=$MEDIACRAFT_BUILD_DATE

VOLUME ["/config"]
EXPOSE 7979
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${MEDIACRAFT_PORT}${MEDIACRAFT_URL_BASE}/ping" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
CMD ["python", "-m", "app.main"]
