"""Default data created on first start."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import CustomFormat, DelayProfile, QualityProfile
from .qualities import default_profile_items

_PROFILES = [
    ("Any", ["SDTV", "DVD", "WEBDL-480p", "WEBRip-480p", "Bluray-480p", "Bluray-576p", "HDTV-720p", "WEBRip-720p",
             "WEBDL-720p", "Bluray-720p", "HDTV-1080p", "WEBRip-1080p", "WEBDL-1080p", "Bluray-1080p"], "WEBDL-1080p"),
    ("HD-720p/1080p", ["HDTV-720p", "WEBRip-720p", "WEBDL-720p", "Bluray-720p", "HDTV-1080p", "WEBRip-1080p",
                       "WEBDL-1080p", "Bluray-1080p"], "Bluray-1080p"),
    ("HD-1080p", ["HDTV-1080p", "WEBRip-1080p", "WEBDL-1080p", "Bluray-1080p"], "Bluray-1080p"),
    ("Ultra-HD", ["WEBRip-2160p", "WEBDL-2160p", "Bluray-2160p", "Remux-2160p"], "Remux-2160p"),
    ("HD + UHD", ["WEBRip-1080p", "WEBDL-1080p", "Bluray-1080p", "WEBRip-2160p", "WEBDL-2160p", "Bluray-2160p"],
     "Bluray-2160p"),
]

_FORMATS = [
    ("German DL", [{"type": "language", "value": "german", "required": True},
                   {"type": "title", "value": r"\b(DL|ML|Dual)\b", "required": True}]),
    ("German", [{"type": "language", "value": "german", "required": True}]),
    ("HDR", [{"type": "hdr", "value": "HDR10"}, {"type": "hdr", "value": "HDR10+"}, {"type": "hdr", "value": "HDR"}]),
    ("Dolby Vision", [{"type": "hdr", "value": "DV", "required": True}]),
    ("x265 (HD)", [{"type": "codec", "value": "x265", "required": True},
                   {"type": "resolution", "value": "1080", "required": True}]),
    ("Upscaled / LQ", [{"type": "title", "value": r"\b(upscale[sd]?|regrade|AI[ ._-]?enhanced)\b"}]),
    ("Atmos / TrueHD", [{"type": "audio", "value": "Atmos"}, {"type": "audio", "value": "TrueHD"}]),
]

_DEFAULT_SCORES = {"German DL": 100, "German": 50, "HDR": 10, "Dolby Vision": 5, "Upscaled / LQ": -10000,
                   "Atmos / TrueHD": 5}


def seed_defaults(db: Session) -> None:
    if db.query(DelayProfile).count() == 0:
        db.add(DelayProfile(order=1000, enabled=True, preferred_protocol="usenet", usenet_delay=0, torrent_delay=0,
                            bypass_highest_quality=True, tags=[]))
    if db.query(CustomFormat).count() == 0:
        for name, conds in _FORMATS:
            db.add(CustomFormat(name=name, conditions=conds))
        db.flush()
    if db.query(QualityProfile).count() == 0:
        fmt_ids = {cf.name: cf.id for cf in db.query(CustomFormat).all()}
        scores = {str(fmt_ids[n]): s for n, s in _DEFAULT_SCORES.items() if n in fmt_ids}
        for name, allowed, cutoff in _PROFILES:
            db.add(QualityProfile(name=name, items=default_profile_items(allowed), cutoff=cutoff,
                                  upgrade_allowed=True, languages=[], language_mode="prefer",
                                  format_scores=scores, min_format_score=-1000, cutoff_format_score=100))
        db.flush()
