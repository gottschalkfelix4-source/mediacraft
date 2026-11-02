"""Decision engine: is a release acceptable for a movie/episodes and how good is it?"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..indexers import usage
from ..indexers.newznab import Release
from ..models import Blocklist, CustomFormat, Episode, Indexer, MediaFile, Movie, QualityProfile, QueueItem, Series, utcnow
from . import customformats, qualities
from . import settings as settings_mod
from .parser import ParsedRelease, normalize_title, parse, title_variants

ACTIVE_QUEUE = ("grabbed", "queued", "downloading", "paused", "completed", "importing", "warning", "import_blocked")


@dataclass
class Decision:
    release: Release
    parsed: ParsedRelease
    approved: bool = True
    rejections: list[str] = field(default_factory=list)
    temporary: bool = False  # only rejected for a temporary reason (limit, queue)
    quality: str = "Unknown"
    quality_rank: int = -1
    format_score: int = 0
    formats: list[str] = field(default_factory=list)
    language_match: bool = True
    episode_ids: list[int] = field(default_factory=list)
    movie_id: Optional[int] = None
    series_id: Optional[int] = None
    language_first: bool = False

    def reject(self, reason: str, temporary: bool = False) -> None:
        if self.approved:
            self.temporary = temporary
        else:
            self.temporary = self.temporary and temporary
        self.approved = False
        self.rejections.append(reason)

    def sort_key(self) -> tuple:
        r = self.release
        seeders = r.seeders or 0
        return (
            1 if (self.language_match or not self.language_first) else 0,
            self.quality_rank,
            self.parsed.revision + self.parsed.real,
            self.format_score,
            len(self.episode_ids),
            -r.indexer_priority,
            min(seeders, 100) if r.protocol == "torrent" else 100,
            -r.age_hours if r.protocol == "torrent" else 0,
        )

    def to_dict(self) -> dict:
        return {
            "release": self.release.to_dict(), "parsed": self.parsed.to_dict(), "approved": self.approved,
            "rejections": self.rejections, "temporary": self.temporary, "quality": self.quality,
            "format_score": self.format_score, "formats": self.formats, "language_match": self.language_match,
            "episode_ids": self.episode_ids, "movie_id": self.movie_id, "series_id": self.series_id,
        }


class Context:
    """Data loaded once per search run."""

    def __init__(self, db: Session, manual: bool = False):
        self.db = db
        self.manual = manual
        self.idx_settings = settings_mod.get(db, "indexers")
        self.media_settings = settings_mod.get(db, "media")
        self.formats = [cf.to_dict() for cf in db.query(CustomFormat).all()]
        self.profiles = {p.id: p for p in db.query(QualityProfile).all()}
        self.indexers = {i.id: i for i in db.query(Indexer).all()}
        bl = db.query(Blocklist).all()
        self.blocked_guids = {b.guid for b in bl if b.guid}
        self.blocked_hashes = {b.info_hash.lower() for b in bl if b.info_hash}
        self.blocked_titles = {(b.movie_id, b.series_id, b.source_title) for b in bl}
        self.queue = db.query(QueueItem).filter(QueueItem.status.in_(ACTIVE_QUEUE)).all()
        self._grab_ok: dict[int, bool] = {}

    def grab_allowed(self, indexer_id: int) -> bool:
        if indexer_id not in self._grab_ok:
            idx = self.indexers.get(indexer_id)
            self._grab_ok[indexer_id] = idx is None or usage.can(self.db, idx, "grab", manual=self.manual)
        return self._grab_ok[indexer_id]


# ------------------------------------------------------------------------------------------ helpers
def _lang_match(profile: QualityProfile, languages: list[str]) -> bool:
    want = [l.lower() for l in (profile.languages or [])]
    if not want:
        return True
    return any(l in languages for l in want) or ("multi" in languages and "original" in want)


def file_rank(profile: QualityProfile, f: MediaFile | QueueItem, upgrade_propers: bool = True) -> tuple:
    revision = getattr(f, "proper", 0) if upgrade_propers else 0
    return (
        1 if _lang_match(profile, f.languages or []) or profile.language_mode != "prefer" else 0,
        qualities.profile_rank(profile.items, f.quality),
        revision,
        f.format_score or 0,
    )


def cutoff_met(profile: QualityProfile, f: MediaFile) -> bool:
    if not profile.upgrade_allowed:
        return True
    cutoff_rank = qualities.profile_rank(profile.items, profile.cutoff)
    q_rank = qualities.profile_rank(profile.items, f.quality)
    if q_rank == -1:  # quality no longer in profile -> upgrade wanted
        return False
    if q_rank < cutoff_rank:
        return False
    if (f.format_score or 0) < (profile.cutoff_format_score or 0):
        return False
    if profile.languages and profile.language_mode == "prefer" and not _lang_match(profile, f.languages or []):
        return False
    return True


def _common_checks(ctx: Context, d: Decision, profile: QualityProfile, runtime: Optional[int], ep_count: int = 1) -> None:
    r, p = d.release, d.parsed
    d.quality = p.quality
    d.quality_rank = qualities.profile_rank(profile.items, p.quality)
    d.format_score, d.formats = customformats.evaluate(ctx.formats, profile.format_scores or {}, p, r.size,
                                                       r.protocol, r.flags)
    d.language_match = _lang_match(profile, p.languages)
    d.language_first = profile.language_mode == "prefer" and bool(profile.languages)

    if d.quality_rank < 0:
        d.reject(f"Qualität {p.quality} ist im Profil '{profile.name}' nicht erlaubt")
    if profile.languages and profile.language_mode == "require" and not d.language_match:
        d.reject(f"Sprache {', '.join(p.languages)} entspricht nicht {', '.join(profile.languages)}")
    if d.format_score < (profile.min_format_score or 0):
        d.reject(f"Custom-Format-Score {d.format_score} < Minimum {profile.min_format_score}")
    title_l = r.title.lower()
    for term in profile.required_terms or []:
        if term and term.lower() not in title_l:
            d.reject(f"Pflichtbegriff '{term}' fehlt")
            break
    for term in profile.ignored_terms or []:
        if term and term.lower() in title_l:
            d.reject(f"Enthält ausgeschlossenen Begriff '{term}'")
            break
    # size
    q = qualities.get(p.quality)
    max_mb = ctx.idx_settings.get("maximum_size_mb") or 0
    size_mb = r.size / 1024 / 1024
    if max_mb and size_mb > max_mb:
        d.reject(f"Größe {size_mb:.0f} MB > Maximum {max_mb} MB")
    if r.size and runtime:
        per_min = size_mb / (runtime * max(ep_count, 1))
        defs = ctx.media_settings.get("quality_sizes", {}).get(p.quality, {})
        mn, mx = defs.get("min", q.min_mb_min), defs.get("max", q.max_mb_min)
        if mn and per_min < mn:
            d.reject(f"Zu klein: {per_min:.1f} MB/min < {mn} MB/min")
        if mx and per_min > mx:
            d.reject(f"Zu groß: {per_min:.1f} MB/min > {mx} MB/min")
    if r.size == 0 and r.protocol == "usenet":
        pass  # some indexers omit sizes
    # age / retention / seeders
    min_age = ctx.idx_settings.get("minimum_age_minutes") or 0
    if r.protocol == "usenet" and min_age and r.age_hours * 60 < min_age:
        d.reject(f"Zu neu ({r.age_hours * 60:.0f} min < {min_age} min)", temporary=True)
    ret = ctx.idx_settings.get("retention_days") or 0
    if r.protocol == "usenet" and ret and r.age_hours / 24 > ret:
        d.reject(f"Älter als Retention ({r.age_hours / 24:.0f} Tage)")
    idx = ctx.indexers.get(r.indexer_id)
    if r.protocol == "torrent" and idx and r.seeders is not None and r.seeders < (idx.minimum_seeders or 0):
        d.reject(f"Zu wenige Seeder ({r.seeders})")
    # blocklist
    if r.guid in ctx.blocked_guids or (r.info_hash and r.info_hash.lower() in ctx.blocked_hashes) or \
            (d.movie_id, d.series_id, r.title) in ctx.blocked_titles:
        d.reject("Release ist auf der Blocklist")
    # indexer limits
    if not ctx.grab_allowed(r.indexer_id):
        d.reject(f"Grab-Limit von {r.indexer} erreicht", temporary=True)


def _upgrade_check(ctx: Context, d: Decision, profile: QualityProfile, existing: MediaFile | None, label: str) -> None:
    if not existing:
        return
    if not profile.upgrade_allowed:
        d.reject(f"{label}: Datei vorhanden, Upgrades deaktiviert")
        return
    if cutoff_met(profile, existing):
        d.reject(f"{label}: Cutoff bereits erreicht ({existing.quality})")
        return
    up_propers = ctx.media_settings.get("upgrade_propers", True)
    new = (1 if d.language_match or profile.language_mode != "prefer" else 0, d.quality_rank,
           d.parsed.revision if up_propers else 0, d.format_score)
    old = file_rank(profile, existing, up_propers)
    if new <= old:
        d.reject(f"{label}: Vorhandene Datei ({existing.quality}, Score {existing.format_score}) ist gleichwertig oder besser")


def _queue_check(ctx: Context, d: Decision, profile: QualityProfile, movie_id=None, episode_ids=()) -> None:
    for q in ctx.queue:
        if movie_id and q.movie_id == movie_id or (episode_ids and set(q.episode_ids or []) & set(episode_ids)):
            new = (d.quality_rank, d.parsed.revision, d.format_score)
            old = (qualities.profile_rank(profile.items, q.quality), 0, q.format_score or 0)
            if new <= old or q.status not in ("grabbed", "queued", "downloading", "paused"):
                d.reject(f"Bereits in der Warteschlange: {q.title}", temporary=True)
                return


# ------------------------------------------------------------------------------------------ movies
def movie_title_matches(movie: Movie, p: ParsedRelease, r: Release | None = None) -> bool:
    if r and (r.imdb_id and movie.imdb_id and r.imdb_id == movie.imdb_id or
              r.tmdb_id and movie.tmdb_id and r.tmdb_id == movie.tmdb_id):
        return True
    names = set()
    for t in [movie.title, movie.original_title, *(movie.alt_titles or [])]:
        if t:
            names |= title_variants(t)
    if p.clean_title not in names:
        return False
    if p.year and movie.year and abs(p.year - movie.year) > 1:
        return False
    return True


def movie_available(movie: Movie, now: Optional[datetime] = None) -> bool:
    now = now or utcnow()
    if movie.minimum_availability == "announced":
        return True
    if movie.minimum_availability == "in_cinemas":
        return bool(movie.in_cinemas and movie.in_cinemas <= now) or movie.status == "released"
    released = [d for d in (movie.digital_release, movie.physical_release) if d]
    if released:
        return min(released) <= now
    if movie.in_cinemas:
        return movie.in_cinemas + timedelta(days=90) <= now
    return movie.status == "released"


def evaluate_movie(ctx: Context, movie: Movie, r: Release, p: ParsedRelease | None = None) -> Decision:
    p = p or parse(r.title)
    d = Decision(release=r, parsed=p, movie_id=movie.id)
    profile = ctx.profiles[movie.quality_profile_id]
    if p.is_tv and not (r.imdb_id and r.imdb_id == movie.imdb_id):
        d.reject("Release ist eine Serie")
    if not movie_title_matches(movie, p, r):
        d.reject(f"Titel passt nicht ('{p.title}' {p.year or ''})")
    if not ctx.manual and not movie.monitored:
        d.reject("Film wird nicht überwacht")
    if not ctx.manual and not movie_available(movie):
        d.reject(f"Film noch nicht verfügbar (Mindestverfügbarkeit: {movie.minimum_availability})", temporary=True)
    _common_checks(ctx, d, profile, movie.runtime or 110)
    _upgrade_check(ctx, d, profile, movie.file, "Film")
    _queue_check(ctx, d, profile, movie_id=movie.id)
    return d


# ------------------------------------------------------------------------------------------ series
def series_title_matches(series: Series, p: ParsedRelease, r: Release | None = None) -> bool:
    if r and r.tvdb_id and series.tvdb_id:
        return r.tvdb_id == series.tvdb_id
    if r and r.tvmaze_id and series.tvmaze_id:
        return r.tvmaze_id == series.tvmaze_id
    names = set()
    for t in [series.title, series.original_title, *(series.alt_titles or [])]:
        if t:
            names |= title_variants(t)
            if series.year:
                names.add(normalize_title(f"{t} {series.year}"))
    clean = p.clean_title
    if p.year and clean + str(p.year) in names:
        return True
    if clean in names:
        return not (p.year and series.year and abs(p.year - series.year) > 1 and normalize_title(f"{series.title} {p.year}") not in names)
    return False


def map_episodes(series: Series, p: ParsedRelease, episodes: list[Episode] | None = None) -> list[Episode]:
    eps = episodes if episodes is not None else list(series.episodes)
    if p.air_date:
        return [e for e in eps if e.air_date == p.air_date]
    if p.absolute_episodes and not p.episodes:
        wanted = set(p.absolute_episodes)
        found = [e for e in eps if e.absolute_number in wanted]
        if not found and series.series_type == "anime":
            # providers without absolute numbering (single season anime): fall back to season 1
            found = [e for e in eps if e.season == 1 and e.number in wanted]
        return found
    if p.full_season:
        seasons = set(p.seasons)
        return [e for e in eps if e.season in seasons]
    if p.seasons and p.episodes:
        s = p.seasons[0]
        wanted = set(p.episodes)
        found = [e for e in eps if e.season == s and e.number in wanted]
        if not found and series.series_type == "anime":
            found = [e for e in eps if e.absolute_number in wanted]
        return found
    return []


def evaluate_episodes(ctx: Context, series: Series, r: Release, p: ParsedRelease | None = None,
                      target_ids: set[int] | None = None) -> Decision:
    p = p or parse(r.title)
    d = Decision(release=r, parsed=p, series_id=series.id)
    profile = ctx.profiles[series.quality_profile_id]
    if not p.is_tv:
        d.reject("Keine Episoden-/Staffelangabe erkannt")
        _common_checks(ctx, d, profile, None)
        return d
    if not series_title_matches(series, p, r):
        d.reject(f"Serientitel passt nicht ('{p.title}')")
    eps = map_episodes(series, p)
    d.episode_ids = [e.id for e in eps]
    if not eps:
        d.reject("Keine passenden Episoden gefunden")
    if target_ids is not None and eps and not (set(d.episode_ids) & target_ids):
        d.reject("Enthält keine der gesuchten Episoden")
    now = utcnow()
    if eps and not ctx.manual:
        if not series.monitored:
            d.reject("Serie wird nicht überwacht")
        monitored = [e for e in eps if e.monitored]
        if not monitored:
            d.reject("Keine der Episoden wird überwacht")
    unaired = [e for e in eps if not e.aired(now + timedelta(hours=1))]
    if unaired:
        d.reject(f"{len(unaired)} Episode(n) noch nicht ausgestrahlt", temporary=True)
    _common_checks(ctx, d, profile, series.runtime or (eps[0].runtime if eps and eps[0].runtime else 45), max(len(eps), 1))
    # every episode that already has a file must be upgraded by this release (also for season packs)
    for e in eps:
        if e.file:
            before = len(d.rejections)
            _upgrade_check(ctx, d, profile, e.file, f"S{e.season:02d}E{e.number:02d}")
            if len(d.rejections) > before:
                break
    _queue_check(ctx, d, profile, episode_ids=d.episode_ids)
    return d


def rank(decisions: list[Decision], approved_only: bool = True) -> list[Decision]:
    lst = [d for d in decisions if d.approved] if approved_only else list(decisions)
    lst.sort(key=lambda d: (d.approved, d.sort_key()), reverse=True)
    return lst
