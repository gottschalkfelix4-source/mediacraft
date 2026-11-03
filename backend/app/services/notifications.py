"""Notifications: webhook (own or Sonarr/Radarr format), Discord, Gotify, ntfy, Telegram, Pushover, e-mail,
Apprise API and media server library refresh (Jellyfin, Emby, Plex)."""
from __future__ import annotations

import html
import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage
from typing import Optional

import httpx

from ..db import session_scope
from ..models import Notification

log = logging.getLogger("notify")

KINDS = {
    "webhook": ["url", "method", "format"],
    "discord": ["webhook_url", "username"],
    "gotify": ["url", "token", "priority"],
    "ntfy": ["url", "topic", "token"],
    "telegram": ["bot_token", "chat_id"],
    "pushover": ["user_key", "app_token", "priority", "device"],
    "email": ["host", "port", "security", "username", "password", "sender", "recipients"],
    "apprise": ["url", "urls", "tag"],
    "jellyfin": ["url", "api_key"],
    "emby": ["url", "api_key"],
    "plex": ["url", "token"],
}
SECRET_FIELDS = ("token", "bot_token", "api_key", "password", "app_token", "user_key")
EVENT_FLAG = {"grab": "on_grab", "import": "on_import", "upgrade": "on_upgrade", "failure": "on_failure",
              "health": "on_health", "delete": "on_delete", "rename": "on_rename", "limit": "on_limit", "test": None}
TITLES = {"grab": "Release geladen", "import": "Importiert", "upgrade": "Upgrade importiert",
          "failure": "Download fehlgeschlagen", "health": "Health-Warnung", "delete": "Gelöscht", "rename": "Umbenannt",
          "limit": "Indexer-Limit", "test": "Test"}
LIBRARY_EVENTS = ("import", "upgrade", "delete", "rename", "test")  # media servers only refresh on these


# ---------------------------------------------------------------------------------- Sonarr/Radarr webhook format
def _arr_payload(event: str, message: str, payload: dict, flavor_hint: str) -> dict:
    """Payload in the shape Sonarr/Radarr webhooks use, so existing scripts/Notifiarr-style receivers work."""
    from ..models import Episode, MediaFile, Movie, Series

    movie_id, series_id = payload.get("movie_id"), payload.get("series_id")
    flavor = "radarr" if movie_id or (flavor_hint == "radarr" and not series_id) else "sonarr"
    event_type = {"grab": "Grab", "import": "Download", "upgrade": "Download", "failure": "DownloadFailure",
                  "health": "Health", "rename": "Rename", "test": "Test", "limit": "Health",
                  "delete": ("MovieDelete" if flavor == "radarr" else "SeriesDelete") if not payload.get("file_only")
                  else ("MovieFileDelete" if flavor == "radarr" else "EpisodeFileDelete")}[event]
    out: dict = {"eventType": event_type, "instanceName": "MediaCraft", "applicationUrl": ""}
    if event in ("health", "limit"):
        out.update(level="warning", message=message, type=event, wikiUrl="")
        return out
    with session_scope() as db:
        if flavor == "radarr" and movie_id:
            m = db.get(Movie, movie_id)
            if m:
                out["movie"] = {"id": m.id, "title": m.title, "year": m.year, "folderPath": m.path, "tmdbId": m.tmdb_id,
                                "imdbId": m.imdb_id, "releaseDate": m.digital_release.isoformat() if m.digital_release else None}
                out["remoteMovie"] = {"tmdbId": m.tmdb_id, "imdbId": m.imdb_id, "title": m.title, "year": m.year}
        elif series_id:
            s = db.get(Series, series_id)
            if s:
                out["series"] = {"id": s.id, "title": s.title, "path": s.path, "tvdbId": s.tvdb_id, "tmdbId": s.tmdb_id,
                                 "imdbId": s.imdb_id, "type": s.series_type, "year": s.year}
            eps = db.query(Episode).filter(Episode.id.in_(payload.get("episode_ids") or [])).all()
            out["episodes"] = [{"id": e.id, "episodeNumber": e.number, "seasonNumber": e.season, "title": e.title,
                                "airDate": e.air_date, "airDateUtc": e.air_date_utc.isoformat() + "Z" if e.air_date_utc else None}
                               for e in eps]
        if payload.get("release_title"):
            out["release"] = {"releaseTitle": payload["release_title"], "quality": payload.get("quality"),
                              "qualityVersion": 1, "releaseGroup": payload.get("release_group"),
                              "indexer": payload.get("indexer"), "size": payload.get("size") or 0}
        if payload.get("file_id"):
            f = db.get(MediaFile, payload["file_id"])
            if f:
                key = "movieFile" if flavor == "radarr" else "episodeFile"
                out[key] = {"id": f.id, "path": f.path, "relativePath": f.path.rsplit("/", 1)[-1], "quality": f.quality,
                            "releaseGroup": f.release_group, "sceneName": f.release_name, "size": f.size}
    if payload.get("download_id"):
        out["downloadId"] = payload["download_id"]
        out["downloadClient"] = payload.get("download_client")
    if event in ("import", "upgrade"):
        out["isUpgrade"] = event == "upgrade"
    if event == "failure":
        out["message"] = message
    return out


# ---------------------------------------------------------------------------------- senders
def _email(s: dict, title: str, message: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = s.get("sender") or s.get("username")
    recipients = [r.strip() for r in (s.get("recipients") or "").replace(";", ",").split(",") if r.strip()]
    if not recipients:
        raise ValueError("Keine Empfänger angegeben")
    msg["To"] = ", ".join(recipients)
    msg.set_content(message)
    port = int(s.get("port") or 587)
    security = (s.get("security") or "starttls").lower()  # starttls | ssl | none
    ctx = ssl.create_default_context()
    if security == "ssl":
        server = smtplib.SMTP_SSL(s["host"], port, timeout=20, context=ctx)
    else:
        server = smtplib.SMTP(s["host"], port, timeout=20)
    with server:
        if security == "starttls":
            server.starttls(context=ctx)
        if s.get("username"):
            server.login(s["username"], s.get("password") or "")
        server.send_message(msg)


def _send(n: Notification, event: str, message: str, payload: dict) -> None:
    s = n.settings or {}
    title = f"MediaCraft – {TITLES.get(event, event)}"
    if n.kind in ("jellyfin", "emby", "plex") and event not in LIBRARY_EVENTS:
        return
    if n.kind == "email":
        return _email(s, title, message)
    with httpx.Client(timeout=15) as c:
        if n.kind == "webhook":
            fmt = (s.get("format") or "mediacraft").lower()
            body = _arr_payload(event, message, payload, fmt) if fmt in ("sonarr", "radarr") else \
                {"eventType": event, "message": message, **payload}
            c.request(s.get("method") or "POST", s["url"], json=body).raise_for_status()
        elif n.kind == "discord":
            color = {"grab": 0x7289DA, "import": 0x2ECC71, "upgrade": 0x27AE60, "failure": 0xE74C3C, "health": 0xF39C12,
                     "limit": 0xF39C12, "delete": 0x95A5A6}.get(event, 0x95A5A6)
            embed = {"title": title, "description": message, "color": color}
            if payload.get("poster"):
                embed["thumbnail"] = {"url": payload["poster"]}
            c.post(s["webhook_url"], json={"username": s.get("username") or "MediaCraft", "embeds": [embed]}).raise_for_status()
        elif n.kind == "gotify":
            c.post(s["url"].rstrip("/") + "/message", params={"token": s["token"]},
                   json={"title": title, "message": message, "priority": int(s.get("priority") or 5)}).raise_for_status()
        elif n.kind == "ntfy":
            h = {"Title": title.encode("utf-8").decode("latin-1", "ignore")}
            if s.get("token"):
                h["Authorization"] = f"Bearer {s['token']}"
            c.post(f"{(s.get('url') or 'https://ntfy.sh').rstrip('/')}/{s['topic']}", content=message.encode(), headers=h).raise_for_status()
        elif n.kind == "telegram":
            c.post(f"https://api.telegram.org/bot{s['bot_token']}/sendMessage",
                   json={"chat_id": s["chat_id"], "text": f"<b>{html.escape(title)}</b>\n{html.escape(message)}",
                         "parse_mode": "HTML"}).raise_for_status()
        elif n.kind == "pushover":
            data = {"token": s["app_token"], "user": s["user_key"], "title": title, "message": message,
                    "priority": int(s.get("priority") or 0)}
            if s.get("device"):
                data["device"] = s["device"]
            if payload.get("poster"):
                data["url"], data["url_title"] = payload["poster"], "Poster"
            c.post("https://api.pushover.net/1/messages.json", data=data).raise_for_status()
        elif n.kind == "apprise":
            # Apprise API (caronc/apprise-api): /notify/<key> for stored configs, /notify with "urls" stateless
            body = {"title": title, "body": message,
                    "type": {"failure": "failure", "health": "warning", "limit": "warning", "import": "success",
                             "upgrade": "success"}.get(event, "info")}
            if s.get("urls"):
                body["urls"] = s["urls"]
            if s.get("tag"):
                body["tag"] = s["tag"]
            c.post(s["url"].rstrip("/"), json=body).raise_for_status()
        elif n.kind in ("jellyfin", "emby"):
            c.post(s["url"].rstrip("/") + "/Library/Refresh", headers={"X-Emby-Token": s["api_key"]}).raise_for_status()
        elif n.kind == "plex":
            c.get(s["url"].rstrip("/") + "/library/sections/all/refresh", params={"X-Plex-Token": s["token"]}).raise_for_status()


def test(n: Notification) -> None:
    _send(n, "test", "Testnachricht von MediaCraft", {})


def notify(event: str, message: str, payload: Optional[dict] = None) -> None:
    """Fire-and-forget dispatch to all matching notification targets."""
    flag = EVENT_FLAG.get(event)

    def run():
        with session_scope() as s:
            targets = [n for n in s.query(Notification).filter(Notification.enabled.is_(True)).all()
                       if flag is None or getattr(n, flag, False)]
            for n in targets:
                try:
                    _send(n, event, message, payload or {})
                except Exception as e:
                    log.warning("Benachrichtigung '%s' fehlgeschlagen: %s", n.name, e)

    threading.Thread(target=run, daemon=True, name="notify").start()
