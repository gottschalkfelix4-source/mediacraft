"""Extracting packed downloads (RAR, multi-volume RAR, 7z, ZIP) before import.

Archives are extracted into ``_mediacraft_unpack`` inside the download folder. The extracted copy is ours
and is removed after the import; the archives themselves stay untouched (torrents keep seeding).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import zipfile

log = logging.getLogger("unpack")

UNPACK_DIR = "_mediacraft_unpack"
_PART = re.compile(r"\.part(\d+)\.rar$", re.I)
_SPLIT = re.compile(r"\.(\d{3})$")


class UnpackError(Exception):
    pass


def tools() -> dict[str, str | None]:
    return {name: shutil.which(name) for name in ("unrar", "7z", "7zz", "unar", "bsdtar")}


def first_volumes(folder: str) -> list[str]:
    """Archives to extract, one per set (part1 of multi-volume RARs, .001 of split archives)."""
    out = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d != UNPACK_DIR]
        names = set(f.lower() for f in files)
        for f in sorted(files):
            low = f.lower()
            path = os.path.join(root, f)
            if "sample" in low:
                continue
            m = _PART.search(low)
            if m:
                if int(m.group(1)) == 1:
                    out.append(path)
                continue
            if low.endswith((".rar", ".7z", ".zip")):
                out.append(path)
            elif _SPLIT.search(low) and low.endswith(".001") and low[:-4] not in names:
                out.append(path)
    return out


def _run(cmd: list[str], timeout: int) -> None:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as e:
        raise UnpackError("Entpacken hat zu lange gedauert") from e
    if r.returncode != 0:
        raise UnpackError((r.stderr or r.stdout or b"").decode("utf-8", "replace").strip()[-300:] or f"Exit {r.returncode}")


def extract(archive: str, dest: str, timeout: int = 3 * 3600) -> None:
    os.makedirs(dest, exist_ok=True)
    if archive.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(archive) as z:
                z.extractall(dest)
            return
        except (zipfile.BadZipFile, OSError) as e:
            raise UnpackError(str(e)) from e
    t = tools()
    if archive.lower().endswith(".rar") and t["unrar"]:
        return _run([t["unrar"], "x", "-o+", "-y", "-p-", archive, dest + os.sep], timeout)
    seven = t["7zz"] or t["7z"]
    if seven:
        return _run([seven, "x", "-y", "-p", f"-o{dest}", archive], timeout)
    if t["unar"]:
        return _run([t["unar"], "-f", "-q", "-p", "", "-o", dest, archive], timeout)
    if t["bsdtar"]:
        return _run([t["bsdtar"], "-xf", archive, "-C", dest], timeout)
    raise UnpackError("Kein Entpack-Programm gefunden (unrar, 7z, unar oder bsdtar)")


def unpack(folder: str) -> str | None:
    """Extract all archive sets below ``folder``; returns the folder with the extracted files (or None)."""
    if not os.path.isdir(folder):
        return None
    archives = first_volumes(folder)
    if not archives:
        return None
    dest = os.path.join(folder, UNPACK_DIR)
    for a in archives:
        log.info("Entpacke %s", a)
        extract(a, os.path.join(dest, os.path.splitext(os.path.basename(_PART.sub(".rar", a)))[0]))
    return dest


def cleanup(folder: str | None) -> None:
    if folder and os.path.basename(folder) == UNPACK_DIR and os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)
