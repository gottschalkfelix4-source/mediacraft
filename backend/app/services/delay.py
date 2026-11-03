"""Delay profiles: hold back automatic grabs for a while so a better release can still show up.

Only automatic grabs (search, RSS) are delayed; interactive grabs never are. Like in Sonarr the
waiting time counts from the release's publish date, and as soon as the first held release for an
item is due, the best release held for that item is grabbed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..core import decision as dec
from ..indexers.newznab import Release
from ..models import DelayProfile, Movie, PendingRelease, QualityProfile, Series, iso, utcnow

log = logging.getLogger("delay")


def profile_for(db: Session, tags: list[int] | None) -> Optional[DelayProfile]:
    profiles = db.query(DelayProfile).filter(DelayProfile.enabled.is_(True)).order_by(DelayProfile.order,
                                                                                       DelayProfile.id).all()
    tags_set = set(tags or [])
    return (next((p for p in profiles if p.tags and set(p.tags) & tags_set), None)
            or next((p for p in profiles if not p.tags), None))


def prefer(decisions: list[dec.Decision], profile: Optional[DelayProfile]) -> list[dec.Decision]:
    """Rank like ``decision.rank`` but, all else (language, quality, revision, score) equal, put the
    preferred protocol first."""
    pref = profile.preferred_protocol if profile else None

    def key(d: dec.Decision):
        k = d.sort_key()
        return (d.approved, *k[:4], 1 if d.release.protocol == pref else 0, *k[4:])

    return sorted(decisions, key=key, reverse=True)


def _highest_rank(profile: QualityProfile) -> int:
    return max((i for i, it in enumerate(profile.items or []) if it.get("allowed")), default=-1)


def _target_filter(db: Session, d: dec.Decision):
    q = db.query(PendingRelease)
    if d.movie_id:
        return [p for p in q.filter(PendingRelease.movie_id == d.movie_id).all()]
    ids = set(d.episode_ids)
    return [p for p in q.filter(PendingRelease.series_id == d.series_id).all() if set(p.episode_ids or []) & ids]


def hold(db: Session, d: dec.Decision, profile: Optional[DelayProfile], quality_profile: QualityProfile) -> bool:
    """True when ``d`` has to wait; it is then stored as a pending release."""
    if not profile:
        return False
    delay = profile.usenet_delay if d.release.protocol == "usenet" else profile.torrent_delay
    if not delay or delay <= 0:
        return False
    if profile.bypass_highest_quality and d.quality_rank >= _highest_rank(quality_profile):
        return False
    if profile.bypass_min_score is not None and d.format_score >= profile.bypass_min_score:
        return False
    age_min = (d.release.age_hours or 0) * 60
    if age_min >= delay:
        return False
    now = utcnow()
    existing = _target_filter(db, d)
    if any(p.release_at <= now for p in existing):
        return False  # the first held release for this item is due – grab the best one now
    release_at = now + timedelta(minutes=delay - age_min)
    pending = next((p for p in existing if p.indexer_id == d.release.indexer_id and p.guid == d.release.guid), None)
    if pending is None:
        pending = PendingRelease(media_type="movie" if d.movie_id else "series", movie_id=d.movie_id,
                                 series_id=d.series_id, indexer_id=d.release.indexer_id, guid=d.release.guid,
                                 protocol=d.release.protocol, release_at=release_at)
        db.add(pending)
        log.info("Zurückgestellt bis %s UTC (Delay-Profil): %s", release_at.strftime("%d.%m. %H:%M"), d.release.title)
    pending.episode_ids = list(d.episode_ids)
    pending.title = d.release.title
    pending.quality = d.quality
    pending.format_score = d.format_score
    pending.release = d.release.to_dict()
    pending.reason = f"{d.release.protocol}-Verzögerung {delay} min"
    db.flush()
    return True


def _release(data: dict) -> Release:
    r = Release(**{k: v for k, v in data.items() if k in Release.__dataclass_fields__})
    if r.publish_date:
        try:
            pub = datetime.fromisoformat(r.publish_date.replace("Z", "+00:00")).replace(tzinfo=None)
            r.age_hours = round(max(0.0, (utcnow() - pub).total_seconds() / 3600), 2)
        except ValueError:
            pass
    return r


def _evaluate(ctx: dec.Context, db: Session, p: PendingRelease, target_ids: set[int]) -> Optional[dec.Decision]:
    r = _release(p.release or {})
    if p.movie_id:
        m = db.get(Movie, p.movie_id)
        return dec.evaluate_movie(ctx, m, r) if m else None
    s = db.get(Series, p.series_id)
    return dec.evaluate_episodes(ctx, s, r, target_ids=target_ids) if s else None


def process_pending(db: Session, force_ids: set[int] | None = None) -> dict:
    """Grab the best held release of every item whose first held release is due (or forced)."""
    from .grab import grab_decision

    now = utcnow()
    pending = db.query(PendingRelease).all()
    due = [p for p in pending if p.release_at <= now or (force_ids and p.id in force_ids)]
    stats = {"pending": len(pending), "grabbed": 0, "processed": 0, "errors": []}
    if not due:
        return stats
    groups: dict[tuple, list[PendingRelease]] = {}
    for p in due:
        if p.movie_id:
            groups.setdefault(("movie", p.movie_id), [])
        else:
            groups.setdefault(("series", p.series_id), [])
    for (kind, tid), _ in groups.items():
        if kind == "movie":
            members = [p for p in pending if p.movie_id == tid]
        else:
            due_eps = {e for p in due if p.series_id == tid for e in (p.episode_ids or [])}
            members = [p for p in pending if p.series_id == tid and set(p.episode_ids or []) & due_eps]
        groups[(kind, tid)] = members
    ctx = dec.Context(db)
    for (kind, tid), members in groups.items():
        target = db.get(Movie if kind == "movie" else Series, tid)
        target_ids = {e for p in members for e in (p.episode_ids or [])}
        decisions = [d for d in (_evaluate(ctx, db, p, target_ids) for p in members) if d is not None]
        ranked = [d for d in prefer(decisions, profile_for(db, target.tags if target else [])) if d.approved]
        covered: set[int] = set()
        for d in ranked:
            if kind == "series" and set(d.episode_ids) <= covered:
                continue
            try:
                grab_decision(db, d)
                stats["grabbed"] += 1
                covered |= set(d.episode_ids)
                if kind == "movie":
                    break
            except Exception as e:
                stats["errors"].append(f"{d.release.title}: {e}")
        for p in members:
            db.delete(p)
            stats["processed"] += 1
    db.flush()
    return stats


def drop_stale(db: Session, days: int = 14) -> int:
    return db.query(PendingRelease).filter(PendingRelease.added < utcnow() - timedelta(days=days)).delete()


def pending_to_dict(db: Session, p: PendingRelease) -> dict:
    target = db.get(Movie, p.movie_id) if p.movie_id else db.get(Series, p.series_id)
    return {"id": p.id, "title": p.title, "media_type": p.media_type, "movie_id": p.movie_id, "series_id": p.series_id,
            "episode_ids": p.episode_ids, "target": target.title if target else "?", "protocol": p.protocol,
            "quality": p.quality, "format_score": p.format_score, "indexer": (p.release or {}).get("indexer"),
            "size": (p.release or {}).get("size", 0), "added": iso(p.added), "release_at": iso(p.release_at),
            "reason": p.reason}
