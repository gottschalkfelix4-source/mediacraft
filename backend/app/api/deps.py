"""Authentication helpers and small utilities shared by the routers."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import threading
import time
from collections import deque
from typing import Any, Iterable

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import config
from ..core import settings as settings_mod
from ..db import get_db

COOKIE = "mc_session"


def hash_password(pw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${h}"


def verify_password(pw: str, stored: str) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_password(pw, salt), stored)


def make_session(secret: str, username: str, days: int = 30) -> str:
    exp = int(time.time()) + days * 86400
    payload = f"{username}|{exp}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}|{sig}"


def check_session(secret: str, token: str | None) -> bool:
    if not token or not secret:
        return False
    try:
        user, exp, sig = token.rsplit("|", 2)
    except ValueError:
        return False
    good = hmac.new(secret.encode(), f"{user}|{exp}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, sig) and int(exp) > time.time()


FORWARD_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded")


def is_local_request(request: Request) -> bool:
    """Direct request from a private/loopback address. Anything that came through a reverse proxy (or
    claims to, via forwarding headers) is never local – those headers can be spoofed by anyone."""
    if any(h in request.headers for h in FORWARD_HEADERS):
        return False
    host = request.client.host if request.client else ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host in ("localhost", "testclient")
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_private or ip.is_loopback or ip.is_link_local


class LoginLimiter:
    """Brute-force protection: at most ``attempts`` failed logins per client within ``window`` seconds."""

    def __init__(self, attempts: int = 5, window: int = 900):
        self.attempts, self.window = attempts, window
        self._fails: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque:
        q = self._fails.setdefault(key, deque())
        while q and q[0] < now - self.window:
            q.popleft()
        return q

    def retry_after(self, key: str) -> int:
        """Seconds until the next attempt is allowed (0 = allowed now)."""
        now = time.time()
        with self._lock:
            q = self._recent(key, now)
            return int(q[0] + self.window - now) + 1 if len(q) >= self.attempts else 0

    def failed(self, key: str) -> None:
        with self._lock:
            self._recent(key, time.time()).append(time.time())

    def reset(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)


login_limiter = LoginLimiter()
# forwarding headers can be forged to look like many clients – this caps failures across all of them
global_login_limiter = LoginLimiter(attempts=30, window=900)


def session_ok(request: Request, auth: dict) -> bool:
    """Web UI access without API key: no auth configured, a valid session, or a local request (if allowed)."""
    if auth.get("method", "none") == "none":
        return True
    if auth.get("local_bypass") and is_local_request(request):
        return True
    return check_session(auth.get("secret", ""), request.cookies.get(COOKIE))


def api_key_from(request: Request) -> str | None:
    return (request.headers.get("X-Api-Key") or request.query_params.get("apikey")
            or request.query_params.get("apiKey"))


def require_auth(request: Request, db: Session = Depends(get_db)) -> None:
    key = api_key_from(request)
    if key and hmac.compare_digest(key, config.API_KEY):
        return
    if session_ok(request, settings_mod.get(db, "auth")):
        return
    raise HTTPException(401, "Nicht angemeldet")


def require_api_key(request: Request) -> None:
    key = api_key_from(request)
    if not key or not hmac.compare_digest(key, config.API_KEY):
        raise HTTPException(401, "Unauthorized")


def apply(obj: Any, data: dict, fields: Iterable[str]) -> Any:
    for f in fields:
        if f in data:
            setattr(obj, f, data[f])
    return obj


def get_or_404(db: Session, model, oid: int):
    obj = db.get(model, oid)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {oid} nicht gefunden")
    return obj
