"""Authentication helpers and small utilities shared by the routers."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
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


def api_key_from(request: Request) -> str | None:
    return (request.headers.get("X-Api-Key") or request.query_params.get("apikey")
            or request.query_params.get("apiKey"))


def require_auth(request: Request, db: Session = Depends(get_db)) -> None:
    key = api_key_from(request)
    if key and hmac.compare_digest(key, config.API_KEY):
        return
    auth = settings_mod.get(db, "auth")
    if auth.get("method", "none") == "none":
        return
    if check_session(auth.get("secret", ""), request.cookies.get(COOKIE)):
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
