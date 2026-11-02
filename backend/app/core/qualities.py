"""Quality definitions (source x resolution) with ranking and default size limits."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Quality:
    name: str
    source: str  # unknown|cam|telesync|telecine|workprint|dvdscr|regional|sdtv|dvd|hdtv|webrip|webdl|bluray|remux|raw
    resolution: int  # 0, 480, 576, 720, 1080, 2160
    rank: int
    min_mb_min: float  # default size limits in MB per minute of runtime
    max_mb_min: float  # 0 = unlimited


_DEFS = [
    ("Unknown", "unknown", 0, 0, 0),
    ("WORKPRINT", "workprint", 0, 0, 100),
    ("CAM", "cam", 0, 0, 100),
    ("TELESYNC", "telesync", 0, 0, 100),
    ("TELECINE", "telecine", 0, 0, 100),
    ("REGIONAL", "regional", 480, 0, 100),
    ("DVDSCR", "dvdscr", 480, 0, 100),
    ("SDTV", "sdtv", 480, 2, 100),
    ("DVD", "dvd", 480, 2, 100),
    ("DVD-R", "dvdr", 480, 2, 100),
    ("WEBDL-480p", "webdl", 480, 2, 100),
    ("WEBRip-480p", "webrip", 480, 2, 100),
    ("Bluray-480p", "bluray", 480, 2, 100),
    ("Bluray-576p", "bluray", 576, 3, 100),
    ("HDTV-720p", "hdtv", 720, 3, 130),
    ("WEBRip-720p", "webrip", 720, 3, 130),
    ("WEBDL-720p", "webdl", 720, 3, 130),
    ("Bluray-720p", "bluray", 720, 4, 130),
    ("HDTV-1080p", "hdtv", 1080, 4, 155),
    ("WEBRip-1080p", "webrip", 1080, 4, 155),
    ("WEBDL-1080p", "webdl", 1080, 4, 155),
    ("Bluray-1080p", "bluray", 1080, 4, 155),
    ("Remux-1080p", "remux", 1080, 15, 0),
    ("HDTV-2160p", "hdtv", 2160, 15, 350),
    ("WEBRip-2160p", "webrip", 2160, 15, 350),
    ("WEBDL-2160p", "webdl", 2160, 15, 350),
    ("Bluray-2160p", "bluray", 2160, 20, 400),
    ("Remux-2160p", "remux", 2160, 35, 0),
    ("BR-DISK", "brdisk", 1080, 0, 0),
    ("Raw-HD", "rawhd", 1080, 4, 0),
]

QUALITIES: dict[str, Quality] = {
    name: Quality(name, src, res, i, mn, mx) for i, (name, src, res, mn, mx) in enumerate(_DEFS)
}
QUALITY_NAMES = [q.name for q in QUALITIES.values()]


def get(name: str | None) -> Quality:
    return QUALITIES.get(name or "Unknown", QUALITIES["Unknown"])


def from_source_resolution(source: str, resolution: int) -> Quality:
    """Map parsed source + resolution onto a named quality."""
    r = resolution
    if source in ("cam", "telesync", "telecine", "workprint", "dvdscr", "regional"):
        return QUALITIES[{"cam": "CAM", "telesync": "TELESYNC", "telecine": "TELECINE", "workprint": "WORKPRINT",
                          "dvdscr": "DVDSCR", "regional": "REGIONAL"}[source]]
    if source == "brdisk":
        return QUALITIES["BR-DISK"]
    if source == "rawhd":
        return QUALITIES["Raw-HD"]
    if source == "dvdr":
        return QUALITIES["DVD-R"]
    if source == "remux":
        return QUALITIES["Remux-2160p" if r >= 2160 else "Remux-1080p"]
    if source == "dvd":
        return QUALITIES["DVD"] if r <= 576 else QUALITIES[f"Bluray-{r}p"] if r in (720, 1080, 2160) else QUALITIES["DVD"]
    if source == "sdtv":
        return QUALITIES["SDTV"]
    prefix = {"hdtv": "HDTV", "webdl": "WEBDL", "webrip": "WEBRip", "bluray": "Bluray"}.get(source)
    if prefix:
        if r == 0:
            r = 480 if source in ("hdtv",) else (1080 if source == "bluray" else 480)
            if source == "hdtv":
                return QUALITIES["SDTV"]
        if r == 576 and prefix != "Bluray":
            r = 480
        if r == 480 and prefix == "HDTV":
            return QUALITIES["SDTV"]
        name = f"{prefix}-{r}p"
        if name in QUALITIES:
            return QUALITIES[name]
    if r >= 2160:
        return QUALITIES["WEBDL-2160p"]
    if r == 1080:
        return QUALITIES["HDTV-1080p"]
    if r == 720:
        return QUALITIES["HDTV-720p"]
    if r in (480, 576):
        return QUALITIES["SDTV"]
    return QUALITIES["Unknown"]


def default_profile_items(allowed: list[str]) -> list[dict]:
    """Profile items ordered by our default rank; only `allowed` are enabled."""
    order = [q for q in QUALITY_NAMES if q not in ("Unknown", "BR-DISK", "Raw-HD")]
    return [{"quality": q, "allowed": q in allowed} for q in order]


def profile_rank(profile_items: list[dict], quality: str) -> int:
    """Position of a quality within a profile (-1 if not allowed)."""
    for i, it in enumerate(profile_items):
        if it["quality"] == quality:
            return i if it.get("allowed") else -1
    return -1
