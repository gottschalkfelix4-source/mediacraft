"""Reading real stream information from video files (ffprobe or MediaInfo CLI).

Release names lie now and then ("German.DL" with only an English track). The probe result tells which
audio languages, codecs, resolution and HDR format the file really has.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Optional

log = logging.getLogger("mediainfo")

# ISO 639-1/-2 codes -> language names used by the parser
ISO_LANGS = {
    "german": ("de", "ger", "deu", "gsw"), "english": ("en", "eng"), "french": ("fr", "fre", "fra"),
    "spanish": ("es", "spa"), "italian": ("it", "ita"), "dutch": ("nl", "dut", "nld"), "japanese": ("ja", "jpn"),
    "korean": ("ko", "kor"), "chinese": ("zh", "chi", "zho", "cmn", "yue"), "russian": ("ru", "rus"),
    "polish": ("pl", "pol"), "portuguese": ("pt", "por"), "swedish": ("sv", "swe"), "danish": ("da", "dan"),
    "norwegian": ("no", "nor", "nob", "nno"), "finnish": ("fi", "fin"), "turkish": ("tr", "tur"),
    "hindi": ("hi", "hin"), "czech": ("cs", "cze", "ces"), "hungarian": ("hu", "hun"),
}
_CODE_TO_LANG = {code: lang for lang, codes in ISO_LANGS.items() for code in codes}


def language(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    return _CODE_TO_LANG.get(code.strip().lower().split("-")[0])


def tool() -> Optional[str]:
    for name in ("ffprobe", "mediainfo"):
        if shutil.which(name):
            return name
    return None


def _resolution(width: int, height: int) -> int:
    # by width first: 1920x800 scope films are still 1080p
    if width >= 3200 or height >= 1800:
        return 2160
    if width >= 1800 or height >= 1000:
        return 1080
    if width >= 1200 or height >= 700:
        return 720
    if height >= 560:
        return 576
    return 480 if height else 0


def _video_codec(name: str) -> str:
    n = (name or "").lower()
    return {"hevc": "x265", "h265": "x265", "avc": "x264", "h264": "x264", "av1": "AV1", "vp9": "VP9",
            "mpeg-4 visual": "XviD", "mpeg4": "XviD", "mpeg2video": "MPEG2", "mpeg video": "MPEG2"}.get(n, name or "")


def _from_ffprobe(data: dict) -> dict:
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"
                  and not (s.get("disposition") or {}).get("attached_pic")), {})
    audio = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    subs = [s for s in data.get("streams", []) if s.get("codec_type") == "subtitle"]
    hdr = None
    if any((sd.get("side_data_type") or "").startswith("DOVI") for sd in video.get("side_data_list") or []):
        hdr = "DV"
    elif video.get("color_transfer") == "smpte2084":
        hdr = "HDR10"
    elif video.get("color_transfer") == "arib-std-b67":
        hdr = "HLG"
    fmt = data.get("format") or {}
    return {
        "video_codec": _video_codec(video.get("codec_name", "")), "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0), "hdr": hdr,
        "audio_tracks": [{"codec": (a.get("codec_name") or "").upper(), "channels": a.get("channels"),
                          "language": (a.get("tags") or {}).get("language"),
                          "title": (a.get("tags") or {}).get("title")} for a in audio],
        "subtitle_languages": [(s.get("tags") or {}).get("language") for s in subs if (s.get("tags") or {}).get("language")],
        "duration_min": round(float(fmt.get("duration") or 0) / 60, 1),
        "bitrate_kbps": int(int(fmt.get("bit_rate") or 0) / 1000),
    }


def _from_mediainfo(data: dict) -> dict:
    tracks = (data.get("media") or {}).get("track") or []
    general = next((t for t in tracks if t.get("@type") == "General"), {})
    video = next((t for t in tracks if t.get("@type") == "Video"), {})
    audio = [t for t in tracks if t.get("@type") == "Audio"]
    subs = [t for t in tracks if t.get("@type") == "Text"]
    hdr_fmt = (video.get("HDR_Format") or "") + " " + (video.get("HDR_Format_Compatibility") or "")
    hdr = "DV" if "Dolby Vision" in hdr_fmt else "HDR10+" if "2094" in hdr_fmt else "HDR10" if (
        "2086" in hdr_fmt or "HDR10" in hdr_fmt or video.get("transfer_characteristics") == "PQ") else (
        "HLG" if video.get("transfer_characteristics") == "HLG" else None)

    def num(v) -> int:
        try:
            return int(float(str(v).split()[0]))
        except (TypeError, ValueError, IndexError):
            return 0

    return {
        "video_codec": _video_codec(video.get("Format", "")), "width": num(video.get("Width")),
        "height": num(video.get("Height")), "hdr": hdr,
        "audio_tracks": [{"codec": a.get("Format_Commercial_IfAny") or a.get("Format"), "channels": num(a.get("Channels")),
                          "language": a.get("Language"), "title": a.get("Title")} for a in audio],
        "subtitle_languages": [s.get("Language") for s in subs if s.get("Language")],
        "duration_min": round(float(general.get("Duration") or 0) / 60, 1),
        "bitrate_kbps": int(num(general.get("OverallBitRate")) / 1000),
    }


def probe(path: str, timeout: int = 120) -> Optional[dict]:
    """Stream info of a video file, or None when no tool is installed or the file can't be read."""
    t = tool()
    if not t:
        return None
    cmd = ([t, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path] if t == "ffprobe"
           else [t, "--Output=JSON", path])
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        data = json.loads(out.stdout or b"{}")
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        log.warning("Mediainfo für %s nicht lesbar: %s", path, e)
        return None
    info = _from_ffprobe(data) if t == "ffprobe" else _from_mediainfo(data)
    if not info["width"] and not info["audio_tracks"]:
        return None
    info["resolution"] = _resolution(info["width"], info["height"])
    langs = [language(a["language"]) for a in info["audio_tracks"]]
    info["audio_languages"] = list(dict.fromkeys(lang for lang in langs if lang))
    info["tool"] = t
    return info


def apply(mf, probe_result: Optional[dict], update_languages: bool = True) -> None:
    """Store a probe result on a MediaFile; real audio languages replace those guessed from the name."""
    if not probe_result:
        return
    mi = dict(mf.media_info or {})
    first = (probe_result["audio_tracks"] or [{}])[0]
    mi.update(probe=probe_result, probed=True, codec=probe_result["video_codec"] or mi.get("codec"),
              hdr=probe_result["hdr"] or mi.get("hdr"), audio=first.get("codec") or mi.get("audio"),
              channels=first.get("channels") or mi.get("channels"))
    claimed = list(mf.languages or [])
    real = probe_result["audio_languages"]
    if real and set(claimed) - set(real) - {"multi", "original"}:
        mi["language_mismatch"] = claimed  # e.g. named German.DL, but no German track
    else:
        mi.pop("language_mismatch", None)
    mf.media_info = mi
    if update_languages and real:
        mf.languages = real
