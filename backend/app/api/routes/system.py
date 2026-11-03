"""System: status, auth, settings, tasks/commands, logs, live events, filesystem browser."""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import queue as queue_mod
import secrets
import shutil
import string
import sys
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from ... import config
from ...core import settings as settings_mod
from ...core.events import ring, subscribe, unsubscribe
from ...core.scheduler import commands, scheduler
from ...db import get_db
from ...models import Movie, RootFolder, Series, utcnow
from ...services import backup as backup_svc
from ...services.commands import health_cache
from ..deps import COOKIE, global_login_limiter, hash_password, login_limiter, make_session, require_auth, session_ok, verify_password

public = APIRouter(prefix="/api/v1")
router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_auth)])

STARTED = utcnow()


# ------------------------------------------------------------------------------------ auth (public)
@public.get("/auth/status")
def auth_status(request: Request, db: Session = Depends(get_db)):
    auth = settings_mod.get(db, "auth")
    return {"method": auth.get("method", "none"), "authenticated": session_ok(request, auth), "app": config.APP_NAME,
            "version": config.VERSION}


@public.post("/auth/login")
def login(body: dict, request: Request, response: Response, db: Session = Depends(get_db)):
    client = request.client.host if request.client else "?"
    wait = max(login_limiter.retry_after(client), global_login_limiter.retry_after("*"))
    if wait:
        raise HTTPException(429, f"Zu viele Fehlversuche – bitte in {max(1, wait // 60)} Minute(n) erneut versuchen",
                            headers={"Retry-After": str(wait)})
    auth = settings_mod.get(db, "auth")
    if body.get("username") != auth.get("username") or not verify_password(body.get("password", ""), auth.get("password_hash", "")):
        login_limiter.failed(client)
        global_login_limiter.failed("*")
        logging.getLogger("auth").warning("Fehlgeschlagene Anmeldung für '%s' von %s", body.get("username"), client)
        raise HTTPException(401, "Benutzername oder Passwort falsch")
    login_limiter.reset(client)
    token = make_session(auth["secret"], auth["username"], 30 if body.get("remember") else 1)
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=30 * 86400 if body.get("remember") else None)
    return {"ok": True}


@public.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


# ------------------------------------------------------------------------------------ system
@router.get("/system/status")
def status(db: Session = Depends(get_db)):
    return {
        "app": config.APP_NAME, "version": config.VERSION, "build": config.BUILD, "commit": config.COMMIT[:7],
        "build_date": config.BUILD_DATE, "started": STARTED.isoformat() + "Z",
        "python": platform.python_version(), "os": platform.platform(), "config_dir": str(config.CONFIG_DIR),
        "db": str(config.DB_PATH), "api_key": config.API_KEY, "url_base": config.URL_BASE,
        "movies": db.query(Movie).count(), "series": db.query(Series).count(),
        "docker": os.path.exists("/.dockerenv"), "tools": _tools(),
    }


def _tools() -> dict:
    from ...core import mediainfo
    from ...services import unpack

    return {"mediainfo": mediainfo.tool(), "unpack": [k for k, v in unpack.tools().items() if v]}


@router.get("/system/updates")
def updates(force: bool = False):
    from ...services import updates as updates_svc

    return updates_svc.check(force)


@router.post("/system/apikey/regenerate")
def regen_key():
    return {"api_key": config.regenerate_api_key()}


@router.get("/system/health")
def health():
    return health_cache


@router.post("/system/health/refresh")
def health_refresh():
    commands.run_sync("health_check")
    return health_cache


@router.get("/system/tasks")
def tasks():
    return scheduler.status()


@router.post("/system/tasks/{name}/run")
def run_task(name: str):
    try:
        return scheduler.run_now(name)
    except StopIteration:
        raise HTTPException(404, "Unbekannte Aufgabe")


@router.get("/commands")
def list_commands():
    return list(commands.history)[:100]


@router.post("/commands")
def create_command(body: dict):
    name = body.get("name")
    try:
        return commands.enqueue(name, body.get("params") or {})
    except KeyError as e:
        raise HTTPException(400, str(e))


@router.get("/commands/{cid}")
def get_command(cid: int):
    c = commands.get(cid)
    if not c:
        raise HTTPException(404, "Befehl nicht gefunden")
    return c


@router.get("/system/logs")
def logs(level: str = "", since: int = 0, limit: int = 500):
    order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    lvl = order.get(level.upper(), 0)
    rows = [r for r in ring.records if r["id"] > since and order.get(r["level"], 0) >= lvl]
    return rows[-limit:][::-1]


@router.get("/events")
async def events(request: Request):
    q = subscribe()

    async def gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.to_thread(q.get, True, 15)
                    yield f"data: {msg}\n\n"
                except queue_mod.Empty:
                    yield ": ping\n\n"
        finally:
            unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache",
                                                                               "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------------------------ restart / backups
def _restart_later(delay: float = 1.0) -> None:
    """Replace the process with a fresh one (same PID, so Docker/tini keep running it)."""
    def run():
        time.sleep(delay)
        logging.getLogger("mediacraft").warning("Neustart…")
        if os.name == "nt":  # execv doesn't quote arguments with spaces on Windows
            import subprocess

            subprocess.Popen([sys.executable, "-m", "app.main"], cwd=os.getcwd())
            os._exit(0)
        os.execv(sys.executable, [sys.executable, "-m", "app.main"])

    threading.Thread(target=run, daemon=True, name="restart").start()


@router.post("/system/restart")
def restart():
    _restart_later()
    return {"ok": True}


@router.get("/system/backups")
def list_backups():
    return {"backups": backup_svc.list_backups(), "restore_pending": backup_svc.restore_pending(),
            "folder": str(backup_svc.backup_dir())}


@router.post("/system/backups")
def create_backup():
    return backup_svc.create_backup("manual")


@router.get("/system/backups/{name}")
def download_backup(name: str):
    try:
        p = backup_svc.backup_file(name)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "Backup nicht gefunden")
    return FileResponse(p, media_type="application/zip", filename=p.name)


@router.delete("/system/backups/{name}")
def delete_backup(name: str):
    try:
        backup_svc.delete_backup(name)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "Backup nicht gefunden")
    return {"ok": True}


@router.post("/system/backups/{name}/restore")
def restore_backup(name: str, restart_now: bool = True):
    try:
        backup_svc.stage_restore_from(name)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e) or "Backup nicht gefunden")
    if restart_now:
        _restart_later()
    return {"ok": True, "restarting": restart_now}


@router.post("/system/backups-upload/restore")
async def restore_upload(request: Request, restart_now: bool = True):
    data = await request.body()
    if len(data) > 2 * 1024 ** 3:
        raise HTTPException(413, "Datei zu groß")
    try:
        backup_svc.stage_restore(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if restart_now:
        _restart_later()
    return {"ok": True, "restarting": restart_now}


# ------------------------------------------------------------------------------------ settings
AUTH_PUBLIC = ("method", "username", "local_bypass")
SECTIONS = ("metadata", "media", "downloads", "indexers", "wanted", "backup", "importlists", "ui", "auth")


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    out = {s: settings_mod.get(db, s) for s in SECTIONS}
    out["auth"] = {k: v for k, v in out["auth"].items() if k in AUTH_PUBLIC}
    return out


@router.put("/settings/{section}")
def put_settings(section: str, body: dict, db: Session = Depends(get_db)):
    if section not in SECTIONS:
        raise HTTPException(404, "Unbekannter Bereich")
    if section == "auth":
        patch = {"method": body.get("method", "none"), "username": body.get("username", ""),
                 "local_bypass": bool(body.get("local_bypass", False))}
        if body.get("password"):
            patch["password_hash"] = hash_password(body["password"])
        current = settings_mod.get(db, "auth")
        if not current.get("secret"):
            patch["secret"] = secrets.token_hex(32)
        if patch["method"] == "forms" and not (patch.get("password_hash") or current.get("password_hash")):
            raise HTTPException(400, "Für Formular-Anmeldung muss ein Passwort gesetzt werden")
        res = settings_mod.update(db, "auth", patch)
        return {k: v for k, v in res.items() if k in AUTH_PUBLIC}
    return settings_mod.update(db, section, body)


# ------------------------------------------------------------------------------------ filesystem
@router.get("/filesystem")
def browse(path: str = "", include_files: bool = False):
    if not path:
        if os.name == "nt":
            drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
            return {"path": "", "parent": None, "dirs": [{"name": d, "path": d} for d in drives], "files": []}
        path = "/"
    if not os.path.isdir(path):
        raise HTTPException(404, "Ordner existiert nicht")
    dirs, files = [], []
    try:
        for e in sorted(os.scandir(path), key=lambda e: e.name.lower()):
            if e.name.startswith("."):
                continue
            if e.is_dir(follow_symlinks=True):
                dirs.append({"name": e.name, "path": e.path})
            elif include_files:
                files.append({"name": e.name, "path": e.path, "size": e.stat().st_size})
    except PermissionError:
        raise HTTPException(403, "Keine Berechtigung")
    norm = os.path.normpath(path)
    parent = os.path.dirname(norm)
    if parent == norm:  # filesystem / drive root
        parent = "" if os.name == "nt" else None
    free = None
    try:
        free = shutil.disk_usage(path).free
    except OSError:
        pass
    return {"path": path, "parent": parent, "dirs": dirs,
            "files": files, "free_space": free}


@router.get("/diskspace")
def diskspace(db: Session = Depends(get_db)):
    out, seen = [], set()
    for rf in db.query(RootFolder).all():
        try:
            u = shutil.disk_usage(rf.path)
        except OSError:
            continue
        key = (u.total, u.free)
        if key in seen:
            continue
        seen.add(key)
        out.append({"path": rf.path, "total": u.total, "free": u.free})
    return out
