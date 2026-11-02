"""Runtime configuration: environment variables + a small persisted config file."""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

VERSION = "1.0.0"
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
