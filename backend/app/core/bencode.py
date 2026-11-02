"""Minimal bencode decoder – just enough to compute a torrent's info hash and name."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Optional


def _decode(data: bytes, i: int) -> tuple[Any, int]:
    c = data[i:i + 1]
    if c == b"i":
        end = data.index(b"e", i)
        return int(data[i + 1:end]), end + 1
    if c == b"l":
        i += 1
        out = []
        while data[i:i + 1] != b"e":
            v, i = _decode(data, i)
            out.append(v)
        return out, i + 1
    if c == b"d":
        i += 1
        out = {}
        while data[i:i + 1] != b"e":
            k, i = _decode(data, i)
            v, i = _decode(data, i)
            out[k] = v
        return out, i + 1
    if c.isdigit():
        colon = data.index(b":", i)
        n = int(data[i:colon])
        return data[colon + 1:colon + 1 + n], colon + 1 + n
    raise ValueError(f"invalid bencode at {i}")


def decode(data: bytes) -> Any:
    v, _ = _decode(data, 0)
    return v


def info_hash(torrent: bytes) -> Optional[str]:
    """SHA1 of the raw bencoded ``info`` dictionary."""
    try:
        if torrent[:1] != b"d":
            return None
        i = 1
        while torrent[i:i + 1] != b"e":
            key, i = _decode(torrent, i)
            start = i
            _, i = _decode(torrent, i)
            if key == b"info":
                return hashlib.sha1(torrent[start:i]).hexdigest()
    except (ValueError, IndexError):
        return None
    return None


def torrent_name(torrent: bytes) -> Optional[str]:
    try:
        d = decode(torrent)
        return d[b"info"][b"name"].decode("utf-8", "replace")
    except Exception:
        return None


def magnet_hash(magnet: str) -> Optional[str]:
    m = re.search(r"xt=urn:btih:([a-zA-Z0-9]+)", magnet)
    if not m:
        return None
    h = m.group(1)
    if len(h) == 32:  # base32
        import base64
        return base64.b32decode(h.upper()).hex()
    return h.lower()
