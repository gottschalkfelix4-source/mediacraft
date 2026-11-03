"""ORM models. Movies and series live side by side and share profiles, indexers and clients."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, BigInteger, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(64), unique=True)

    def to_dict(self):
        return {"id": self.id, "label": self.label}


class RootFolder(Base):
    __tablename__ = "root_folders"
    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(1024), unique=True)
    media_type: Mapped[str] = mapped_column(String(16), default="movie")  # movie | series | anime

    def to_dict(self):
        return {"id": self.id, "path": self.path, "media_type": self.media_type}


class QualityProfile(Base):
    __tablename__ = "quality_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    # ordered list (lowest -> highest) of {"quality": "WEBDL-1080p", "allowed": true}
    items: Mapped[list] = mapped_column(JSON, default=list)
    cutoff: Mapped[str] = mapped_column(String(32), default="WEBDL-1080p")
    upgrade_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    languages: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["german"]; empty = any
    language_mode: Mapped[str] = mapped_column(String(16), default="prefer")  # require | prefer
    format_scores: Mapped[dict] = mapped_column(JSON, default=dict)  # {custom_format_id: score}
    min_format_score: Mapped[int] = mapped_column(Integer, default=0)
    cutoff_format_score: Mapped[int] = mapped_column(Integer, default=0)
    required_terms: Mapped[list] = mapped_column(JSON, default=list)
    ignored_terms: Mapped[list] = mapped_column(JSON, default=list)

    def to_dict(self):
        return {c: getattr(self, c) for c in (
            "id", "name", "items", "cutoff", "upgrade_allowed", "languages", "language_mode", "format_scores",
            "min_format_score", "cutoff_format_score", "required_terms", "ignored_terms")}


class CustomFormat(Base):
    __tablename__ = "custom_formats"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    # [{"type": "title"|"group"|"source"|"resolution"|"language"|"codec"|"size"|"edition"|"hdr"|"audio",
    #   "value": "...", "negate": false, "required": false}]
    conditions: Mapped[list] = mapped_column(JSON, default=list)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "conditions": self.conditions}


class Movie(Base):
    __tablename__ = "movies"
    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(String(16), index=True)
    anilist_id: Mapped[Optional[int]] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(512))
    original_title: Mapped[Optional[str]] = mapped_column(String(512))
    sort_title: Mapped[str] = mapped_column(String(512), default="")
    alt_titles: Mapped[list] = mapped_column(JSON, default=list)
    year: Mapped[Optional[int]] = mapped_column(Integer)
    overview: Mapped[Optional[str]] = mapped_column(Text)
    runtime: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="announced")  # announced|in_cinemas|released
    in_cinemas: Mapped[Optional[datetime]] = mapped_column(DateTime)
    digital_release: Mapped[Optional[datetime]] = mapped_column(DateTime)
    physical_release: Mapped[Optional[datetime]] = mapped_column(DateTime)
    genres: Mapped[list] = mapped_column(JSON, default=list)
    images: Mapped[dict] = mapped_column(JSON, default=dict)  # {"poster": url, "fanart": url}
    ratings: Mapped[dict] = mapped_column(JSON, default=dict)
    certification: Mapped[Optional[str]] = mapped_column(String(16))
    studio: Mapped[Optional[str]] = mapped_column(String(256))
    collection: Mapped[Optional[str]] = mapped_column(String(256))
    original_language: Mapped[Optional[str]] = mapped_column(String(16))
    metadata_sources: Mapped[list] = mapped_column(JSON, default=list)
    monitored: Mapped[bool] = mapped_column(Boolean, default=True)
    minimum_availability: Mapped[str] = mapped_column(String(16), default="released")  # announced|in_cinemas|released
    quality_profile_id: Mapped[int] = mapped_column(ForeignKey("quality_profiles.id"))
    root_folder: Mapped[str] = mapped_column(String(1024))
    path: Mapped[str] = mapped_column(String(1024))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    added: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_refresh: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_search: Mapped[Optional[datetime]] = mapped_column(DateTime)
    file_id: Mapped[Optional[int]] = mapped_column(ForeignKey("media_files.id", ondelete="SET NULL"))

    file: Mapped[Optional["MediaFile"]] = relationship(foreign_keys=[file_id], lazy="joined")

    @property
    def has_file(self) -> bool:
        return self.file_id is not None


class Series(Base):
    __tablename__ = "series"
    id: Mapped[int] = mapped_column(primary_key=True)
    tvdb_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    tmdb_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    tvmaze_id: Mapped[Optional[int]] = mapped_column(Integer)
    imdb_id: Mapped[Optional[str]] = mapped_column(String(16))
    anilist_id: Mapped[Optional[int]] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(512))
    original_title: Mapped[Optional[str]] = mapped_column(String(512))
    sort_title: Mapped[str] = mapped_column(String(512), default="")
    alt_titles: Mapped[list] = mapped_column(JSON, default=list)
    year: Mapped[Optional[int]] = mapped_column(Integer)
    overview: Mapped[Optional[str]] = mapped_column(Text)
    runtime: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="continuing")  # continuing|ended|upcoming
    network: Mapped[Optional[str]] = mapped_column(String(256))
    air_time: Mapped[Optional[str]] = mapped_column(String(8))
    genres: Mapped[list] = mapped_column(JSON, default=list)
    images: Mapped[dict] = mapped_column(JSON, default=dict)
    ratings: Mapped[dict] = mapped_column(JSON, default=dict)
    certification: Mapped[Optional[str]] = mapped_column(String(16))
    original_language: Mapped[Optional[str]] = mapped_column(String(16))
    series_type: Mapped[str] = mapped_column(String(16), default="standard")  # standard|daily|anime
    episode_source: Mapped[str] = mapped_column(String(16), default="")  # provider that defines numbering
    metadata_sources: Mapped[list] = mapped_column(JSON, default=list)
    monitored: Mapped[bool] = mapped_column(Boolean, default=True)
    monitor_new_seasons: Mapped[bool] = mapped_column(Boolean, default=True)
    season_folder: Mapped[bool] = mapped_column(Boolean, default=True)
    quality_profile_id: Mapped[int] = mapped_column(ForeignKey("quality_profiles.id"))
    root_folder: Mapped[str] = mapped_column(String(1024))
    path: Mapped[str] = mapped_column(String(1024))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    added: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_refresh: Mapped[Optional[datetime]] = mapped_column(DateTime)

    seasons: Mapped[list["Season"]] = relationship(back_populates="series", cascade="all, delete-orphan",
                                                    order_by="Season.number")
    episodes: Mapped[list["Episode"]] = relationship(back_populates="series", cascade="all, delete-orphan",
                                                      order_by="[Episode.season, Episode.number]")


class Season(Base):
    __tablename__ = "seasons"
    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    monitored: Mapped[bool] = mapped_column(Boolean, default=True)
    images: Mapped[dict] = mapped_column(JSON, default=dict)
    series: Mapped[Series] = relationship(back_populates="seasons")


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (Index("ix_episode_series_se", "series_id", "season", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), index=True)
    season: Mapped[int] = mapped_column(Integer)
    number: Mapped[int] = mapped_column(Integer)
    absolute_number: Mapped[Optional[int]] = mapped_column(Integer)
    title: Mapped[Optional[str]] = mapped_column(String(512))
    overview: Mapped[Optional[str]] = mapped_column(Text)
    air_date: Mapped[Optional[str]] = mapped_column(String(10))  # YYYY-MM-DD (local airing date)
    air_date_utc: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    runtime: Mapped[Optional[int]] = mapped_column(Integer)
    monitored: Mapped[bool] = mapped_column(Boolean, default=True)
    file_id: Mapped[Optional[int]] = mapped_column(ForeignKey("media_files.id", ondelete="SET NULL"), index=True)
    last_search: Mapped[Optional[datetime]] = mapped_column(DateTime)

    series: Mapped[Series] = relationship(back_populates="episodes")
    file: Mapped[Optional["MediaFile"]] = relationship(foreign_keys=[file_id])

    @property
    def has_file(self) -> bool:
        return self.file_id is not None

    def aired(self, now: Optional[datetime] = None) -> bool:
        now = now or utcnow()
        return self.air_date_utc is not None and self.air_date_utc <= now


class MediaFile(Base):
    __tablename__ = "media_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    media_type: Mapped[str] = mapped_column(String(16))  # movie | episode
    movie_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    series_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    path: Mapped[str] = mapped_column(String(2048))
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    quality: Mapped[str] = mapped_column(String(32), default="Unknown")
    proper: Mapped[int] = mapped_column(Integer, default=0)  # revision count (proper/repack)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    release_group: Mapped[Optional[str]] = mapped_column(String(128))
    release_name: Mapped[Optional[str]] = mapped_column(String(1024))
    format_score: Mapped[int] = mapped_column(Integer, default=0)
    edition: Mapped[Optional[str]] = mapped_column(String(128))
    media_info: Mapped[dict] = mapped_column(JSON, default=dict)
    added: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def to_dict(self):
        return {"id": self.id, "media_type": self.media_type, "path": self.path, "size": self.size,
                "quality": self.quality, "proper": self.proper, "languages": self.languages,
                "release_group": self.release_group, "release_name": self.release_name,
                "format_score": self.format_score, "edition": self.edition, "media_info": self.media_info,
                "added": iso(self.added)}


class Indexer(Base):
    __tablename__ = "indexers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default="newznab")  # newznab | torznab
    url: Mapped[str] = mapped_column(String(1024))
    api_path: Mapped[str] = mapped_column(String(64), default="/api")
    api_key: Mapped[str] = mapped_column(String(256), default="")
    movie_categories: Mapped[list] = mapped_column(JSON, default=list)
    tv_categories: Mapped[list] = mapped_column(JSON, default=list)
    anime_categories: Mapped[list] = mapped_column(JSON, default=list)
    additional_params: Mapped[str] = mapped_column(String(512), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_rss: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_auto_search: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_interactive_search: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=25)
    minimum_seeders: Mapped[int] = mapped_column(Integer, default=1)
    seed_ratio: Mapped[Optional[float]] = mapped_column(Float)
    seed_time: Mapped[Optional[int]] = mapped_column(Integer)  # minutes
    download_client_id: Mapped[Optional[int]] = mapped_column(Integer)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # --- usage limits -------------------------------------------------------------------
    query_limit: Mapped[int] = mapped_column(Integer, default=0)  # 0 = unlimited
    grab_limit: Mapped[int] = mapped_column(Integer, default=0)
    limit_window_hours: Mapped[float] = mapped_column(Float, default=24.0)
    limit_mode: Mapped[str] = mapped_column(String(16), default="rolling")  # rolling | fixed
    limit_reset_hour: Mapped[int] = mapped_column(Integer, default=0)  # UTC hour for fixed mode
    grab_reserve: Mapped[int] = mapped_column(Integer, default=0)  # grabs kept for manual use
    query_reserve: Mapped[int] = mapped_column(Integer, default=0)
    min_request_interval: Mapped[float] = mapped_column(Float, default=0.0)  # seconds
    sync_remote_limits: Mapped[bool] = mapped_column(Boolean, default=True)
    remote_limits: Mapped[dict] = mapped_column(JSON, default=dict)  # last newznab:apilimits seen
    # --- state --------------------------------------------------------------------------
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    disabled_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    last_rss_guid: Mapped[Optional[str]] = mapped_column(String(1024))
    sync_source: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. {"sonarr": true, "radarr": true}

    @property
    def protocol(self) -> str:
        return "torrent" if self.kind == "torznab" else "usenet"


class IndexerEvent(Base):
    __tablename__ = "indexer_events"
    __table_args__ = (Index("ix_idxevent_indexer_time", "indexer_id", "kind", "timestamp"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    indexer_id: Mapped[int] = mapped_column(ForeignKey("indexers.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))  # query | rss | grab | caps
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    results: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[Optional[str]] = mapped_column(String(1024))


class DownloadClient(Base):
    __tablename__ = "download_clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))  # qbittorrent|transmission|deluge|sabnzbd|nzbget|blackhole_torrent|blackhole_usenet
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    host: Mapped[str] = mapped_column(String(256), default="localhost")
    port: Mapped[int] = mapped_column(Integer, default=8080)
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=False)
    url_base: Mapped[str] = mapped_column(String(256), default="")
    username: Mapped[str] = mapped_column(String(256), default="")
    password: Mapped[str] = mapped_column(String(256), default="")
    api_key: Mapped[str] = mapped_column(String(256), default="")
    movie_category: Mapped[str] = mapped_column(String(128), default="movies")
    tv_category: Mapped[str] = mapped_column(String(128), default="tv")
    remove_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    remove_failed: Mapped[bool] = mapped_column(Boolean, default=True)
    add_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)  # client specific (watch_folder, ...)
    tags: Mapped[list] = mapped_column(JSON, default=list)

    @property
    def protocol(self) -> str:
        return "torrent" if self.kind in ("qbittorrent", "transmission", "deluge", "blackhole_torrent") else "usenet"


class RemotePathMapping(Base):
    __tablename__ = "remote_path_mappings"
    id: Mapped[int] = mapped_column(primary_key=True)
    host: Mapped[str] = mapped_column(String(256))
    remote_path: Mapped[str] = mapped_column(String(1024))
    local_path: Mapped[str] = mapped_column(String(1024))

    def to_dict(self):
        return {"id": self.id, "host": self.host, "remote_path": self.remote_path, "local_path": self.local_path}


class QueueItem(Base):
    """A download we sent to a client and are tracking until import."""
    __tablename__ = "queue"
    id: Mapped[int] = mapped_column(primary_key=True)
    download_client_id: Mapped[int] = mapped_column(Integer)
    download_id: Mapped[str] = mapped_column(String(256), index=True)  # infohash / nzo id
    protocol: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(1024))
    media_type: Mapped[str] = mapped_column(String(16))  # movie | series
    movie_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    series_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    episode_ids: Mapped[list] = mapped_column(JSON, default=list)
    quality: Mapped[str] = mapped_column(String(32), default="Unknown")
    languages: Mapped[list] = mapped_column(JSON, default=list)
    format_score: Mapped[int] = mapped_column(Integer, default=0)
    indexer_id: Mapped[Optional[int]] = mapped_column(Integer)
    indexer_name: Mapped[Optional[str]] = mapped_column(String(128))
    guid: Mapped[Optional[str]] = mapped_column(String(1024))
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    size_left: Mapped[int] = mapped_column(BigInteger, default=0)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    eta_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    # grabbed | downloading | paused | queued | completed | importing | imported | failed | import_blocked | warning
    status: Mapped[str] = mapped_column(String(32), default="grabbed")
    client_status: Mapped[Optional[str]] = mapped_column(String(64))
    output_path: Mapped[Optional[str]] = mapped_column(String(2048))
    messages: Mapped[list] = mapped_column(JSON, default=list)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    added: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished: Mapped[Optional[datetime]] = mapped_column(DateTime)
    stalled_since: Mapped[Optional[datetime]] = mapped_column(DateTime)  # no progress since (stall timeout)


class History(Base):
    __tablename__ = "history"
    id: Mapped[int] = mapped_column(primary_key=True)
    event: Mapped[str] = mapped_column(String(32), index=True)  # grabbed|imported|upgraded|failed|deleted|renamed|ignored
    date: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    media_type: Mapped[str] = mapped_column(String(16))
    movie_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    series_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    episode_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_title: Mapped[str] = mapped_column(String(1024), default="")
    quality: Mapped[Optional[str]] = mapped_column(String(32))
    indexer: Mapped[Optional[str]] = mapped_column(String(128))
    download_client: Mapped[Optional[str]] = mapped_column(String(128))
    download_id: Mapped[Optional[str]] = mapped_column(String(256))
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class Blocklist(Base):
    __tablename__ = "blocklist"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    media_type: Mapped[str] = mapped_column(String(16))
    movie_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    series_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    episode_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_title: Mapped[str] = mapped_column(String(1024))
    guid: Mapped[Optional[str]] = mapped_column(String(1024))
    info_hash: Mapped[Optional[str]] = mapped_column(String(64))
    indexer: Mapped[Optional[str]] = mapped_column(String(128))
    protocol: Mapped[Optional[str]] = mapped_column(String(16))
    reason: Mapped[Optional[str]] = mapped_column(String(512))


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))  # webhook|discord|gotify|ntfy|telegram|jellyfin|emby|plex
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    on_grab: Mapped[bool] = mapped_column(Boolean, default=True)
    on_import: Mapped[bool] = mapped_column(Boolean, default=True)
    on_upgrade: Mapped[bool] = mapped_column(Boolean, default=True)
    on_failure: Mapped[bool] = mapped_column(Boolean, default=True)
    on_health: Mapped[bool] = mapped_column(Boolean, default=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)


class MetadataCache(Base):
    __tablename__ = "metadata_cache"
    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    created: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    value: Mapped[Any] = mapped_column(JSON)


class TaskState(Base):
    __tablename__ = "task_state"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_run: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
