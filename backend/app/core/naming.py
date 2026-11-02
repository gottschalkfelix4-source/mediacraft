"""Token based naming engine for folders and files.

Tokens are written as ``{Token Name}``. Number tokens accept a pad format: ``{season:00}``.
Characters before/after the name inside the braces are only emitted when the value is
non-empty: ``{-Release Group}`` -> ``-GROUP`` or nothing, ``{[Edition Tags]}`` -> ``[Extended]``.
"""
from __future__ import annotations

import re
from typing import Any, Optional

TOKEN_RE = re.compile(r"\{(?P<pre>[^A-Za-z{}]*)(?P<name>[A-Za-z][A-Za-z0-9 .\-]*?)(?::(?P<fmt>0+))?(?P<post>[^A-Za-z0-9{}]*)\}")
_ILLEGAL = re.compile(r'[\\/*?"<>|\x00-\x1f]')


def clean_component(value: str, colon_replacement: str = " - ") -> str:
    v = value.replace(":", colon_replacement)
    v = _ILLEGAL.sub("", v)
    v = re.sub(r"\s+", " ", v)
    return v.strip().rstrip(".")


def title_the(title: str) -> str:
    m = re.match(r"^(The|A|An|Der|Die|Das)\s+(.*)$", title or "")
    return f"{m.group(2)}, {m.group(1)}" if m else (title or "")


def clean_title(title: str) -> str:
    return re.sub(r"[^\w\s]", "", title or "").strip()


def render(template: str, values: dict[str, Any], colon_replacement: str = " - ") -> str:
    lookup = {k.lower(): v for k, v in values.items()}

    def repl(m: re.Match) -> str:
        name = m.group("name").strip().lower()
        val = lookup.get(name)
        if val is None or val == "" or val == []:
            return ""
        if m.group("fmt") and isinstance(val, (int, float)):
            val = str(int(val)).zfill(len(m.group("fmt")))
        elif isinstance(val, (list, tuple)):
            val = " ".join(str(x) for x in val)
        return f"{m.group('pre')}{val}{m.group('post')}"

    out = TOKEN_RE.sub(repl, template)
    out = re.sub(r"\[\s*\]|\(\s*\)|\{\s*\}", "", out)
    out = re.sub(r"\s+", " ", out)
    out = re.sub(r"\s+([\]\)])", r"\1", out)
    out = re.sub(r"(\s-)+\s*$", "", out)
    out = re.sub(r"\s-\s(?=-)", " ", out)
    return clean_component(out.strip(" -"), colon_replacement)


def quality_full(quality: str, revision: int = 0) -> str:
    return f"{quality} Proper" if revision else quality


def movie_values(movie, file_info: Optional[dict] = None) -> dict:
    f = file_info or {}
    return {
        "Movie Title": movie.title,
        "Movie TitleThe": title_the(movie.title),
        "Movie CleanTitle": clean_title(movie.title),
        "Movie OriginalTitle": movie.original_title or movie.title,
        "Release Year": movie.year,
        "ImdbId": movie.imdb_id,
        "TmdbId": movie.tmdb_id,
        "Movie Collection": movie.collection,
        "Movie Certification": movie.certification,
        **_file_values(f),
    }


def series_values(series) -> dict:
    return {
        "Series Title": series.title,
        "Series TitleThe": title_the(series.title),
        "Series CleanTitle": clean_title(series.title),
        "Series Year": series.year,
        "TvdbId": series.tvdb_id,
        "TmdbId": series.tmdb_id,
        "ImdbId": series.imdb_id,
        "Network": series.network,
    }


def episode_values(series, episodes: list, file_info: Optional[dict] = None, multi_style: str = "extend") -> dict:
    eps = sorted(episodes, key=lambda e: (e.season, e.number))
    first = eps[0]
    v = series_values(series)
    v.update({
        "season": first.season,
        "episode": first.number,
        "absolute": first.absolute_number,
        "Episode Title": " + ".join(dict.fromkeys(_strip_part(e.title or "") for e in eps if e.title)),
        "Air-Date": first.air_date,
        "Air Date": (first.air_date or "").replace("-", " "),
        **_file_values(file_info or {}),
    })
    if len(eps) > 1:
        last = eps[-1]
        v["episode_suffix"] = (f"-E{last.number:02d}" if multi_style == "extend"
                               else "".join(f"E{e.number:02d}" for e in eps[1:]))
    return v


def _strip_part(title: str) -> str:
    return re.sub(r"\s*\((?:Part\s*)?\d+\)$", "", title)


def _file_values(f: dict) -> dict:
    return {
        "Quality Full": quality_full(f.get("quality", ""), f.get("revision", 0)) if f.get("quality") else "",
        "Quality Title": f.get("quality", ""),
        "Release Group": f.get("release_group"),
        "Edition Tags": f.get("edition"),
        "MediaInfo VideoCodec": f.get("codec"),
        "MediaInfo VideoDynamicRange": "HDR" if f.get("hdr") else "",
        "MediaInfo VideoDynamicRangeType": " ".join(f.get("hdr") or []),
        "MediaInfo AudioCodec": (f.get("audio") or [None])[0],
        "MediaInfo AudioChannels": f.get("audio_channels"),
        "Languages": "+".join(l[:2].upper() for l in (f.get("languages") or []) if l != "multi"),
        "Original Title": f.get("release_name"),
    }


def render_episode_file(template: str, values: dict, colon_replacement: str = " - ") -> str:
    """Episode files: inject the multi-episode suffix right after the first {episode:..} token."""
    suffix = values.get("episode_suffix")
    if suffix:
        template = re.sub(r"(\{episode:0+\})", lambda m: m.group(1) + suffix.replace("{", "{{"), template, count=1)
    return render(template, values, colon_replacement)
