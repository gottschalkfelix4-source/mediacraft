"""Update check against the GitHub repository: is the running build the newest one, and what changed since?

Images are built from every push to ``main``; the build carries its commit (MEDIACRAFT_COMMIT). The check
compares that commit with the head of ``main`` and lists the commit messages in between as changelog.
"""
from __future__ import annotations

import logging
import os
import threading
import time

import httpx

from .. import config

log = logging.getLogger("updates")
REPO = os.environ.get("MEDIACRAFT_REPO", "gottschalkfelix4-source/mediacraft")
API = f"https://api.github.com/repos/{REPO}"
CACHE_SECONDS = 6 * 3600
_cache: dict = {"at": 0.0, "data": None}
_lock = threading.Lock()


def _get(path: str):
    r = httpx.get(API + path, headers={"Accept": "application/vnd.github+json", "User-Agent": "MediaCraft"},
                  timeout=15, follow_redirects=True)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _commit(c: dict) -> dict:
    msg = (c.get("commit") or {}).get("message") or ""
    return {"sha": c.get("sha", "")[:7], "title": msg.split("\n", 1)[0], "body": msg.split("\n", 1)[1].strip() if "\n" in msg else "",
            "date": ((c.get("commit") or {}).get("committer") or {}).get("date"), "url": c.get("html_url")}


def current() -> dict:
    return {"version": config.VERSION, "build": config.BUILD, "commit": config.COMMIT[:7] if config.COMMIT else None,
            "build_date": config.BUILD_DATE, "repo": f"https://github.com/{REPO}"}


def check(force: bool = False) -> dict:
    with _lock:
        if not force and _cache["data"] and time.time() - _cache["at"] < CACHE_SECONDS:
            return _cache["data"]
    out = {"current": current(), "latest": None, "update_available": None, "changes": [], "error": None,
           "checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        head = _get("/commits/main")
        if head:
            out["latest"] = _commit(head)
        if config.COMMIT and head:
            if head["sha"].startswith(config.COMMIT) or config.COMMIT.startswith(head["sha"][:7]):
                out["update_available"] = False
            else:
                cmp = _get(f"/compare/{config.COMMIT}...main") or {}
                commits = cmp.get("commits") or []
                out["update_available"] = bool(commits) or cmp.get("status") in ("ahead", "diverged")
                out["changes"] = [_commit(c) for c in reversed(commits)][:50]
        else:  # development build: just show what happened recently
            out["changes"] = [_commit(c) for c in (_get("/commits?sha=main&per_page=15") or [])]
    except (httpx.HTTPError, ValueError) as e:
        out["error"] = f"GitHub nicht erreichbar: {e}"
        log.info("Update-Prüfung fehlgeschlagen: %s", e)
    with _lock:
        _cache.update(at=time.time(), data=out)
    return out
