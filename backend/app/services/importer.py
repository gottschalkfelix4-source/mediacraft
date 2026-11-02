"""Importing finished downloads (or arbitrary files) into the library: hardlink/copy/move,
renaming, upgrades (old file -> recycle bin), extra files and history."""
from __future__ import annotations

import errno
import logging
import os
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..core import customformats, naming
from ..core import settings as settings_mod
from ..core.decision import map_episodes, movie_title_matches, series_title_matches
from ..core.events import publish
from ..core.parser import VIDEO_EXTENSIONS, ParsedRelease, parse, parse_path
from ..models import Episode, History, MediaFile, Movie, QualityProfile, QueueItem, Series
from .notifications import notify

log = logging.getLogger("import")


class ImportError_(Exception):
    pass


# ------------------------------------------------------------------------------------- files
def video_files(path: str, sample_max_mb: int = 150) -> list[str]:
    p = Path(path)
    if p.is_file():
        return [str(p)] if p.suffix.lower() in VIDEO_EXTENSIONS else []
    out = []
    for f in p.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        low = f.name.lower()
        size_mb = f.stat().st_size / 1024 / 1024
        if ("sample" in low or "/sample" in str(f).lower().replace("\\", "/")) and size_mb < sample_max_mb:
            continue
        if re.search(r"\b(trailer|featurette|behind[ ._-]the[ ._-]scenes|deleted[ ._-]scenes?)\b", low):
            continue
        out.append(str(f))
    return sorted(out)


def _free_space_ok(dest_dir: str, size: int, min_free_mb: int) -> bool:
    try:
        probe = dest_dir
        while not os.path.exists(probe) and os.path.dirname(probe) != probe:
            probe = os.path.dirname(probe)
        free = shutil.disk_usage(probe).free
        return free - size > min_free_mb * 1024 * 1024
    except OSError:
        return True


# queue id -> {"done": bytes, "total": bytes} while a download is being imported (served by GET /queue)
import_progress: dict[int, dict] = {}
_tracking = threading.local()


class _ImportTracker:
    """Counts transferred bytes of a download's video files and announces progress (max. 2x per second)."""

    def __init__(self, qid: int, files: list[str]):
        self.qid, self.files = qid, set(files)
        self.total = sum(os.path.getsize(f) for f in files) or 1
        self.done, self._last = 0, 0.0
        import_progress[qid] = {"done": 0, "total": self.total}
        publish("queue.updated", {"id": qid})

    def add(self, n: int) -> None:
        self.done = min(self.done + n, self.total)
        import_progress[self.qid] = {"done": self.done, "total": self.total}
        now = time.monotonic()
        if now - self._last >= 0.5 or self.done >= self.total:
            self._last = now
            publish("queue.updated", {"id": self.qid})


def _copy(src: str, dest: str, report) -> None:
    """Chunked copy so the import progress can be shown; keeps timestamps/permissions like copy2."""
    with open(src, "rb") as fi, open(dest, "wb") as fo:
        while chunk := fi.read(8 << 20):
            fo.write(chunk)
            if report:
                report(len(chunk))
    shutil.copystat(src, dest)


def transfer(src: str, dest: str, mode: str, use_hardlinks: bool = True) -> str:
    """mode: move | copy. Copies try a hardlink first. Returns the method actually used."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        os.remove(dest)
    tracker = getattr(_tracking, "tracker", None)
    report = tracker.add if tracker and src in tracker.files else None
    if mode == "move":
        try:
            os.rename(src, dest)  # same filesystem: instant
            if report:
                report(os.path.getsize(dest))
            return "move"
        except OSError as e:
            if e.errno != errno.EXDEV:
                raise
        _copy(src, dest, report)
        os.remove(src)
        return "move"
    if use_hardlinks:
        try:
            os.link(src, dest)
            if report:
                report(os.path.getsize(dest))
            return "hardlink"
        except OSError as e:
            if e.errno not in (errno.EXDEV, errno.EPERM, errno.ENOTSUP, errno.EMLINK, errno.EACCES) and os.name != "nt":
                log.debug("Hardlink fehlgeschlagen (%s), kopiere", e)
    _copy(src, dest, report)
    return "copy"


def remove_old(db: Session, f: MediaFile, cfg: dict) -> None:
    if not f.path or not os.path.exists(f.path):
        return
    rb = cfg.get("recycle_bin")
    try:
        if rb:
            target = os.path.join(rb, os.path.basename(os.path.dirname(f.path)), os.path.basename(f.path))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(f.path, target)
        else:
            os.remove(f.path)
    except OSError as e:
        log.warning("Alte Datei konnte nicht entfernt werden: %s", e)


def _extras(src_video: str, dest_video: str, cfg: dict, mode: str) -> None:
    if not cfg.get("import_extra_files"):
        return
    exts = {"." + e.strip().lower() for e in cfg.get("extra_extensions", "").split(",") if e.strip()}
    src = Path(src_video)
    stem = src.stem
    dest_stem = os.path.splitext(dest_video)[0]
    candidates = list(src.parent.glob("*")) + list((src.parent / "Subs").glob("*")) if (src.parent / "Subs").is_dir() else list(src.parent.glob("*"))
    videos_in_folder = len([c for c in src.parent.iterdir() if c.suffix.lower() in VIDEO_EXTENSIONS])
    for f in candidates:
        if not f.is_file() or f.suffix.lower() not in exts:
            continue
        if f.suffix.lower() == ".nfo":
            continue  # scene nfos are useless for media servers
        if videos_in_folder > 1 and not f.stem.startswith(stem):
            continue
        suffix = f.stem[len(stem):] if f.stem.startswith(stem) else ""
        lang = re.search(r"\.(de|ger|german|deu|en|eng|english|forced|sdh|[a-z]{2,3})$", f.stem, re.I)
        if not suffix and lang:
            suffix = "." + lang.group(1).lower()
        try:
            transfer(str(f), f"{dest_stem}{suffix}{f.suffix.lower()}", "copy" if mode != "move" else "move",
                     cfg.get("use_hardlinks", True))
        except OSError as e:
            log.warning("Extra-Datei %s nicht importiert: %s", f, e)


def _file_info(p: ParsedRelease, release_name: Optional[str]) -> dict:
    return {"quality": p.quality, "revision": p.revision, "release_group": p.release_group, "edition": p.edition,
            "codec": p.codec, "hdr": p.hdr, "audio": p.audio, "audio_channels": p.audio_channels,
            "languages": p.languages, "release_name": release_name}


def _chmod(path: str, cfg: dict) -> None:
    if cfg.get("file_chmod") and os.name != "nt":
        try:
            os.chmod(path, int(str(cfg["file_chmod"]), 8))
        except (OSError, ValueError):
            pass


# ------------------------------------------------------------------------------------- movies
def movie_file_name(db: Session, movie: Movie, info: dict, ext: str) -> str:
    cfg = settings_mod.get(db, "media")
    if not cfg.get("rename", True) and info.get("original_file"):
        return info["original_file"]
    return naming.render(cfg["movie_file"], naming.movie_values(movie, info), cfg["colon_replacement"]) + ext


def import_movie_file(db: Session, movie: Movie, src: str, p: ParsedRelease, *, mode: str = "copy",
                      queue_item: Optional[QueueItem] = None, release_name: Optional[str] = None) -> MediaFile:
    cfg = settings_mod.get(db, "media")
    profile = db.get(QualityProfile, movie.quality_profile_id)
    size = os.path.getsize(src)
    if not _free_space_ok(movie.path, size, cfg.get("min_free_space_mb", 200)):
        raise ImportError_("Nicht genug freier Speicherplatz")
    if queue_item and queue_item.languages and p.languages == ["english"]:
        p.languages = queue_item.languages
    info = _file_info(p, release_name or (queue_item.title if queue_item else None))
    info["original_file"] = os.path.basename(src)
    dest = os.path.join(movie.path, movie_file_name(db, movie, info, os.path.splitext(src)[1].lower()))
    score, _ = customformats.score_for(db, profile, parse(release_name) if release_name else p, size)
    old = movie.file
    method = transfer(src, dest, mode, cfg.get("use_hardlinks", True))
    _chmod(dest, cfg)
    _extras(src, dest, cfg, mode)
    mf = MediaFile(media_type="movie", movie_id=movie.id, path=dest, size=size, quality=p.quality, proper=p.revision,
                   languages=p.languages, release_group=p.release_group, release_name=info["release_name"],
                   format_score=score, edition=p.edition,
                   media_info={"codec": p.codec, "hdr": p.hdr, "audio": p.audio, "channels": p.audio_channels})
    db.add(mf)
    db.flush()
    upgraded = old is not None
    if old:
        movie.file_id = None
        db.flush()
        if os.path.normcase(old.path) != os.path.normcase(dest):
            remove_old(db, old, cfg)
        db.delete(old)
    movie.file_id = mf.id
    event = "upgraded" if upgraded else "imported"
    db.add(History(event=event, media_type="movie", movie_id=movie.id, source_title=info["release_name"] or os.path.basename(src),
                   quality=p.quality, download_id=queue_item.download_id if queue_item else None,
                   indexer=queue_item.indexer_name if queue_item else None,
                   data={"path": dest, "method": method, "size": size, "languages": p.languages}))
    db.flush()
    log.info("Importiert (%s): %s → %s", method, os.path.basename(src), dest)
    publish("movie.updated", {"id": movie.id})
    notify("upgrade" if upgraded else "import", f"{movie.title} ({movie.year}) – {p.quality}",
           {"title": movie.title, "path": dest, "poster": (movie.images or {}).get("poster")})
    return mf


# ------------------------------------------------------------------------------------- episodes
def episode_dest(db: Session, series: Series, episodes: list[Episode], info: dict, ext: str) -> str:
    cfg = settings_mod.get(db, "media")
    first = min(episodes, key=lambda e: (e.season, e.number))
    folder = series.path
    if series.season_folder:
        if first.season == 0:
            folder = os.path.join(folder, cfg.get("specials_folder") or "Specials")
        else:
            folder = os.path.join(folder, naming.render(cfg["season_folder"], {"season": first.season}))
    if not cfg.get("rename", True) and info.get("original_file"):
        return os.path.join(folder, info["original_file"])
    template = {"daily": cfg["daily_file"], "anime": cfg["anime_file"]}.get(series.series_type, cfg["episode_file"])
    values = naming.episode_values(series, episodes, info, cfg.get("multi_episode_style", "extend"))
    return os.path.join(folder, naming.render_episode_file(template, values, cfg["colon_replacement"]) + ext)


def import_episode_file(db: Session, series: Series, episodes: list[Episode], src: str, p: ParsedRelease, *,
                        mode: str = "copy", queue_item: Optional[QueueItem] = None,
                        release_name: Optional[str] = None) -> MediaFile:
    cfg = settings_mod.get(db, "media")
    profile = db.get(QualityProfile, series.quality_profile_id)
    size = os.path.getsize(src)
    if not _free_space_ok(series.path, size, cfg.get("min_free_space_mb", 200)):
        raise ImportError_("Nicht genug freier Speicherplatz")
    if queue_item and queue_item.languages and p.languages == ["english"]:
        p.languages = queue_item.languages
    info = _file_info(p, release_name or (queue_item.title if queue_item else None))
    info["original_file"] = os.path.basename(src)
    dest = episode_dest(db, series, episodes, info, os.path.splitext(src)[1].lower())
    score, _ = customformats.score_for(db, profile, p, size)
    old_files = {e.file_id: e.file for e in episodes if e.file_id}
    method = transfer(src, dest, mode, cfg.get("use_hardlinks", True))
    _chmod(dest, cfg)
    _extras(src, dest, cfg, mode)
    mf = MediaFile(media_type="episode", series_id=series.id, path=dest, size=size, quality=p.quality,
                   proper=p.revision, languages=p.languages, release_group=p.release_group,
                   release_name=info["release_name"], format_score=score,
                   media_info={"codec": p.codec, "hdr": p.hdr, "audio": p.audio, "channels": p.audio_channels})
    db.add(mf)
    db.flush()
    for e in episodes:
        e.file_id = mf.id
    db.flush()
    for fid, f in old_files.items():
        still_used = db.query(Episode).filter(Episode.file_id == fid).count()
        if f and not still_used:
            if os.path.normcase(f.path) != os.path.normcase(dest):
                remove_old(db, f, cfg)
            db.delete(f)
    upgraded = bool(old_files)
    label = ", ".join(f"S{e.season:02d}E{e.number:02d}" for e in sorted(episodes, key=lambda e: (e.season, e.number)))
    db.add(History(event="upgraded" if upgraded else "imported", media_type="series", series_id=series.id,
                   episode_ids=[e.id for e in episodes], source_title=info["release_name"] or os.path.basename(src),
                   quality=p.quality, download_id=queue_item.download_id if queue_item else None,
                   indexer=queue_item.indexer_name if queue_item else None,
                   data={"path": dest, "method": method, "size": size, "languages": p.languages}))
    db.flush()
    log.info("Importiert (%s): %s %s → %s", method, series.title, label, dest)
    publish("series.updated", {"id": series.id})
    notify("upgrade" if upgraded else "import", f"{series.title} {label} – {p.quality}",
           {"title": series.title, "path": dest, "poster": (series.images or {}).get("poster")})
    return mf


# ------------------------------------------------------------------------------------- downloads
def process_download(db: Session, q: QueueItem, path: str, mode: str) -> tuple[bool, list[str]]:
    """Import a finished download. Returns (fully_imported, messages)."""
    cfg = settings_mod.get(db, "media")
    files = video_files(path, cfg.get("sample_max_mb", 150)) if path and os.path.exists(path) else []
    if q.media_type == "movie" and files:
        files = [max(files, key=os.path.getsize)]  # only the main file is imported
    _tracking.tracker = _ImportTracker(q.id, files) if files else None
    try:
        return _process_download(db, q, path, mode)
    finally:
        _tracking.tracker = None
        import_progress.pop(q.id, None)


def _process_download(db: Session, q: QueueItem, path: str, mode: str) -> tuple[bool, list[str]]:
    cfg = settings_mod.get(db, "media")
    if not path or not os.path.exists(path):
        return False, [f"Pfad nicht gefunden: {path} (Remote-Path-Mapping prüfen)"]
    files = video_files(path, cfg.get("sample_max_mb", 150))
    if not files:
        return False, ["Keine Videodateien im Download gefunden"]
    messages: list[str] = []
    if q.media_type == "movie":
        movie = db.get(Movie, q.movie_id)
        if not movie:
            return False, ["Film existiert nicht mehr in der Bibliothek"]
        src = max(files, key=os.path.getsize)
        p = parse_path(src)
        rp = parse(q.title)
        if p.quality == "Unknown" or rp.quality != "Unknown":
            p.quality, p.source, p.resolution = rp.quality, rp.source, rp.resolution
            p.revision = max(p.revision, rp.revision)
        p.languages = rp.languages if rp.languages != ["english"] else p.languages
        p.release_group = p.release_group or rp.release_group
        p.edition = p.edition or rp.edition
        try:
            import_movie_file(db, movie, src, p, mode=mode, queue_item=q, release_name=q.title)
        except (OSError, ImportError_) as e:
            return False, [f"Import fehlgeschlagen: {e}"]
        return True, messages

    series = db.get(Series, q.series_id)
    if not series:
        return False, ["Serie existiert nicht mehr in der Bibliothek"]
    rp = parse(q.title)
    allowed = set(q.episode_ids or [])
    imported_any, missing = False, set(allowed)
    for src in files:
        p = parse_path(src)
        if not p.is_tv or not (p.episodes or p.absolute_episodes or p.air_date):
            # file without episode info inside a single-episode release
            if len(files) == 1 and rp.is_tv and (rp.episodes or rp.absolute_episodes or rp.air_date):
                p = rp
            else:
                messages.append(f"{os.path.basename(src)}: keine Episodennummer erkannt")
                continue
        eps = map_episodes(series, p)
        if allowed:
            eps = [e for e in eps if e.id in allowed] or eps
        if not eps:
            messages.append(f"{os.path.basename(src)}: keine passende Episode")
            continue
        if p.quality == "Unknown" and rp.quality != "Unknown":
            p.quality, p.source, p.resolution = rp.quality, rp.source, rp.resolution
        if rp.languages != ["english"]:
            p.languages = rp.languages
        p.release_group = p.release_group or rp.release_group
        try:
            import_episode_file(db, series, eps, src, p, mode=mode, queue_item=q, release_name=q.title)
            imported_any = True
            missing -= {e.id for e in eps}
        except (OSError, ImportError_) as e:
            messages.append(f"{os.path.basename(src)}: {e}")
    if missing:
        messages.append(f"{len(missing)} erwartete Episode(n) nicht im Download gefunden")
    return imported_any and not [m for m in messages if "fehlgeschlagen" in m], messages


# ------------------------------------------------------------------------------------- manual import
def scan_for_manual_import(db: Session, path: str) -> list[dict]:
    """Suggest a mapping for every video file below ``path``."""
    from ..core.parser import normalize_title

    cfg = settings_mod.get(db, "media")
    files = video_files(path, cfg.get("sample_max_mb", 150))
    movies = db.query(Movie).all()
    series_all = db.query(Series).all()
    out = []
    for f in files:
        p = parse_path(f)
        item: dict = {"path": f, "size": os.path.getsize(f), "parsed": p.to_dict(), "quality": p.quality,
                      "languages": p.languages, "movie_id": None, "series_id": None, "episode_ids": [], "rejections": []}
        if p.is_tv:
            s = next((s for s in series_all if series_title_matches(s, p)), None)
            if s:
                item["series_id"] = s.id
                item["episode_ids"] = [e.id for e in map_episodes(s, p)]
                if not item["episode_ids"]:
                    item["rejections"].append("Episode nicht gefunden")
            else:
                item["rejections"].append(f"Serie '{p.title}' nicht in der Bibliothek")
        else:
            m = next((m for m in movies if movie_title_matches(m, p)), None)
            if m:
                item["movie_id"] = m.id
            else:
                item["rejections"].append(f"Film '{p.title}' nicht in der Bibliothek")
        out.append(item)
    return out


def manual_import(db: Session, items: list[dict], mode: str = "copy") -> list[dict]:
    results = []
    for it in items:
        try:
            p = parse_path(it["path"])
            if it.get("quality"):
                p.quality = it["quality"]
            if it.get("languages"):
                p.languages = it["languages"]
            if it.get("movie_id"):
                movie = db.get(Movie, it["movie_id"])
                import_movie_file(db, movie, it["path"], p, mode=mode)
            elif it.get("series_id") and it.get("episode_ids"):
                series = db.get(Series, it["series_id"])
                eps = [db.get(Episode, i) for i in it["episode_ids"]]
                import_episode_file(db, series, [e for e in eps if e], it["path"], p, mode=mode)
            else:
                raise ImportError_("Keine Zuordnung angegeben")
            results.append({"path": it["path"], "ok": True})
        except Exception as e:
            results.append({"path": it["path"], "ok": False, "error": str(e)})
    return results


# ------------------------------------------------------------------------------------- rename
def rename_preview(db: Session, movie: Movie | None = None, series: Series | None = None) -> list[dict]:
    out = []
    if movie and movie.file:
        f = movie.file
        p = parse(f.release_name) if f.release_name else parse_path(f.path)
        info = {**_file_info(p, f.release_name), "quality": f.quality, "revision": f.proper,
                "languages": f.languages, "release_group": f.release_group, "edition": f.edition}
        new = os.path.join(movie.path, movie_file_name(db, movie, info, os.path.splitext(f.path)[1]))
        if os.path.normcase(new) != os.path.normcase(f.path):
            out.append({"file_id": f.id, "existing": f.path, "new": new})
    if series:
        by_file: dict[int, list[Episode]] = {}
        for e in series.episodes:
            if e.file_id:
                by_file.setdefault(e.file_id, []).append(e)
        for fid, eps in by_file.items():
            f = db.get(MediaFile, fid)
            p = parse(f.release_name) if f.release_name else parse_path(f.path)
            info = {**_file_info(p, f.release_name), "quality": f.quality, "revision": f.proper,
                    "languages": f.languages, "release_group": f.release_group}
            new = episode_dest(db, series, eps, info, os.path.splitext(f.path)[1])
            if os.path.normcase(new) != os.path.normcase(f.path):
                out.append({"file_id": f.id, "existing": f.path, "new": new})
    return out


def rename_apply(db: Session, movie: Movie | None = None, series: Series | None = None) -> int:
    n = 0
    for r in rename_preview(db, movie, series):
        f = db.get(MediaFile, r["file_id"])
        try:
            os.makedirs(os.path.dirname(r["new"]), exist_ok=True)
            shutil.move(r["existing"], r["new"])
            old_dir = os.path.dirname(r["existing"])
            f.path = r["new"]
            n += 1
            db.add(History(event="renamed", media_type="movie" if movie else "series",
                           movie_id=movie.id if movie else None, series_id=series.id if series else None,
                           source_title=os.path.basename(r["existing"]), data=r))
            if not os.listdir(old_dir):
                os.rmdir(old_dir)
        except OSError as e:
            log.warning("Umbenennen fehlgeschlagen: %s", e)
    db.flush()
    return n
