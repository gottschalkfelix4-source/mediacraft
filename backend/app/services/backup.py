"""Backups of the database and config.json as zip files in /config/backups.

A backup is a consistent SQLite copy (online backup API, works while MediaCraft runs) plus config.json.
Restoring stages the zip as ``restore_pending.zip``; it is applied on the next start (see config.py),
because the open database cannot be swapped underneath the running process.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import config

log = logging.getLogger("backup")

KINDS = ("manual", "scheduled", "migration", "restore")
_NAME = re.compile(r"^mediacraft_(manual|scheduled|migration|restore)_\d{8}_\d{6}(_\d+)?\.zip$")
SQLITE_MAGIC = b"SQLite format 3\x00"


def backup_dir() -> Path:
    d = config.CONFIG_DIR / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(name: str) -> Path:
    if not _NAME.match(name):
        raise ValueError("Ungültiger Backup-Name")
    p = backup_dir() / name
    if not p.is_file():
        raise FileNotFoundError(name)
    return p


def _info(p: Path) -> dict:
    m = _NAME.match(p.name)
    st = p.stat()
    return {"name": p.name, "kind": m.group(1) if m else "manual", "size": st.st_size,
            "created": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()}


def list_backups() -> list[dict]:
    files = [p for p in backup_dir().iterdir() if p.is_file() and _NAME.match(p.name)]
    return [_info(p) for p in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)]


def create_backup(kind: str = "manual") -> dict:
    if kind not in KINDS:
        raise ValueError(kind)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir() / f"mediacraft_{kind}_{stamp}.zip"
    n = 1
    while target.exists():
        target = backup_dir() / f"mediacraft_{kind}_{stamp}_{n}.zip"
        n += 1
    fd, tmp = tempfile.mkstemp(suffix=".db", dir=backup_dir())
    os.close(fd)
    try:
        src = sqlite3.connect(str(config.DB_PATH), timeout=30)
        dst = sqlite3.connect(tmp)
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
            src.close()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, "mediacraft.db")
            cfg = config.CONFIG_DIR / "config.json"
            if cfg.exists():
                z.write(cfg, "config.json")
            z.writestr("backup.json", json.dumps({"app": config.APP_NAME, "version": config.VERSION, "kind": kind,
                                                  "created": datetime.now(timezone.utc).isoformat()}))
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    log.info("Backup erstellt: %s", target.name)
    return _info(target)


def delete_backup(name: str) -> None:
    _path(name).unlink()


def backup_file(name: str) -> Path:
    return _path(name)


def validate(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
            if "mediacraft.db" not in names:
                raise ValueError("Die Datei enthält keine mediacraft.db")
            with z.open("mediacraft.db") as f:
                if f.read(16) != SQLITE_MAGIC:
                    raise ValueError("mediacraft.db im Backup ist keine SQLite-Datenbank")
    except zipfile.BadZipFile as e:
        raise ValueError("Keine gültige ZIP-Datei") from e


def stage_restore(data: bytes) -> None:
    """Validate and stage a backup; it replaces the database on the next start."""
    validate(data)
    pending = config.CONFIG_DIR / "restore_pending.zip"
    tmp = pending.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(pending)
    log.warning("Wiederherstellung vorgemerkt – wird beim nächsten Start angewendet")


def stage_restore_from(name: str) -> None:
    stage_restore(_path(name).read_bytes())


def restore_pending() -> bool:
    return (config.CONFIG_DIR / "restore_pending.zip").exists()


def prune(retention_days: int) -> int:
    """Remove scheduled/migration backups older than the retention; manual ones are kept."""
    if retention_days <= 0:
        return 0
    limit = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed = 0
    for b in list_backups():
        if b["kind"] in ("scheduled", "migration", "restore") and datetime.fromisoformat(b["created"]) < limit:
            try:
                (backup_dir() / b["name"]).unlink()
                removed += 1
            except OSError:
                pass
    return removed


def scheduled_backup(db) -> dict:
    from ..core import settings as settings_mod

    cfg = settings_mod.get(db, "backup")
    info = create_backup("scheduled")
    return {"backup": info["name"], "pruned": prune(int(cfg.get("retention_days") or 0))}
