"""Release name parser.

Understands scene/P2P naming for movies and TV (incl. daily and anime), quality markers,
languages (incl. the German scene conventions ``German.DL`` / ``ML`` / ``Subbed``),
codecs, HDR, audio, editions, proper/repack revisions and release groups.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Optional

from . import qualities

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".m4v", ".ts", ".m2ts", ".wmv", ".mov", ".mpg", ".mpeg", ".webm", ".flv", ".iso", ".vob",
    ".divx", ".ogm", ".3gp", ".rmvb",
}
_EXT_RE = re.compile(r"\.(mkv|mp4|avi|m4v|ts|m2ts|wmv|mov|mpg|mpeg|webm|flv|iso|vob|divx|nzb|torrent|rar|par2|srt)$", re.I)

S = r"[ ._\-\[\]()]"  # separator class
B = rf"(?:^|(?<={S}))"  # token start
E = rf"(?=$|{S})"  # token end


def _tok(pattern: str) -> re.Pattern:
    return re.compile(B + "(?:" + pattern + ")" + E, re.I)


# ---------------------------------------------------------------------------------------- quality
RES_PATTERNS = [
    (2160, _tok(r"2160p|4k|uhd")),
    (1080, _tok(r"1080[pi]|fullhd|fhd")),
    (720, _tok(r"720p|hd720")),
    (576, _tok(r"576[pi]")),
    (480, _tok(r"480[pi]|sd|640x480|848x480")),
]
SOURCE_PATTERNS = [
    ("brdisk", _tok(r"bd25|bd50|bdmv|bdiso|complete[ ._-]blu-?ray|untouched[ ._-]blu-?ray")),
    ("remux", _tok(r"(?:bd|uhd|bluray)?[ ._-]?remux")),
    ("rawhd", _tok(r"raw-?hd")),
    ("workprint", _tok(r"workprint|wp")),
    ("cam", _tok(r"cam|camrip|hdcam|cam-?rip")),
    ("telesync", _tok(r"ts|telesync|hdts|pdvd|ts-?rip")),
    ("telecine", _tok(r"tc|telecine|hdtc")),
    ("dvdscr", _tok(r"dvdscr|screener|scr|bdscr|dvd-?screener")),
    ("regional", _tok(r"r5|r6")),
    ("bluray", _tok(r"blu-?ray|bdrip|brrip|bd-?rip|br-?rip|bd(?:5|9)|hddvd|hd-dvd")),
    ("webrip", _tok(r"web-?rip|webrip|web-?cap")),
    ("webdl", _tok(r"web-?dl|webdl|web|amzn|nf|dsnp|atvp|hmax|itunes|vudu|dcu|pcok|hulu|ma|stan|crav|joyn|rtlp|mubi|vimeo")),
    ("hdtv", _tok(r"hdtv|hdtvrip|hd-?tv|dvb|dvbrip|dvb-?s2?|hdtv-?rip|sat-?rip-hd")),
    ("sdtv", _tok(r"pdtv|sdtv|dsr|dsrip|tvrip|satrip|dthrip|ppvrip|tv-?rip")),
    ("dvdr", _tok(r"dvd-?r|dvd[59]|dvd-?full|full-?dvd")),
    ("dvd", _tok(r"dvdrip|dvd|ntsc|pal|dvd-?rip|xvidvd")),
]
# streaming service tags are only a webdl hint when nothing stronger matched
_WEAK_WEB = {"amzn", "nf", "dsnp", "atvp", "hmax", "itunes", "vudu", "dcu", "pcok", "hulu", "ma", "stan", "crav",
             "joyn", "rtlp", "mubi", "vimeo"}

CODEC_PATTERNS = [
    ("x265", _tok(r"x\.?265|h\.?265|hevc")),
    ("x264", _tok(r"x\.?264|h\.?264|avc")),
    ("AV1", _tok(r"av1")),
    ("VC-1", _tok(r"vc-?1")),
    ("XviD", _tok(r"xvid|divx")),
    ("MPEG2", _tok(r"mpeg-?2")),
]
HDR_PATTERNS = [
    ("DV", _tok(r"dv|dovi|dolby[ ._-]?vision")),
    ("HDR10+", _tok(r"hdr10\+|hdr10plus|hdr10p")),
    ("HDR10", _tok(r"hdr10")),
    ("HDR", _tok(r"hdr")),
    ("HLG", _tok(r"hlg")),
]
AUDIO_PATTERNS = [
    ("Atmos", _tok(r"atmos")),
    ("TrueHD", _tok(r"true-?hd")),
    ("DTS-X", _tok(r"dts[ ._-]?x")),
    ("DTS-HD MA", _tok(r"dts[ ._-]?hd[ ._-]?ma|dts-?ma")),
    ("DTS-HD", _tok(r"dts[ ._-]?hd")),
    ("DTS", _tok(r"dts(?:[ ._-]?es)?")),
    ("DD+", _tok(r"ddp(?:\d[ ._]?\d)?|dd\+|e-?ac-?3|eac3")),
    ("DD", _tok(r"dd(?:\d[ ._]?\d)?|ac-?3(?:d)?|dolby[ ._-]?digital")),
    ("AAC", _tok(r"aac(?:\d[ ._]?\d)?|aac-?lc")),
    ("FLAC", _tok(r"flac")),
    ("Opus", _tok(r"opus")),
    ("MP3", _tok(r"mp3")),
]
CHANNEL_RE = re.compile(r"(?<![0-9])([1-7])[ ._]([01])(?![0-9])|(?:ddp?|aac|dts|truehd|ac3|eac3|flac)([1-7])[ ._]?([01])", re.I)
EDITION_RE = re.compile(
    B + r"(?P<edition>extended(?:[ ._-]cut|[ ._-]edition)?|director'?s?[ ._-]?cut|dc|unrated|uncut|uncensored|"
    r"theatrical(?:[ ._-]cut)?|imax(?:[ ._-]enhanced)?|remastered|criterion(?:[ ._-]collection)?|special[ ._-]edition|"
    r"final[ ._-]cut|ultimate(?:[ ._-](?:cut|edition))?|collector'?s?[ ._-]edition|anniversary(?:[ ._-]edition)?|"
    r"open[ ._-]matte|fan[ ._-]edit|hybrid)" + E, re.I)
PROPER_RE = _tok(r"proper|repack|rerip")
REAL_RE = re.compile(B + r"REAL" + E)  # case sensitive like the scene
VERSION_RE = re.compile(r"(?<=\d)v(\d)(?=$|[ ._\-\]\[])", re.I)
THREE_D_RE = _tok(r"3d|h-?sbs|h-?ou|half-?sbs")
HC_RE = _tok(r"hc|hcsubs|korsub")

# ---------------------------------------------------------------------------------------- language
LANGUAGE_PATTERNS = [
    ("german", _tok(r"german|deutsch|ger|deu|de")),
    ("english", _tok(r"english|eng|en")),
    ("french", _tok(r"french|truefrench|vff|vf2|vfq|vfi|vostfr|fr")),
    ("spanish", _tok(r"spanish|castellano|esp|espanol|latino")),
    ("italian", _tok(r"italian|ita")),
    ("dutch", _tok(r"dutch|nl|flemish")),
    ("japanese", _tok(r"japanese|jap|jpn")),
    ("korean", _tok(r"korean|kor")),
    ("chinese", _tok(r"chinese|chi|mandarin|cantonese")),
    ("russian", _tok(r"russian|rus")),
    ("polish", _tok(r"polish|pol|pl")),
    ("portuguese", _tok(r"portuguese|por|pt-?br|brazilian")),
    ("swedish", _tok(r"swedish|swe")),
    ("danish", _tok(r"danish|dan")),
    ("norwegian", _tok(r"norwegian|nor")),
    ("finnish", _tok(r"finnish|fin")),
    ("turkish", _tok(r"turkish|tur")),
    ("hindi", _tok(r"hindi")),
    ("czech", _tok(r"czech|cze")),
    ("hungarian", _tok(r"hungarian|hun")),
]
# ambiguous 2-letter codes only count after a quality marker or at known positions
_AMBIGUOUS_LANG_TOKENS = {"de", "en", "fr", "nl", "pl", "pt", "ger", "eng", "ita", "por", "fin", "nor", "dan", "pol",
                          "rus", "kor", "chi", "jap", "tur", "cze", "hun", "swe", "esp", "deu", "jpn"}
DL_RE = re.compile(B + r"(?:dl|dual[ ._-]?(?:language|audio)?|dual)" + E, re.I)
ML_RE = re.compile(B + r"(?:ml|multi(?:[ ._-]?(?:language|lang|audio))?|multilang)" + E, re.I)
SUBBED_RE = _tok(r"subbed|sub|subs|vostfr|hardsub")
DUBBED_RE = _tok(r"dubbed|dub|synchro|synced|ld|md|line[ ._-]?dubbed|mic[ ._-]?dubbed")

# ---------------------------------------------------------------------------------------- tv
SXXEXX_RE = re.compile(rf"(?:^|{S})S(?P<season>\d{{1,4}})[ ._]?E(?P<ep>\d{{1,4}})", re.I)
MULTI_EP_RE = re.compile(r"^(?:(?P<sep>[ ._]?-[ ._]?|[ ._]?)E(?P<ep>\d{1,4})|(?P<dash>-)(?P<ep2>\d{1,4})(?![\dp]))", re.I)
NXNN_RE = re.compile(rf"(?:^|{S})(?P<season>\d{{1,2}})x(?P<ep>\d{{2,3}})(?:-?x?(?P<ep2>\d{{2,3}}))?(?=$|{S})", re.I)
DAILY_RE = re.compile(rf"(?:^|{S})(?P<y>(?:19|20)\d{{2}})[ ._-](?P<m>0[1-9]|1[0-2])[ ._-](?P<d>0[1-9]|[12]\d|3[01])(?=$|{S})")
MULTI_SEASON_RE = re.compile(rf"(?:^|{S})S(?P<s1>\d{{1,2}})[ ._]?-[ ._]?S?(?P<s2>\d{{1,2}})(?=$|{S})", re.I)
SEASON_RE = re.compile(rf"(?:^|{S})(?:S(?P<s>\d{{1,4}})|(?:season|staffel|saison|temporada|stagione)[ ._-]?(?P<s2>\d{{1,4}}))(?=$|{S})", re.I)
COMPLETE_RE = _tok(r"complete[ ._-]series|complete|komplett|integrale")
ANIME_RE = re.compile(r"^\[(?P<group>[^\]]+)\][ ._]*(?P<title>.+?)[ ._]+(?:-[ ._]+)?(?:(?:S(?P<season>\d{1,2})[ ._]?E)?|E(?:P|pisode)?[ ._]?)?(?P<abs>\d{2,4})(?:v(?P<v>\d))?(?:[ ._]?-[ ._]?(?P<abs2>\d{2,4}))?(?=$|[ ._\[\(])", re.I)
ANIME_NOGROUP_RE = re.compile(r"^(?P<title>.+?)[ ._]+-[ ._]+(?P<abs>\d{2,4})(?:v(?P<v>\d))?(?:[ ._]?-[ ._]?(?P<abs2>\d{2,4}))?(?=$|[ ._\[\(])", re.I)
CRC_RE = re.compile(r"\[(?P<crc>[0-9A-F]{8})\]", re.I)

YEAR_RE = re.compile(rf"(?:^|{S})(?P<year>(?:19|20)\d{{2}})(?=$|{S})")
GROUP_RE = re.compile(r"-(?P<group>[A-Za-z0-9_.@!&]+?)(?:\[[^\]]+\]|\.[a-z]{2,4})?$")
_BAD_GROUPS = {"dl", "x264", "x265", "h264", "h265", "hevc", "web", "webdl", "1080p", "720p", "2160p", "dts", "ac3",
               "hd", "sd", "ma", "rip", "ger", "german", "eng"}


@dataclass
class ParsedRelease:
    raw: str
    title: str = ""
    clean_title: str = ""
    year: Optional[int] = None
    # tv
    is_tv: bool = False
    seasons: list[int] = field(default_factory=list)
    episodes: list[int] = field(default_factory=list)
    absolute_episodes: list[int] = field(default_factory=list)
    air_date: Optional[str] = None
    full_season: bool = False
    multi_season: bool = False
    complete_series: bool = False
    is_anime: bool = False
    special: bool = False
    # quality
    source: str = "unknown"
    resolution: int = 0
    quality: str = "Unknown"
    revision: int = 0
    real: int = 0
    codec: Optional[str] = None
    hdr: list[str] = field(default_factory=list)
    audio: list[str] = field(default_factory=list)
    audio_channels: Optional[str] = None
    three_d: bool = False
    hardcoded_subs: bool = False
    # misc
    languages: list[str] = field(default_factory=list)
    subbed: bool = False
    edition: Optional[str] = None
    release_group: Optional[str] = None
    crc: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def season(self) -> Optional[int]:
        return self.seasons[0] if self.seasons else None


# -------------------------------------------------------------------------------------------- utils
_TRANSLIT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe", "Ü": "ue", "ß": "ss", "&": " and "})


def normalize_title(title: str) -> str:
    """Comparable form of a title: lowercase alphanumerics, umlauts transliterated, articles removed."""
    t = (title or "").translate(_TRANSLIT)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.lower()
    t = re.sub(r"['`´’]", "", t)
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    t = re.sub(r"^(the|a|an|der|die|das|le|la|les) ", "", t)
    t = re.sub(r" (und|and) ", " ", f" {t} ").strip()
    return t.replace(" ", "")


def title_variants(title: str) -> set[str]:
    """Normalized variants (with/without year suffix, with umlauts reduced) for matching."""
    out = {normalize_title(title)}
    stripped = re.sub(r"\s*\((?:19|20)\d{2}\)\s*$", "", title or "")
    out.add(normalize_title(stripped))
    plain = unicodedata.normalize("NFKD", stripped)
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    out.add(normalize_title(plain))
    out.discard("")
    return out


def _clean_display_title(t: str) -> str:
    t = re.sub(r"^\[[^\]]*\][ ._]*", "", t)
    t = t.replace("_", " ")
    # keep dots in abbreviations like "S.W.A.T." but replace separators
    if t.count(".") > 1 and t.count(" ") == 0:
        t = re.sub(r"(?<=\w)\.(?=\w{2,}|\d)", " ", t)
        t = re.sub(r"(?<=\w{2})\.(?=\w)", " ", t)
    t = re.sub(r"[ ._]+", " ", t)
    t = re.sub(r"[\s\-\(\[]+$", "", t)
    return t.strip(" -.")


def strip_extension(name: str) -> str:
    return _EXT_RE.sub("", name.strip())


# -------------------------------------------------------------------------------------------- parse
def _parse_quality(name: str, p: ParsedRelease) -> int:
    """Fill quality fields, returns index of the first quality marker (for title extraction)."""
    first = len(name)
    for res, pat in RES_PATTERNS:
        m = pat.search(name)
        if m:
            p.resolution = res
            first = min(first, m.start())
            break
    src_found = None
    weak = None
    for src, pat in SOURCE_PATTERNS:
        for m in pat.finditer(name):
            tok = m.group(0).strip(" ._-[]()").lower()
            # 'ts' / 'tc' / 'dc' etc. are only trusted after the title part
            if src in ("telesync", "telecine", "workprint", "regional") and m.start() < len(name) * 0.35:
                continue
            if src == "webdl" and tok in _WEAK_WEB:
                weak = weak or (src, m.start())
                continue
            src_found = src
            first = min(first, m.start())
            break
        if src_found:
            break
    if not src_found and weak:
        src_found = weak[0]
        first = min(first, weak[1])
    if src_found == "dvd" and p.resolution >= 720:
        src_found = "bluray"  # "DVD" upscales are rare; usually mislabeled bluray encodes
    if src_found == "remux" and p.resolution == 0:
        p.resolution = 1080
    if not src_found and p.resolution:
        src_found = "webdl" if p.resolution >= 2160 else "hdtv"
    p.source = src_found or "unknown"
    q = qualities.from_source_resolution(p.source, p.resolution)
    p.quality = q.name
    if not p.resolution:
        p.resolution = q.resolution

    for codec, pat in CODEC_PATTERNS:
        m = pat.search(name)
        if m:
            p.codec = codec
            first = min(first, m.start())
            break
    for tag, pat in HDR_PATTERNS:
        if pat.search(name) and not (tag == "HDR" and any(h.startswith("HDR") for h in p.hdr)):
            p.hdr.append(tag)
    for tag, pat in AUDIO_PATTERNS:
        if pat.search(name):
            if tag == "DTS" and any(a.startswith("DTS") for a in p.audio):
                continue
            if tag == "DD" and "DD+" in p.audio:
                continue
            p.audio.append(tag)
    m = CHANNEL_RE.search(name)
    if m:
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        p.audio_channels = f"{a}.{b}"

    p.revision = len(PROPER_RE.findall(name))
    if REAL_RE.search(name):
        p.real = 1
    vm = VERSION_RE.search(name)
    if vm and int(vm.group(1)) > 1:
        p.revision = max(p.revision, int(vm.group(1)) - 1)
    p.three_d = bool(THREE_D_RE.search(name))
    p.hardcoded_subs = bool(HC_RE.search(name))
    em = EDITION_RE.search(name)
    if em:
        ed = em.group("edition").replace(".", " ").replace("_", " ")
        p.edition = re.sub(r"\s+", " ", ed).title().replace("Directors", "Director's").replace("'S", "'s")
    return first


def _parse_languages(name: str, p: ParsedRelease, title_end: int) -> None:
    found: list[str] = []
    for lang, pat in LANGUAGE_PATTERNS:
        for m in pat.finditer(name):
            tok = m.group(0).strip(" ._-[]()").lower()
            if tok in _AMBIGUOUS_LANG_TOKENS and m.start() < title_end:
                continue
            if lang not in found:
                found.append(lang)
            break
    subbed = bool(SUBBED_RE.search(name[title_end:])) and not DUBBED_RE.search(name[title_end:])
    if subbed and "german" in found and len(found) == 1:
        # German.Subbed => original audio (assume english) with german subs
        p.subbed = True
        found = ["english"]
    if DL_RE.search(name[title_end:]) and found and "english" not in found:
        found.append("english")  # DL = dual language: given language + original
    if ML_RE.search(name[title_end:]):
        if "english" not in found:
            found.append("english")
        found.append("multi")
    p.languages = found or ["english"]


def _set_title(p: ParsedRelease, raw_title: str) -> None:
    t = _clean_display_title(raw_title)
    m = YEAR_RE.search(t)
    if m and p.year is None and p.is_tv:
        # "Show 2019 S01E01" -> year belongs to the show title for disambiguation
        if m.end() >= len(t) - 1:
            p.year = int(m.group("year"))
            t = t[: m.start()].strip(" -")
    p.title = t.strip()
    p.clean_title = normalize_title(p.title)


def parse(release: str) -> ParsedRelease:
    raw = release
    name = strip_extension(release.strip())
    name = re.sub(r"^www\.[a-z0-9-]+\.[a-z]{2,4}[ ._-]+", "", name, flags=re.I)  # "www.site.org - "
    p = ParsedRelease(raw=raw)

    # release group / anime crc
    cm = CRC_RE.search(name)
    if cm:
        p.crc = cm.group("crc").upper()
    gm = re.match(r"^\[(?P<group>[^\]]+)\]", name)
    if gm:
        p.release_group = gm.group("group").strip()
        p.is_anime = True
    else:
        g = GROUP_RE.search(name)
        if g and g.group("group").lower() not in _BAD_GROUPS and not g.group("group").isdigit():
            p.release_group = g.group("group")

    q_start = _parse_quality(name, p)

    # ---- TV detection
    title_end: Optional[int] = None
    m = SXXEXX_RE.search(name)
    if m:
        p.is_tv = True
        season = int(m.group("season"))
        eps = [int(m.group("ep"))]
        rest = name[m.end():]
        while True:
            mm = MULTI_EP_RE.match(rest)
            if not mm:
                break
            if mm.group("ep") is not None:
                n = int(mm.group("ep"))
                is_range = bool(mm.group("sep") and "-" in mm.group("sep"))
            else:
                n = int(mm.group("ep2"))
                is_range = True
            if n <= eps[-1] or n - eps[-1] > 50:
                break
            if is_range:
                eps.extend(range(eps[-1] + 1, n + 1))
            else:
                eps.append(n)
            rest = rest[mm.end():]
        p.seasons = [season]
        p.episodes = eps
        title_end = m.start()
    if title_end is None:
        m = NXNN_RE.search(name)
        if m and not re.match(r"\d{3,4}x\d{3,4}", name[m.start():].strip(" ._-")):
            p.is_tv = True
            p.seasons = [int(m.group("season"))]
            e1 = int(m.group("ep"))
            p.episodes = [e1] + ([*range(e1 + 1, int(m.group("ep2")) + 1)] if m.group("ep2") else [])
            title_end = m.start()
    if title_end is None:
        m = DAILY_RE.search(name)
        if m:
            p.is_tv = True
            p.air_date = f"{m.group('y')}-{m.group('m')}-{m.group('d')}"
            title_end = m.start()
    if title_end is None:
        m = MULTI_SEASON_RE.search(name)
        if m:
            s1, s2 = int(m.group("s1")), int(m.group("s2"))
            if s2 >= s1:
                p.is_tv = True
                p.seasons = list(range(s1, s2 + 1))
                p.full_season = True
                p.multi_season = True
                title_end = m.start()
    if title_end is None:
        m = SEASON_RE.search(name)
        if m:
            p.is_tv = True
            p.seasons = [int(m.group("s") or m.group("s2"))]
            p.full_season = True
            title_end = m.start()
            # "Season 1-3"
            more = re.match(r"[ ._]?-[ ._]?(\d{1,2})(?=$|[ ._-])", name[m.end():])
            if more and int(more.group(1)) > p.seasons[0]:
                p.seasons = list(range(p.seasons[0], int(more.group(1)) + 1))
                p.multi_season = True
    if title_end is None and p.is_anime:
        m = ANIME_RE.match(name)
        if m:
            p.is_tv = True
            a1 = int(m.group("abs"))
            a2 = int(m.group("abs2")) if m.group("abs2") else a1
            if a1 not in (480, 576, 720, 1080, 2160) and a2 - a1 < 200:
                p.absolute_episodes = list(range(a1, a2 + 1))
                if m.group("season"):
                    p.seasons = [int(m.group("season"))]
                    p.episodes = [a1]
                    p.absolute_episodes = []
                if m.group("v"):
                    p.revision = max(p.revision, int(m.group("v")) - 1)
                title_end = m.start("title") + len(m.group("title"))
                _set_title(p, m.group("title"))
    if title_end is None:
        m = ANIME_NOGROUP_RE.match(name)
        if m and int(m.group("abs")) not in (480, 576, 720, 1080, 2160) and not YEAR_RE.fullmatch(" " + m.group("abs")):
            p.is_tv = True
            p.is_anime = True
            a1 = int(m.group("abs"))
            a2 = int(m.group("abs2")) if m.group("abs2") else a1
            p.absolute_episodes = list(range(a1, a2 + 1))
            title_end = m.end("title")
            _set_title(p, m.group("title"))

    if p.is_tv:
        if COMPLETE_RE.search(name) and (p.full_season or not p.seasons):
            p.complete_series = not p.seasons or p.multi_season
        if p.seasons and p.seasons[0] == 0:
            p.special = True
        if not p.title and title_end is not None:
            _set_title(p, name[:title_end])
        _parse_languages(name, p, title_end or 0)
        return p

    # ---- movie
    end = q_start
    lang_m = None
    for _lang, pat in LANGUAGE_PATTERNS[:3]:
        lm = pat.search(name)
        if lm and lm.group(0).strip(" ._-[]()").lower() not in _AMBIGUOUS_LANG_TOKENS:
            lang_m = lm if lang_m is None or lm.start() < lang_m.start() else lang_m
    if lang_m and lang_m.start() > 0:
        end = min(end, lang_m.start())
    for pat in (EDITION_RE, PROPER_RE, THREE_D_RE, ML_RE, DL_RE):
        mm = pat.search(name)
        if mm and mm.start() > 0:
            end = min(end, mm.start())
    head = name[:end]
    years = [y for y in YEAR_RE.finditer(head) if y.start() > 0]
    if years:
        y = years[-1]
        p.year = int(y.group("year"))
        title_part = head[: y.start()]
    else:
        title_part = head
        # fall back: year after the marker area (e.g. "Title.German.2019.1080p")
        y2 = YEAR_RE.search(name, end)
        if y2:
            p.year = int(y2.group("year"))
    if p.release_group and title_part.endswith("-" + p.release_group):
        title_part = title_part[: -len(p.release_group) - 1]
    p.title = _clean_display_title(re.sub(r"[\(\[]\s*$", "", title_part))
    p.clean_title = normalize_title(p.title)
    _parse_languages(name, p, len(title_part))
    return p


def parse_path(path: str) -> ParsedRelease:
    """Parse a file path: combine file name with parent folder name when the file name is obfuscated."""
    import os

    base = os.path.basename(path)
    folder = os.path.basename(os.path.dirname(path))
    pf = parse(base)
    if folder:
        pd = parse(folder)
        weak_file = (pf.quality == "Unknown" or not pf.clean_title or len(base) < 12
                     or re.fullmatch(r"[a-z0-9]{8,}", os.path.splitext(base)[0], re.I))
        if weak_file and pd.clean_title:
            # keep episode info from file if present (season pack folders)
            if pf.is_tv and (pf.episodes or pf.absolute_episodes or pf.air_date):
                pd.episodes, pd.absolute_episodes, pd.air_date = pf.episodes, pf.absolute_episodes, pf.air_date
                pd.seasons = pf.seasons or pd.seasons
                pd.full_season = False
            return pd
        if pf.quality == "Unknown" and pd.quality != "Unknown":
            pf.quality, pf.source, pf.resolution = pd.quality, pd.source, pd.resolution
        if not pf.release_group and pd.release_group:
            pf.release_group = pd.release_group
        if pf.languages == ["english"] and pd.languages != ["english"]:
            pf.languages = pd.languages
    return pf
