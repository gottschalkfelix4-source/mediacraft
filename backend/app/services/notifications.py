"""Notifications: webhook, Discord, Gotify, ntfy, Telegram + media server library refresh."""
from __future__ import annotations

import logging
import threading
from typing import Optional

import httpx

from ..db import session_scope
from ..models import Notification

log = logging.getLogger("notify")

KINDS = {
    "webhook": ["url", "method"],
    "discord": ["webhook_url", "username"],
    "gotify": ["url", "token", "priority"],
    "ntfy": ["url", "topic", "token"],
    "telegram": ["bot_token", "chat_id"],
    "jellyfin": ["url", "api_key"],
    "emby": ["url", "api_key"],
    "plex": ["url", "token"],
}
EVENT_FLAG = {"grab": "on_grab", "import": "on_import", "upgrade": "on_upgrade", "failure": "on_failure",
              "health": "on_health", "test": None}
TITLES = {"grab": "Release geladen", "import": "Importiert", "upgrade": "Upgrade importiert",
          "failure": "Download fehlgeschlagen", "health": "Health-Warnung", "test": "Test"}


def _send(n: Notification, event: str, message: str, payload: dict) -> None:
    s = n.settings or {}
    title = f"MediaCraft – {TITLES.get(event, event)}"
    with httpx.Client(timeout=15) as c:
        if n.kind == "webhook":
            c.request(s.get("method", "POST"), s["url"], json={"eventType": event, "message": message, **payload})
        elif n.kind == "discord":
            color = {"grab": 0x7289DA, "import": 0x2ECC71, "upgrade": 0x27AE60, "failure": 0xE74C3C, "health": 0xF39C12}.get(event, 0x95A5A6)
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
                   json={"chat_id": s["chat_id"], "text": f"*{title}*\n{message}", "parse_mode": "Markdown"}).raise_for_status()
        elif n.kind in ("jellyfin", "emby"):
            if event in ("import", "upgrade", "test"):
                c.post(s["url"].rstrip("/") + "/Library/Refresh", headers={"X-Emby-Token": s["api_key"]}).raise_for_status()
        elif n.kind == "plex":
            if event in ("import", "upgrade", "test"):
                c.get(s["url"].rstrip("/") + "/library/sections/all/refresh", params={"X-Plex-Token": s["token"]}).raise_for_status()


def test(n: Notification) -> None:
    _send(n, "test", "Testnachricht von MediaCraft", {})


def notify(event: str, message: str, payload: Optional[dict] = None) -> None:
    """Fire-and-forget dispatch to all matching notification targets."""
    flag = EVENT_FLAG.get(event)

    def run():
        with session_scope() as s:
            targets = [n for n in s.query(Notification).filter(Notification.enabled.is_(True)).all()
                       if flag is None or getattr(n, flag)]
            for n in targets:
                try:
                    _send(n, event, message, payload or {})
                except Exception as e:
                    log.warning("Benachrichtigung '%s' fehlgeschlagen: %s", n.name, e)

    threading.Thread(target=run, daemon=True, name="notify").start()
