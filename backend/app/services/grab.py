"""Sending an accepted release to a download client and tracking it in the queue."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from ..core import decision as dec
from ..core.bencode import info_hash, magnet_hash
from ..core.events import live_state, publish
from ..downloadclients.base import AddRequest, ClientError
from ..downloadclients.manager import get_client, pick_client
from ..indexers import newznab
from ..indexers.newznab import Release
from ..models import History, Indexer, Movie, QueueItem, Series
from .notifications import notify

log = logging.getLogger("grab")


class GrabError(Exception):
    pass


def grab_decision(db: Session, d: dec.Decision, manual: bool = False) -> dict:
    return grab(db, d.release, quality=d.quality, languages=d.parsed.languages, format_score=d.format_score,
                movie_id=d.movie_id, series_id=d.series_id, episode_ids=d.episode_ids, manual=manual,
                revision=d.parsed.revision)


def grab(db: Session, r: Release, *, quality: str, languages: list[str], format_score: int = 0,
         movie_id: Optional[int] = None, series_id: Optional[int] = None, episode_ids: list[int] | None = None,
         manual: bool = False, revision: int = 0) -> dict:
    idx = db.get(Indexer, r.indexer_id)
    if not idx:
        raise GrabError("Indexer existiert nicht mehr")
    target = db.get(Movie, movie_id) if movie_id else db.get(Series, series_id)
    client_cfg = pick_client(db, r.protocol, idx.download_client_id, target.tags if target else None)
    if not client_cfg:
        raise GrabError(f"Kein passender aktiver {r.protocol}-Downloadclient (Protokoll/Tags)")
    media_type = "movie" if movie_id else "series"
    category = client_cfg.movie_category if media_type == "movie" else client_cfg.tv_category

    content: Optional[bytes] = None
    magnet: Optional[str] = None
    if r.download_url.startswith("magnet:"):
        magnet = r.download_url
    else:
        try:
            body, ctype = newznab.download(db, idx, r.download_url, manual=manual)
        except newznab.IndexerError as e:
            if r.magnet:
                magnet = r.magnet
            else:
                raise GrabError(str(e)) from e
        else:
            if ctype == "application/x-magnet":
                magnet = body.decode()
            else:
                content = body
    if r.protocol == "torrent" and content and not info_hash(content):
        if r.magnet:
            content, magnet = None, r.magnet
        else:
            raise GrabError("Indexer lieferte keine gültige .torrent-Datei")
    if r.protocol == "usenet" and content and b"<nzb" not in content[:2000].lower():
        raise GrabError("Indexer lieferte keine gültige NZB-Datei")

    db.commit()  # persist the grab event and release the write lock before talking to the client
    client = get_client(client_cfg)
    req = AddRequest(title=r.title, category=category, content=content, magnet=magnet,
                     seed_ratio=idx.seed_ratio, seed_time=idx.seed_time,
                     filename=f"{r.title}.{'torrent' if r.protocol == 'torrent' else 'nzb'}")
    try:
        download_id = client.add(req)
    except ClientError as e:
        raise GrabError(f"{client_cfg.name}: {e}") from e

    item = QueueItem(download_client_id=client_cfg.id, download_id=download_id.lower() if r.protocol == "torrent" else download_id,
                     protocol=r.protocol, title=r.title, media_type=media_type, movie_id=movie_id, series_id=series_id,
                     episode_ids=episode_ids or [], quality=quality, languages=languages, format_score=format_score,
                     indexer_id=idx.id, indexer_name=idx.name, guid=r.guid, size=r.size, size_left=r.size,
                     status="grabbed", manual=manual)
    db.add(item)
    db.add(History(event="grabbed", media_type=media_type, movie_id=movie_id, series_id=series_id,
                   episode_ids=episode_ids or [], source_title=r.title, quality=quality, indexer=idx.name,
                   download_client=client_cfg.name, download_id=item.download_id,
                   data={"size": r.size, "guid": r.guid, "info_url": r.info_url, "protocol": r.protocol,
                         "languages": languages, "format_score": format_score, "manual": manual,
                         "info_hash": r.info_hash or (magnet_hash(magnet) if magnet else None), "revision": revision}))
    db.flush()
    name = target.title if target else r.title
    log.info("Grabbed '%s' von %s → %s", r.title, idx.name, client_cfg.name)
    live_state["active_downloads"] = True  # poll the client quickly from now on
    publish("queue.updated", {"id": item.id})
    notify("grab", f"{name}: {r.title} ({quality}) via {idx.name}",
           {"title": r.title, "quality": quality, "indexer": idx.name,
            "poster": (target.images or {}).get("poster") if target else None, "movie_id": movie_id,
            "series_id": series_id, "episode_ids": episode_ids or [], "release_title": r.title, "size": r.size,
            "download_id": item.download_id, "download_client": client_cfg.name})
    return {"queue_id": item.id, "download_id": item.download_id, "client": client_cfg.name, "title": r.title}
