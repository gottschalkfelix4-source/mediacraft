"""Custom format evaluation: conditions against a parsed release -> score."""
from __future__ import annotations

import re
from typing import Iterable, Optional

from .parser import ParsedRelease

CONDITION_TYPES = ["title", "group", "source", "resolution", "language", "codec", "hdr", "audio", "edition", "size",
                   "indexer_flag", "protocol"]


def _cond_matches(cond: dict, p: ParsedRelease, size: int = 0, protocol: str = "", flags: Iterable[str] = ()) -> bool:
    t = cond.get("type")
    v = str(cond.get("value", ""))
    try:
        if t == "title":
            return re.search(v, p.raw, re.I) is not None
        if t == "group":
            return bool(p.release_group) and re.search(v, p.release_group, re.I) is not None
        if t == "source":
            return p.source == v.lower()
        if t == "resolution":
            return str(p.resolution) == v.rstrip("p")
        if t == "language":
            return v.lower() in p.languages
        if t == "codec":
            return (p.codec or "").lower() == v.lower()
        if t == "hdr":
            return v.upper() in [h.upper() for h in p.hdr]
        if t == "audio":
            return v.lower() in [a.lower() for a in p.audio]
        if t == "edition":
            return bool(p.edition) and re.search(v, p.edition, re.I) is not None
        if t == "size":  # "min-max" in GB
            lo, _, hi = v.partition("-")
            gb = size / 1024 ** 3
            return (not lo or gb >= float(lo)) and (not hi or gb <= float(hi))
        if t == "indexer_flag":
            return v.lower() in {f.lower() for f in flags}
        if t == "protocol":
            return protocol == v.lower()
    except re.error:
        return False
    return False


def matches(fmt: dict, p: ParsedRelease, size: int = 0, protocol: str = "", flags: Iterable[str] = ()) -> bool:
    """A format matches when every required condition matches and, per condition type, at least one matches."""
    conds = fmt.get("conditions") or []
    if not conds:
        return False
    by_type: dict[str, list[bool]] = {}
    for c in conds:
        if c.get("unsupported") and not c.get("required"):
            continue  # imported from Sonarr/Radarr, can't be evaluated – optional ones don't count
        ok = _cond_matches(c, p, size, protocol, flags)
        if c.get("negate"):
            ok = not ok
        if c.get("required") and not ok:
            return False
        if not c.get("required"):
            by_type.setdefault(c.get("type", ""), []).append(ok)
    return all(any(v) for v in by_type.values())


def evaluate(formats: list[dict], scores: dict, p: ParsedRelease, size: int = 0, protocol: str = "",
             flags: Iterable[str] = ()) -> tuple[int, list[str]]:
    total = 0
    names: list[str] = []
    for f in formats:
        if matches(f, p, size, protocol, flags):
            names.append(f["name"])
            total += int(scores.get(str(f["id"]), scores.get(f["id"], 0)) or 0)
    return total, names


def score_for(db, profile, p: ParsedRelease, size: int = 0, protocol: str = "",
              flags: Iterable[str] = ()) -> tuple[int, list[str]]:
    from ..models import CustomFormat

    formats = [cf.to_dict() for cf in db.query(CustomFormat).all()]
    return evaluate(formats, profile.format_scores or {}, p, size, protocol, flags)
