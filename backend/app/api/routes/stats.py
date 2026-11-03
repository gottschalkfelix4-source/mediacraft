"""Library and activity statistics for the statistics page."""
from __future__ import annotations

import os
import shutil
from collections import Counter, defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import Episode, History, Indexer, IndexerEvent, MediaFile, Movie, RootFolder, Series, utcnow
from ..deps import require_auth

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_auth)])


def _top(counter: Counter, sizes: dict | None = None, limit: int = 12) -> list[dict]:
    rows = counter.most_common()
    out = [{"name": k or "unbekannt", "count": v, "size": int((sizes or {}).get(k, 0))} for k, v in rows[:limit]]
    rest = rows[limit:]
    if rest:
        out.append({"name": "Sonstige", "count": sum(v for _, v in rest),
                    "size": int(sum((sizes or {}).get(k, 0) for k, _ in rest))})
    return out


def _week_start(d):
    d = d.date() if hasattr(d, "date") else d
    return d - timedelta(days=d.weekday())


@router.get("/stats")
def stats(weeks: int = 12, db: Session = Depends(get_db)):
    now = utcnow()
    files = db.query(MediaFile).all()
    quality, quality_size = Counter(), defaultdict(int)
    langs, codecs, resolutions, groups = Counter(), Counter(), Counter(), Counter()
    by_type = {"movie": [0, 0], "episode": [0, 0]}
    for f in files:
        quality[f.quality] += 1
        quality_size[f.quality] += f.size or 0
        for lang in f.languages or ["unbekannt"]:
            langs[lang] += 1
        mi = f.media_info or {}
        probe = mi.get("probe") or {}
        codecs[probe.get("video_codec") or mi.get("codec") or "unbekannt"] += 1
        if probe.get("resolution"):
            resolutions[f"{probe['resolution']}p"] += 1
        if f.release_group:
            groups[f.release_group] += 1
        t = by_type.setdefault(f.media_type, [0, 0])
        t[0] += 1
        t[1] += f.size or 0

    # space per root folder: what MediaCraft stores there + what the disk has left
    roots = []
    for rf in db.query(RootFolder).all():
        prefix = os.path.normpath(rf.path)
        used = sum(f.size or 0 for f in files if os.path.normpath(f.path).startswith(prefix + os.sep))
        try:
            du = shutil.disk_usage(rf.path)
            total, free = du.total, du.free
        except OSError:
            total = free = None
        roots.append({"path": rf.path, "media_type": rf.media_type, "library_size": used, "total": total, "free": free})

    # activity per week
    since = now - timedelta(weeks=max(1, min(weeks, 52)))
    start = _week_start(since)
    week_keys = [(start + timedelta(weeks=i)).isoformat() for i in range(max(1, min(weeks, 52)) + 1)]
    names = {i.id: i.name for i in db.query(Indexer).all()}
    grabs_week = {k: 0 for k in week_keys}
    per_indexer: dict[str, dict] = {}
    for ev in db.query(IndexerEvent).filter(IndexerEvent.timestamp >= since,
                                            IndexerEvent.kind.in_(("grab", "query", "rss"))).all():
        name = names.get(ev.indexer_id, f"#{ev.indexer_id}")
        row = per_indexer.setdefault(name, {"name": name, "grabs": 0, "queries": 0, "failed": 0})
        if ev.kind == "grab":
            if ev.success:
                row["grabs"] += 1
                k = _week_start(ev.timestamp).isoformat()
                if k in grabs_week:
                    grabs_week[k] += 1
        else:
            row["queries"] += 1
        if not ev.success:
            row["failed"] += 1
    imports_week = {k: 0 for k in week_keys}
    failed_week = {k: 0 for k in week_keys}
    for h in db.query(History).filter(History.date >= since, History.event.in_(("imported", "upgraded", "failed"))).all():
        k = _week_start(h.date).isoformat()
        target = failed_week if h.event == "failed" else imports_week
        if k in target:
            target[k] += 1

    movies_total = db.query(Movie).count()
    movies_have = db.query(Movie).filter(Movie.file_id.isnot(None)).count()
    eps_total = db.query(Episode).filter(Episode.season > 0).count()
    eps_have = db.query(Episode).filter(Episode.season > 0, Episode.file_id.isnot(None)).count()
    return {
        "library": {
            "movies": movies_total, "movies_with_file": movies_have, "series": db.query(Series).count(),
            "episodes": eps_total, "episodes_with_file": eps_have,
            "movie_size": by_type["movie"][1], "episode_size": by_type["episode"][1],
            "total_size": int(db.query(func.sum(MediaFile.size)).scalar() or 0), "files": len(files),
        },
        "qualities": _top(quality, quality_size, 15),
        "languages": _top(langs),
        "codecs": _top(codecs, limit=8),
        "resolutions": _top(resolutions, limit=8),
        "release_groups": _top(groups, limit=10),
        "root_folders": roots,
        "weeks": [{"week": k, "grabs": grabs_week[k], "imports": imports_week[k], "failed": failed_week[k]}
                  for k in week_keys],
        "indexers": sorted(per_indexer.values(), key=lambda r: -r["grabs"]),
    }
