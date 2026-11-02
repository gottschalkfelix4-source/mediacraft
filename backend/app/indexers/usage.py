"""Indexer usage tracking and limit enforcement.

Every API query and every NZB/torrent download (grab) is stored as an ``IndexerEvent``.
Limits are evaluated over either a *rolling* window (e.g. 400 grabs in the last 24 h – the
oldest event "falls out" exactly 24 h after it happened) or a *fixed* window that resets at
a configured UTC hour. Counters reported by the indexer itself (``newznab:apilimits``) are
merged in so that usage from other tools on the same account is respected as well.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Indexer, IndexerEvent, utcnow

QUERY_KINDS = ("query", "rss", "caps", "limits")

_interval_lock = threading.Lock()
_last_request: dict[int, float] = {}


class LimitReached(Exception):
    def __init__(self, indexer: str, kind: str, until: Optional[datetime]):
        self.indexer, self.kind, self.until = indexer, kind, until
        when = until.strftime("%Y-%m-%d %H:%M UTC") if until else "unbekannt"
        super().__init__(f"{indexer}: {kind}-Limit erreicht, nächster freier Slot {when}")


@dataclass
class LimitState:
    kind: str  # query | grab
    limit: int
    used: int
    remote_used: Optional[int]
    reserve: int
    window_start: str
    window_end: Optional[str]  # fixed mode: reset time
    next_slot: Optional[str]  # when the next unit becomes available (if exhausted)
    remaining: Optional[int]
    remaining_auto: Optional[int]  # remaining for automatic use (minus reserve)
    percent: float

    def to_dict(self):
        return asdict(self)


def window_bounds(idx: Indexer, now: Optional[datetime] = None) -> tuple[datetime, Optional[datetime]]:
    now = now or utcnow()
    hours = idx.limit_window_hours or 24
    if idx.limit_mode == "fixed":
        # fixed windows reset at limit_reset_hour (UTC) every ceil(hours/24) days (daily, weekly, ...)
        days = max(1, int(math.ceil(hours / 24)))
        epoch = datetime(2024, 1, 1, idx.limit_reset_hour % 24)
        k = int((now - epoch).total_seconds() // (days * 86400))
        reset = epoch + timedelta(days=days * k)
        return reset, reset + timedelta(days=days)
    return now - timedelta(hours=hours), None


def _kinds(kind: str) -> tuple[str, ...]:
    return QUERY_KINDS if kind == "query" else ("grab",)


def _filters(idx: Indexer, kind: str, start: datetime) -> list:
    f = [IndexerEvent.indexer_id == idx.id, IndexerEvent.kind.in_(_kinds(kind)), IndexerEvent.timestamp >= start]
    if kind == "grab":
        f.append(IndexerEvent.success.is_(True))  # failed downloads don't consume a grab
    return f


def count(db: Session, idx: Indexer, kind: str, now: Optional[datetime] = None) -> int:
    start, _ = window_bounds(idx, now)
    return db.query(func.count(IndexerEvent.id)).filter(*_filters(idx, kind, start)).scalar() or 0


def _remote_seen(idx: Indexer) -> Optional[datetime]:
    rl = idx.remote_limits or {}
    if not idx.sync_remote_limits or not rl.get("seen"):
        return None
    try:
        return datetime.fromisoformat(rl["seen"])
    except ValueError:
        return None


def _remote_used(db: Session, idx: Indexer, kind: str, now: datetime) -> Optional[int]:
    """Live counter: what the indexer reported plus our own requests since that report.

    The indexer counts usage from every tool on the account (other *arr apps, the website, ...),
    so this is the authoritative number. Requests we made after the report are added on top
    because the indexer could not include them yet.
    """
    seen = _remote_seen(idx)
    # remote counters older than the window are meaningless
    if seen is None or now - seen > timedelta(hours=idx.limit_window_hours or 24):
        return None
    v = (idx.remote_limits or {}).get("api_current" if kind == "query" else "grab_current")
    if v is None:
        return None
    since = db.query(func.count(IndexerEvent.id)).filter(*_filters(idx, kind, seen)).scalar() or 0
    return int(v) + since


def effective_limit(idx: Indexer, kind: str) -> int:
    local = idx.query_limit if kind == "query" else idx.grab_limit
    rl = idx.remote_limits or {}
    remote = rl.get("api_max" if kind == "query" else "grab_max") if idx.sync_remote_limits else None
    if local and remote:
        return min(int(local), int(remote))
    return int(local or remote or 0)


def next_slot(db: Session, idx: Indexer, kind: str, limit: int, now: Optional[datetime] = None) -> Optional[datetime]:
    """Point in time when usage drops below the limit again."""
    now = now or utcnow()
    start, end = window_bounds(idx, now)
    if idx.limit_mode == "fixed":
        return end
    hours = idx.limit_window_hours or 24
    used = count(db, idx, kind, now)
    over = used - limit + 1  # how many events have to fall out of the window
    candidate = None
    if over > 0:
        row = db.query(IndexerEvent.timestamp).filter(*_filters(idx, kind, start)).order_by(IndexerEvent.timestamp.asc()).offset(over - 1).limit(1).first()
        candidate = row[0] + timedelta(hours=hours) if row else None
    elif (_remote_used(db, idx, kind, now) or 0) < limit:
        return None
    # remote oldest time (if indexer told us) can push the slot further out
    rl = idx.remote_limits or {}
    remote_slot = None
    try:
        if rl.get(f"{_rk(kind)}_next"):  # indexer says directly when the next unit frees up
            remote_slot = datetime.fromisoformat(rl[f"{_rk(kind)}_next"])
        elif rl.get(f"{_rk(kind)}_oldest"):
            remote_slot = datetime.fromisoformat(rl[f"{_rk(kind)}_oldest"]) + timedelta(hours=hours)
    except ValueError:
        remote_slot = None
    if remote_slot and remote_slot > now and (candidate is None or remote_slot > candidate):
        candidate = remote_slot
    if candidate is None and _remote_seen(idx):
        # exhausted according to the indexer, but it gave no times: every unit it counted is out of the
        # window one window-length after its report at the latest (the next limits poll refines this)
        candidate = _remote_seen(idx) + timedelta(hours=hours)
    return candidate


def _rk(kind: str) -> str:
    return "api" if kind == "query" else "grab"


def state(db: Session, idx: Indexer, kind: str, now: Optional[datetime] = None) -> LimitState:
    now = now or utcnow()
    limit = effective_limit(idx, kind)
    used_local = count(db, idx, kind, now)
    remote = _remote_used(db, idx, kind, now)
    used = max(used_local, remote or 0)
    reserve = idx.query_reserve if kind == "query" else idx.grab_reserve
    start, end = window_bounds(idx, now)
    remaining = max(limit - used, 0) if limit else None
    nxt = None
    if limit and used >= limit - reserve:
        nxt = next_slot(db, idx, kind, limit - reserve if used < limit else limit, now)
    return LimitState(
        kind=kind, limit=limit, used=used, remote_used=remote, reserve=reserve,
        window_start=start.isoformat() + "Z", window_end=end.isoformat() + "Z" if end else None,
        next_slot=nxt.isoformat() + "Z" if nxt else None, remaining=remaining,
        remaining_auto=max(remaining - reserve, 0) if remaining is not None else None,
        percent=round(100.0 * used / limit, 1) if limit else 0.0,
    )


def check(db: Session, idx: Indexer, kind: str, manual: bool = False) -> None:
    """Raise LimitReached when a request of ``kind`` is not allowed right now."""
    now = utcnow()
    if idx.disabled_until and idx.disabled_until > now:
        raise LimitReached(idx.name, "pausiert", idx.disabled_until)
    st = state(db, idx, kind, now)
    if not st.limit:
        return
    allowed = st.limit if manual else st.limit - st.reserve
    if st.used >= allowed:
        nxt = st.next_slot
        raise LimitReached(idx.name, kind, datetime.fromisoformat(nxt[:-1]) if nxt else None)


def can(db: Session, idx: Indexer, kind: str, manual: bool = False) -> bool:
    try:
        check(db, idx, kind, manual)
        return True
    except LimitReached:
        return False


def wait_interval(idx: Indexer) -> None:
    """Enforce the minimum gap between two requests to the same indexer."""
    if not idx.min_request_interval:
        return
    with _interval_lock:
        last = _last_request.get(idx.id, 0.0)
        wait = last + idx.min_request_interval - time.monotonic()
        _last_request[idx.id] = max(time.monotonic(), last + idx.min_request_interval)
    if wait > 0:
        time.sleep(wait)


def record(db: Session, idx: Indexer, kind: str, *, success: bool = True, manual: bool = False, elapsed_ms: int = 0,
           results: int = 0, detail: str | None = None) -> None:
    db.add(IndexerEvent(indexer_id=idx.id, kind=kind, success=success, manual=manual, elapsed_ms=elapsed_ms,
                        results=results, detail=(detail or "")[:1000]))
    db.flush()


def apply_remote_limits(idx: Indexer, attrs: dict) -> None:
    """Store counters from ``<newznab:apilimits .../>``.

    Attribute names are case-insensitive (``apiCurrent`` / ``apicurrent``). Besides the spec
    attributes (``apiNextAvailable``/``grabNextAvailable``) the widespread ``apiOldestTime``/
    ``grabOldestTime`` variant is understood. A missing ``*Current`` next to a ``*Max`` means 0.
    """
    a = {k.lower(): v for k, v in attrs.items()}

    def _int(k):
        try:
            return int(a[k]) if a.get(k) not in (None, "") else None
        except ValueError:
            return None

    def _dt(k):
        v = a.get(k)
        if not v:
            return None
        from email.utils import parsedate_to_datetime
        try:
            d = parsedate_to_datetime(v)
        except (TypeError, ValueError):
            try:
                d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                return None
        if d.tzinfo:
            d = d.astimezone(timezone.utc).replace(tzinfo=None)
        return d.isoformat()

    out = {"seen": utcnow().isoformat(), "checked": utcnow().isoformat(), "supported": True,
           "raw": {k: v for k, v in attrs.items()}}
    for p in ("api", "grab"):
        cur, mx = _int(f"{p}current"), _int(f"{p}max")
        out[f"{p}_current"] = 0 if cur is None and mx is not None else cur
        out[f"{p}_max"] = mx
        out[f"{p}_oldest"] = _dt(f"{p}oldesttime")
        out[f"{p}_next"] = _dt(f"{p}nextavailable")
    idx.remote_limits = out


def mark_remote_missing(idx: Indexer) -> None:
    """A limits probe got an answer without ``apilimits`` – remember so polling stops wasting queries."""
    rl = dict(idx.remote_limits or {})
    rl["checked"] = utcnow().isoformat()
    if not rl.get("seen"):
        rl["supported"] = False
    idx.remote_limits = rl


def pause(db: Session, idx: Indexer, reason: str, until: Optional[datetime] = None, backoff: list[int] | None = None) -> None:
    """Pause an indexer after a failure (explicit ``until`` or escalating backoff)."""
    idx.failure_count = (idx.failure_count or 0) + 1
    idx.last_error = reason[:2000]
    if until is None:
        steps = backoff or [5, 15, 30, 60, 180, 360]
        until = utcnow() + timedelta(minutes=steps[min(idx.failure_count, len(steps)) - 1])
    idx.disabled_until = until
    db.flush()


def mark_ok(idx: Indexer) -> None:
    if idx.failure_count or idx.disabled_until:
        idx.failure_count = 0
        idx.disabled_until = None
        idx.last_error = None


def histogram(db: Session, idx: Indexer, hours: int = 48) -> list[dict]:
    """Per-hour counts of queries/grabs/failures for charts."""
    now = utcnow().replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=hours - 1)
    rows = db.query(IndexerEvent.timestamp, IndexerEvent.kind, IndexerEvent.success).filter(
        IndexerEvent.indexer_id == idx.id, IndexerEvent.timestamp >= start).all()
    buckets = {start + timedelta(hours=i): {"query": 0, "grab": 0, "failed": 0} for i in range(hours)}
    for ts, kind, ok in rows:
        b = buckets.get(ts.replace(minute=0, second=0, microsecond=0))
        if b is None:
            continue
        if not ok:
            b["failed"] += 1
        b["grab" if kind == "grab" else "query"] += 1
    return [{"hour": k.isoformat() + "Z", **v} for k, v in sorted(buckets.items())]


def forecast(db: Session, idx: Indexer, kind: str, steps: int = 24) -> list[dict]:
    """How many units become free over the next hours (rolling mode): [{hour, available}]."""
    now = utcnow()
    limit = effective_limit(idx, kind)
    if not limit:
        return []
    hours = idx.limit_window_hours or 24
    start, end = window_bounds(idx, now)
    times = [r[0] for r in db.query(IndexerEvent.timestamp).filter(*_filters(idx, kind, start)).all()]
    # usage the indexer knows about but we don't (other tools): exact times are unknown, so assume the
    # latest possible – right before the report – which never promises a slot too early
    extra = (_remote_used(db, idx, kind, now) or 0) - len(times)
    if extra > 0:
        times += [_remote_seen(idx)] * extra
    out = []
    for h in range(steps + 1):
        t = now + timedelta(hours=h)
        if idx.limit_mode == "fixed":
            used = 0 if end and t >= end else len(times)
        else:
            used = sum(1 for x in times if x + timedelta(hours=hours) > t)
        out.append({"at": t.isoformat() + "Z", "available": max(limit - used, 0)})
    return out
