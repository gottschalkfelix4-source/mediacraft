"""Recycle bin: replaced or deleted files/folders are moved there instead of being deleted.

An index file in the bin remembers where every entry came from, so it can be restored. Entries are
touched when they arrive – the clean-up after ``recycle_bin_days`` counts from the deletion, not from
the (often much older) file date.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone

log = logging.getLogger("recycle")

INDEX = ".mediacraft-recycle.json"
_lock = threading.Lock()


def _bin(cfg: dict) -> str | None:
    rb = (cfg.get("recycle_bin") or "").strip()
    return rb or None


def _load(rb: str) -> dict:
    try:
        with open(os.path.join(rb, INDEX), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(rb: str, index: dict) -> None:
    tmp = os.path.join(rb, INDEX + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1)
    os.replace(tmp, os.path.join(rb, INDEX))


def _touch(path: str) -> None:
    now = time.time()
    if os.path.isdir(path):
        for root, _dirs, files in os.walk(path):
            for n in files:
                try:
                    os.utime(os.path.join(root, n), (now, now))
                except OSError:
                    pass
    try:
        os.utime(path, (now, now))
    except OSError:
        pass


def _unique(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = (path, "") if os.path.isdir(path) else os.path.splitext(path)
    n = 1
    while os.path.exists(f"{base}.{n}{ext}"):
        n += 1
    return f"{base}.{n}{ext}"


def remove(path: str, cfg: dict) -> None:
    """Delete a file or folder – into the recycle bin when one is configured."""
    if not path or not os.path.exists(path):
        return
    rb = _bin(cfg)
    if not rb:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)
        return
    norm = os.path.normpath(path)
    # files keep their parent folder (series/movie name) so the bin stays readable
    rel = os.path.basename(norm) if os.path.isdir(norm) else os.path.join(os.path.basename(os.path.dirname(norm)),
                                                                          os.path.basename(norm))
    with _lock:
        os.makedirs(rb, exist_ok=True)
        target = _unique(os.path.join(rb, rel))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.move(norm, target)
        _touch(target)
        index = _load(rb)
        index[os.path.relpath(target, rb).replace("\\", "/")] = {
            "original": norm, "deleted": datetime.now(timezone.utc).isoformat()}
        _save(rb, index)
    log.info("In den Papierkorb verschoben: %s", norm)


def _size(p: str) -> int:
    if os.path.isfile(p):
        return os.path.getsize(p)
    return sum(os.path.getsize(os.path.join(r, f)) for r, _d, fs in os.walk(p) for f in fs)


def entries(cfg: dict) -> list[dict]:
    rb = _bin(cfg)
    if not rb or not os.path.isdir(rb):
        return []
    index = _load(rb)
    out = []
    for rel, info in index.items():
        p = os.path.join(rb, rel)
        if os.path.exists(p):
            out.append({"path": rel, "original": info.get("original"), "deleted": info.get("deleted"),
                        "size": _size(p), "folder": os.path.isdir(p)})
    known = {r.split("/")[0] for r in index}
    for name in os.listdir(rb):  # things put there by hand / older versions
        if name.startswith(".mediacraft-recycle") or name in known:
            continue
        p = os.path.join(rb, name)
        out.append({"path": name, "original": None, "size": _size(p), "folder": os.path.isdir(p),
                    "deleted": datetime.fromtimestamp(os.path.getmtime(p), timezone.utc).isoformat()})
    out.sort(key=lambda e: e["deleted"] or "", reverse=True)
    return out


def _resolve(rb: str, rel: str) -> str:
    p = os.path.normpath(os.path.join(rb, rel))
    if not p.startswith(os.path.normpath(rb) + os.sep):
        raise ValueError("Ungültiger Pfad")
    if not os.path.exists(p):
        raise FileNotFoundError(rel)
    return p


def _prune_empty(rb: str, folder: str) -> None:
    root = os.path.normpath(rb)
    folder = os.path.normpath(folder)
    while folder.startswith(root + os.sep) and os.path.isdir(folder) and not os.listdir(folder):
        os.rmdir(folder)
        folder = os.path.dirname(folder)


def restore(rel: str, cfg: dict) -> str:
    rb = _bin(cfg)
    if not rb:
        raise ValueError("Kein Papierkorb konfiguriert")
    with _lock:
        src = _resolve(rb, rel)
        index = _load(rb)
        original = (index.get(rel.replace("\\", "/")) or {}).get("original")
        if not original:
            raise ValueError("Ursprünglicher Ort unbekannt – bitte von Hand zurückkopieren")
        if os.path.exists(original):
            raise ValueError(f"Am ursprünglichen Ort existiert bereits etwas: {original}")
        os.makedirs(os.path.dirname(original), exist_ok=True)
        shutil.move(src, original)
        index.pop(rel.replace("\\", "/"), None)
        _save(rb, index)
        _prune_empty(rb, os.path.dirname(src))
    log.info("Aus dem Papierkorb wiederhergestellt: %s", original)
    return original


def delete(rel: str, cfg: dict) -> None:
    rb = _bin(cfg)
    if not rb:
        raise ValueError("Kein Papierkorb konfiguriert")
    with _lock:
        p = _resolve(rb, rel)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        index = _load(rb)
        index.pop(rel.replace("\\", "/"), None)
        _save(rb, index)
        _prune_empty(rb, os.path.dirname(p))


def empty(cfg: dict, older_than_days: int = 0) -> int:
    """Remove entries (all, or deleted more than ``older_than_days`` ago). Returns the number removed."""
    rb = _bin(cfg)
    if not rb or not os.path.isdir(rb):
        return 0
    cutoff = time.time() - older_than_days * 86400
    removed = 0
    with _lock:
        index = _load(rb)
        for name in os.listdir(rb):
            if name.startswith(".mediacraft-recycle"):
                continue
            p = os.path.join(rb, name)
            if os.path.isdir(p):
                # an entry can be a whole folder or single files inside a series/movie folder
                for root, dirs, files in os.walk(p, topdown=False):
                    for f in files:
                        fp = os.path.join(root, f)
                        if not older_than_days or os.path.getmtime(fp) < cutoff:
                            os.remove(fp)
                            removed += 1
                    for d in dirs:
                        dp = os.path.join(root, d)
                        if not os.listdir(dp):
                            os.rmdir(dp)
                if not os.listdir(p):
                    os.rmdir(p)
            elif not older_than_days or os.path.getmtime(p) < cutoff:
                os.remove(p)
                removed += 1
        index = {k: v for k, v in index.items() if os.path.exists(os.path.join(rb, k))}
        _save(rb, index)
    return removed
