"""FastAPI application entry point."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .core.events import setup_logging

setup_logging()
log = logging.getLogger("mediacraft")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from .core.scheduler import commands, scheduler
    from .db import init_db
    from .services.commands import register_all

    init_db()
    register_all()
    commands.start()
    if not config.DISABLE_SCHEDULER:
        scheduler.start()
    log.info("%s %s gestartet – Port %s, Config %s", config.APP_NAME, config.VERSION, config.PORT, config.CONFIG_DIR)
    log.info("API-Key: %s…", config.API_KEY[:6])
    yield
    scheduler.stop()


def _index_html(path) -> str:
    """index.html with the URL base: assets are referenced relatively and resolve against <base href>."""
    base = config.URL_BASE
    inject = f'<base href="{base}/" /><script>window.__MC_BASE__ = {json.dumps(base)};</script>'
    return path.read_text("utf-8").replace("<head>", "<head>" + inject, 1)


def create_app() -> FastAPI:
    app = FastAPI(title=config.APP_NAME, version=config.VERSION, lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", root_path=config.URL_BASE)
    app.add_middleware(GZipMiddleware, minimum_size=2048)

    from .api.compat import VERSIONS, radarr_router, sonarr_router
    from .api.routes import config as config_routes
    from .api.routes import lists, media, stats, system

    app.include_router(system.public)
    app.include_router(system.router)
    app.include_router(config_routes.router)
    app.include_router(media.router)
    app.include_router(lists.router)
    app.include_router(stats.router)
    app.include_router(sonarr_router)
    app.include_router(radarr_router)

    @app.middleware("http")
    async def compat_headers(request: Request, call_next):
        # Sonarr/Radarr (ASP.NET) route case-insensitively and Jellyseerr/Seerr call e.g.
        # /qualityProfile and /rootFolder; our compat routes are all lowercase, so normalise first.
        base, path = config.URL_BASE, request.scope["path"]
        flavor = next((f for f in VERSIONS if path.lower().startswith(f"{base.lower()}/{f}/")), None)
        if flavor:
            request.scope["path"] = base + path[len(base):].lower()
        response = await call_next(request)
        # Prowlarr & co. read the application version from this header
        if flavor:
            response.headers["X-Application-Version"] = VERSIONS[flavor]
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("Unbehandelter Fehler bei %s %s", request.method, request.url.path)
        return JSONResponse({"detail": f"Interner Fehler: {exc}"}, status_code=500)

    @app.get("/ping")
    def ping():
        return {"status": "ok"}

    static = config.STATIC_DIR
    if (static / "index.html").exists():
        if (static / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")
        index_html = _index_html(static / "index.html")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            target = (static / full_path).resolve()
            if full_path and target.is_file() and static.resolve() in target.parents and target.name != "index.html":
                return FileResponse(target)
            if full_path.startswith(("api/", "sonarr/", "radarr/")):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            return HTMLResponse(index_html, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT, log_config=None, proxy_headers=True,
                forwarded_allow_ips="*")


if __name__ == "__main__":
    run()
