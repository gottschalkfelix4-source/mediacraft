"""Runtime configuration: environment variables + a small persisted config file."""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

VERSION = os.environ.get("MEDIACRAFT_VERSION") or "1.1.0"
BUILD = os.environ.get("MEDIACRAFT_BUILD") or ""  # CI run number
COMMIT = os.environ.get("MEDIACRAFT_COMMIT") or ""  # git sha the image was built from
BUILD_DATE = os.environ.get("MEDIACRAFT_BUILD_DATE") or ""
APP_NAME = "MediaCraft"

CONFIG_DIR = Path(os.environ.get("MEDIACRAFT_CONFIG_DIR", "/config" if os.name != "nt" else "./config")).resolve()
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.environ.get("MEDIACRAFT_DB", CONFIG_DIR / "mediacraft.db"))
LOG_DIR = CONFIG_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

HOST = os.environ.get("MEDIACRAFT_HOST", "0.0.0.0")
PORT = int(os.environ.get("MEDIACRAFT_PORT", "7979"))
URL_BASE = os.environ.get("MEDIACRAFT_URL_BASE", "").rstrip("/")
STATIC_DIR = Path(os.environ.get("MEDIACRAFT_STATIC_DIR", Path(__file__).resolve().parent.parent / "static"))
DISABLE_SCHEDULER = os.environ.get("MEDIACRAFT_DISABLE_SCHEDULER", "") == "1"

_CONFIG_FILE = CONFIG_DIR / "config.json"


def _apply_pending_restore() -> None:
    """A restore staged via the UI replaces database + config.json before anything opens them."""
    pending = CONFIG_DIR / "restore_pending.zip"
    if not pending.exists():
        return
    import shutil
    import zipfile

    try:
        from .services import backup

        if DB_PATH.exists():
            backup.create_backup("restore")  # the state we are about to overwrite
        with zipfile.ZipFile(pending) as z:
            tmp = DB_PATH.with_suffix(".restoring")
            with z.open("mediacraft.db") as src, open(tmp, "wb") as dst:
                shutil.copyfileobj(src, dst)
            for suffix in ("-wal", "-shm"):
                Path(str(DB_PATH) + suffix).unlink(missing_ok=True)
            tmp.replace(DB_PATH)
            if "config.json" in z.namelist():
                _CONFIG_FILE.write_bytes(z.read("config.json"))
        pending.unlink()
        print("MediaCraft: Backup wiederhergestellt", flush=True)
    except Exception as e:  # keep the old database, but don't retry forever
        pending.replace(CONFIG_DIR / "restore_failed.zip")
        print(f"MediaCraft: Wiederherstellung fehlgeschlagen: {e}", flush=True)


_apply_pending_restore()


def _load() -> dict:
    if _CONFIG_FILE.exists():
        try:
            return json.loads(_CONFIG_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    tmp = _CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), "utf-8")
    tmp.replace(_CONFIG_FILE)


_file_config = _load()
if "api_key" not in _file_config:
    _file_config["api_key"] = os.environ.get("MEDIACRAFT_API_KEY") or secrets.token_hex(16)
    _save(_file_config)

API_KEY: str = os.environ.get("MEDIACRAFT_API_KEY") or _file_config["api_key"]


def regenerate_api_key() -> str:
    global API_KEY
    API_KEY = secrets.token_hex(16)
    _file_config["api_key"] = API_KEY
    _save(_file_config)
    return API_KEY
