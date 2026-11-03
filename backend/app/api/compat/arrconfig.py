"""Configuration endpoints for tools that manage Sonarr/Radarr settings, and file details for Bazarr.

* Recyclarr (TRaSH guides): custom formats, quality definitions, quality profiles (scores, cutoff,
  qualities), naming and media management.
* Bazarr: movie/episode files with release (scene) name, audio/subtitle languages and media info.
* Dashboards: history.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...core import qualities
from ...core import settings as settings_mod
from ...db import get_db
from ...models import CustomFormat, Episode, History, MediaFile, Movie, QualityProfile, Series, iso
from .base import LANG_IDS, _languages, _profiles, _quality

# ---------------------------------------------------------------------------------- custom formats
# Source enums differ between Radarr and Sonarr
RADARR_SOURCES = {0: "unknown", 1: "cam", 2: "telesync", 3: "telecine", 4: "workprint", 5: "dvd", 6: "hdtv",
                  7: "webdl", 8: "webrip", 9: "bluray"}
SONARR_SOURCES = {0: "unknown", 1: "hdtv", 2: "raw", 3: "webdl", 4: "webrip", 5: "dvd", 6: "bluray", 7: "remux"}
QUALITY_MODIFIERS = {1: "regional", 2: "dvdscr", 3: "rawhd", 4: "brdisk", 5: "remux"}  # Radarr
INDEXER_FLAGS = {1: "freeleech", 2: "halfleech", 4: "doubleupload", 8: "internal", 16: "scene", 32: "freeleech75",
                 64: "freeleech25", 128: "nuked"}
LANG_NAMES = {v: k for k, v in LANG_IDS.items()}
NEVER = "(?!x)x"  # regex that never matches: stands in for specifications we can't evaluate


def _fields(spec: dict) -> dict:
    f = spec.get("fields") or {}
    if isinstance(f, list):
        return {x.get("name"): x.get("value") for x in f}
    return dict(f)


def spec_to_condition(spec: dict, flavor: str) -> dict:
    impl = spec.get("implementation", "")
    f = _fields(spec)
    v = f.get("value")
    cond = {"negate": bool(spec.get("negate")), "required": bool(spec.get("required")),
            "name": spec.get("name") or "", "implementation": impl}
    if impl == "ReleaseTitleSpecification":
        cond.update(type="title", value=str(v or ""))
    elif impl == "ReleaseGroupSpecification":
        cond.update(type="group", value=str(v or ""))
    elif impl == "EditionSpecification":
        cond.update(type="edition", value=str(v or ""))
    elif impl == "ResolutionSpecification":
        cond.update(type="resolution", value=str(int(v or 0)))
    elif impl == "SourceSpecification":
        src = (SONARR_SOURCES if flavor == "sonarr" else RADARR_SOURCES).get(int(v or 0), "unknown")
        cond.update(type="source", value=src)
    elif impl == "QualityModifierSpecification" and int(v or 0) in QUALITY_MODIFIERS:
        cond.update(type="source", value=QUALITY_MODIFIERS[int(v or 0)])
    elif impl == "LanguageSpecification":
        cond.update(type="language", value=LANG_NAMES.get(int(v or 0), "unknown"))
    elif impl == "SizeSpecification":
        cond.update(type="size", value=f"{f.get('min') or ''}-{f.get('max') or ''}")
    elif impl == "IndexerFlagSpecification":
        cond.update(type="indexer_flag", value=INDEXER_FLAGS.get(int(v or 0), str(v)))
    else:  # ReleaseTypeSpecification, YearSpecification, …: kept for round trips, never matches
        cond.update(type="title", value=NEVER, unsupported=True, raw=spec)
    return cond


def condition_to_spec(c: dict, flavor: str) -> dict:
    if c.get("raw"):
        return c["raw"]
    t, v = c.get("type"), c.get("value", "")
    impl, value = "ReleaseTitleSpecification", v
    extra: list[dict] = []
    if t == "group":
        impl = "ReleaseGroupSpecification"
    elif t == "edition":
        impl = "EditionSpecification" if flavor == "radarr" else "ReleaseTitleSpecification"
    elif t == "resolution":
        impl, value = "ResolutionSpecification", int(str(v).rstrip("p") or 0)
    elif t == "source":
        table = SONARR_SOURCES if flavor == "sonarr" else RADARR_SOURCES
        ids = {name: i for i, name in table.items()}
        if v in ids:
            impl, value = "SourceSpecification", ids[v]
        elif flavor == "radarr" and v in QUALITY_MODIFIERS.values():
            impl, value = "QualityModifierSpecification", {n: i for i, n in QUALITY_MODIFIERS.items()}[v]
        else:
            value = rf"\b{v}\b"
    elif t == "language":
        impl, value = "LanguageSpecification", LANG_IDS.get(v, 0)
    elif t == "size":
        lo, _, hi = str(v).partition("-")
        impl, value = "SizeSpecification", None
        extra = [{"name": "min", "value": float(lo or 0)}, {"name": "max", "value": float(hi or 0)}]
    elif t == "indexer_flag":
        impl = "IndexerFlagSpecification"
        value = {n: i for i, n in INDEXER_FLAGS.items()}.get(v, 0)
    elif t in ("codec", "hdr", "audio"):
        value = {"x265": r"\b(x265|h\.?265|hevc)\b", "x264": r"\b(x264|h\.?264|avc)\b"}.get(v, rf"\b{v}\b")
    fields = extra if extra else [{"name": "value", "value": value}]
    return {"name": c.get("name") or f"{t}: {v}", "implementation": impl, "implementationName": impl,
            "negate": bool(c.get("negate")), "required": bool(c.get("required")), "fields": fields}


def cf_resource(cf: CustomFormat, flavor: str) -> dict:
    return {"id": cf.id, "name": cf.name, "includeCustomFormatWhenRenaming": False,
            "specifications": [condition_to_spec(c, flavor) for c in cf.conditions or []]}


def _apply_cf(db: Session, cf: CustomFormat, body: dict, flavor: str) -> CustomFormat:
    name = (body.get("name") or cf.name or "").strip()
    if not name:
        raise HTTPException(400, "Name fehlt")
    clash = db.query(CustomFormat).filter(CustomFormat.name == name, CustomFormat.id != cf.id).first()
    if clash:
        raise HTTPException(400, f"Custom Format '{name}' existiert bereits")
    cf.name = name
    cf.conditions = [spec_to_condition(s, flavor) for s in body.get("specifications") or []]
    return cf


# ---------------------------------------------------------------------------------- qualities
SONARR_NAMES = {"Remux-1080p": "Bluray-1080p Remux", "Remux-2160p": "Bluray-2160p Remux"}
ALIASES = {**{v: k for k, v in SONARR_NAMES.items()}, "WEBDL-1080p": "WEBDL-1080p"}


def _arr_name(name: str, flavor: str) -> str:
    return SONARR_NAMES.get(name, name) if flavor == "sonarr" else name


def _our_quality(q: dict) -> Optional[str]:
    """Quality name from a Sonarr/Radarr quality object (by id = our rank, else by name)."""
    by_rank = {x.rank: x.name for x in qualities.QUALITIES.values()}
    name = q.get("name") or ""
    if name in qualities.QUALITIES:
        return name
    if ALIASES.get(name) in qualities.QUALITIES:
        return ALIASES[name]
    return by_rank.get(q.get("id"))


def quality_definitions(db: Session, flavor: str) -> list[dict]:
    sizes = settings_mod.get(db, "media").get("quality_sizes") or {}
    out = []
    for q in sorted(qualities.QUALITIES.values(), key=lambda q: q.rank):
        own = sizes.get(q.name) or {}
        mn, mx = own.get("min", q.min_mb_min), own.get("max", q.max_mb_min)
        qd = _quality(q.name)["quality"]
        qd["name"] = _arr_name(q.name, flavor)
        out.append({"id": q.rank, "quality": qd, "title": qd["name"], "weight": q.rank + 1, "minSize": mn,
                    "maxSize": mx or None, "preferredSize": mx or None})
    return out


def _save_definitions(db: Session, items: list[dict]) -> None:
    sizes = dict(settings_mod.get(db, "media").get("quality_sizes") or {})
    for d in items:
        name = _our_quality(d.get("quality") or {}) or _our_quality({"name": d.get("title"), "id": d.get("id")})
        if not name:
            continue
        q = qualities.QUALITIES[name]
        mn, mx = float(d.get("minSize") or 0), float(d.get("maxSize") or 0)
        if (mn, mx) == (q.min_mb_min, q.max_mb_min):
            sizes.pop(name, None)
        else:
            sizes[name] = {"min": mn, "max": mx}
    settings_mod.replace_key(db, "media", "quality_sizes", sizes)


def _apply_profile(db: Session, p: QualityProfile, body: dict) -> QualityProfile:
    if body.get("name"):
        p.name = body["name"]
    if "upgradeAllowed" in body:
        p.upgrade_allowed = bool(body["upgradeAllowed"])
    if "minFormatScore" in body:
        p.min_format_score = int(body["minFormatScore"] or 0)
    if "cutoffFormatScore" in body:
        p.cutoff_format_score = int(body["cutoffFormatScore"] or 0)
    if body.get("formatItems") is not None:
        scores = {str(fi["format"]): int(fi.get("score") or 0) for fi in body["formatItems"] if fi.get("format")}
        p.format_scores = {k: v for k, v in scores.items() if v}
    groups: dict[int, list[str]] = {}
    if body.get("items"):
        items, seen = [], set()
        for it in body["items"]:  # lowest -> highest; groups are flattened in their order
            members = it.get("items") or [it]
            names = [n for n in (_our_quality(m.get("quality") or {}) for m in members) if n]
            if it.get("id") is not None and it.get("items"):
                groups[int(it["id"])] = names
            for n in names:
                if n not in seen:
                    seen.add(n)
                    items.append({"quality": n, "allowed": bool(it.get("allowed"))})
        p.items = items
    if body.get("cutoff") is not None:
        cid = int(body["cutoff"])
        name = groups[cid][0] if cid in groups and groups[cid] else _our_quality({"id": cid})
        if name:
            p.cutoff = name
    return p


# ---------------------------------------------------------------------------------- naming / media management
COLONS = {"": "delete", "-": "dash", " -": "spaceDash", " - ": "spaceDashSpace"}
SONARR_COLONS = ["delete", "dash", "spaceDash", "spaceDashSpace", "smart"]
MULTI_EP = ["extend", "duplicate", "repeat", "scene", "range", "prefixedRange"]


def naming(db: Session, flavor: str) -> dict:
    m = settings_mod.get(db, "media")
    colon = COLONS.get(m.get("colon_replacement", " - "), "spaceDashSpace")
    if flavor == "radarr":
        return {"id": 1, "renameMovies": m.get("rename", True), "replaceIllegalCharacters": True,
                "colonReplacementFormat": colon, "standardMovieFormat": m["movie_file"],
                "movieFolderFormat": m["movie_folder"]}
    return {"id": 1, "renameEpisodes": m.get("rename", True), "replaceIllegalCharacters": True,
            "colonReplacementFormat": SONARR_COLONS.index(colon), "customColonReplacementFormat": "",
            "multiEpisodeStyle": MULTI_EP.index(m.get("multi_episode_style", "extend"))
            if m.get("multi_episode_style", "extend") in MULTI_EP else 0,
            "standardEpisodeFormat": m["episode_file"], "dailyEpisodeFormat": m["daily_file"],
            "animeEpisodeFormat": m["anime_file"], "seriesFolderFormat": m["series_folder"],
            "seasonFolderFormat": m["season_folder"], "specialsFolderFormat": m["specials_folder"]}


def save_naming(db: Session, flavor: str, body: dict) -> dict:
    patch: dict = {}
    colon = body.get("colonReplacementFormat")
    if isinstance(colon, int) and 0 <= colon < len(SONARR_COLONS):
        colon = SONARR_COLONS[colon]
    rev = {v: k for k, v in COLONS.items()}
    if colon in rev:
        patch["colon_replacement"] = rev[colon]
    keys = ({"renameMovies": "rename", "standardMovieFormat": "movie_file", "movieFolderFormat": "movie_folder"}
            if flavor == "radarr" else
            {"renameEpisodes": "rename", "standardEpisodeFormat": "episode_file", "dailyEpisodeFormat": "daily_file",
             "animeEpisodeFormat": "anime_file", "seriesFolderFormat": "series_folder",
             "seasonFolderFormat": "season_folder", "specialsFolderFormat": "specials_folder"})
    for src, dst in keys.items():
        if body.get(src) is not None:
            patch[dst] = body[src]
    if flavor == "sonarr" and isinstance(body.get("multiEpisodeStyle"), int):
        style = MULTI_EP[body["multiEpisodeStyle"]] if body["multiEpisodeStyle"] < len(MULTI_EP) else "extend"
        patch["multi_episode_style"] = style if style in ("extend", "duplicate") else "extend"
    settings_mod.update(db, "media", patch)
    return naming(db, flavor)


def media_management(db: Session) -> dict:
    m = settings_mod.get(db, "media")
    return {"id": 1, "downloadPropersAndRepacks": "preferAndUpgrade" if m.get("upgrade_propers", True) else "doNotUpgrade",
            "recycleBin": m.get("recycle_bin") or "", "recycleBinCleanupDays": m.get("recycle_bin_days", 7),
            "deleteEmptyFolders": m.get("delete_empty_folders", True), "copyUsingHardlinks": m.get("use_hardlinks", True),
            "importExtraFiles": m.get("import_extra_files", True), "extraFileExtensions": m.get("extra_extensions", ""),
            "minimumFreeSpaceWhenImporting": m.get("min_free_space_mb", 200), "enableMediaInfo": m.get("probe_files", True),
            "skipFreeSpaceCheckWhenImporting": False, "autoUnmonitorPreviouslyDownloadedEpisodes": False,
            "autoUnmonitorPreviouslyDownloadedMovies": False, "createEmptySeriesFolders": False,
            "createEmptyMovieFolders": False, "episodeTitleRequired": "always", "fileDate": "none",
            "rescanAfterRefresh": "always", "setPermissionsLinux": False, "chmodFolder": "755", "chownGroup": "",
            "autoRenameFolders": False, "pathsDefaultStatic": False, "scriptImportPath": "", "useScriptImport": False}


def save_media_management(db: Session, body: dict) -> dict:
    patch = {}
    if body.get("downloadPropersAndRepacks"):
        patch["upgrade_propers"] = body["downloadPropersAndRepacks"] != "doNotUpgrade"
    for src, dst in (("recycleBin", "recycle_bin"), ("recycleBinCleanupDays", "recycle_bin_days"),
                     ("deleteEmptyFolders", "delete_empty_folders"), ("copyUsingHardlinks", "use_hardlinks"),
                     ("importExtraFiles", "import_extra_files"), ("extraFileExtensions", "extra_extensions"),
                     ("minimumFreeSpaceWhenImporting", "min_free_space_mb"), ("enableMediaInfo", "probe_files")):
        if src in body and body[src] is not None:
            patch[dst] = body[src]
    settings_mod.update(db, "media", patch)
    return media_management(db)


# ---------------------------------------------------------------------------------- files (Bazarr)
def media_info(f: MediaFile) -> dict:
    mi = f.media_info or {}
    probe = mi.get("probe") or {}
    audio = probe.get("audio_tracks") or []
    first = audio[0] if audio else {}
    langs = [a.get("language") or "" for a in audio]
    width, height = probe.get("width"), probe.get("height")
    hdr = probe.get("hdr") or (mi.get("hdr")[0] if isinstance(mi.get("hdr"), list) and mi.get("hdr") else mi.get("hdr"))
    named_audio = mi.get("audio")
    if isinstance(named_audio, list):
        named_audio = named_audio[0] if named_audio else ""
    return {"audioBitrate": 0, "audioChannels": first.get("channels") or mi.get("channels") or 0,
            "audioCodec": first.get("codec") or named_audio or "",
            "audioLanguages": "/".join(x for x in langs if x), "audioStreamCount": len(audio),
            "videoBitDepth": 10 if hdr else 8, "videoBitrate": (probe.get("bitrate_kbps") or 0) * 1000,
            "videoCodec": probe.get("video_codec") or mi.get("codec") or "", "videoDynamicRange": "HDR" if hdr else "",
            "videoDynamicRangeType": hdr or "", "videoFps": 0,
            "resolution": f"{width}x{height}" if width and height else "",
            "runTime": f"{int((probe.get('duration_min') or 0) // 60)}:{int((probe.get('duration_min') or 0) % 60):02d}:00",
            "scanType": "Progressive", "subtitles": "/".join(probe.get("subtitle_languages") or [])}


def episode_file_resource(db: Session, f: MediaFile, series: Series | None = None) -> dict:
    series = series or db.get(Series, f.series_id)
    eps = db.query(Episode).filter(Episode.file_id == f.id).all()
    return {"id": f.id, "seriesId": f.series_id, "seasonNumber": eps[0].season if eps else 0,
            "relativePath": os.path.relpath(f.path, series.path) if series and series.path else os.path.basename(f.path),
            "path": f.path, "size": f.size, "dateAdded": iso(f.added), "sceneName": f.release_name,
            "releaseGroup": f.release_group, "languages": _languages(f.languages), "quality": _quality(f.quality, f.proper),
            "customFormatScore": f.format_score, "mediaInfo": media_info(f), "qualityCutoffNotMet": False}


def movie_file_resource(f: MediaFile, m: Movie) -> dict:
    return {"id": f.id, "movieId": m.id, "relativePath": os.path.relpath(f.path, m.path) if m.path else f.path,
            "path": f.path, "size": f.size, "dateAdded": iso(f.added), "sceneName": f.release_name,
            "releaseGroup": f.release_group, "edition": f.edition or "", "languages": _languages(f.languages),
            "quality": _quality(f.quality, f.proper), "customFormatScore": f.format_score, "mediaInfo": media_info(f),
            "qualityCutoffNotMet": False}


# ---------------------------------------------------------------------------------- history
EVENT_TYPES = {"grabbed": "grabbed", "imported": "downloadFolderImported", "upgraded": "downloadFolderImported",
               "failed": "downloadFailed", "renamed": "{kind}FileRenamed", "deleted": "{kind}FileDeleted",
               "ignored": "downloadIgnored"}


def history_records(db: Session, flavor: str, request: Request) -> dict:
    media = "movie" if flavor == "radarr" else "series"
    q = db.query(History).filter(History.media_type == media)
    if request.query_params.get("movieId"):
        q = q.filter(History.movie_id == int(request.query_params["movieId"]))
    if request.query_params.get("seriesId"):
        q = q.filter(History.series_id == int(request.query_params["seriesId"]))
    page = int(request.query_params.get("page", 1))
    size = int(request.query_params.get("pageSize", 20))
    total = q.count()
    rows = q.order_by(History.date.desc()).offset((page - 1) * size).limit(size).all()
    kind = "movie" if flavor == "radarr" else "episode"
    records = []
    for h in rows:
        rec = {"id": h.id, "eventType": EVENT_TYPES.get(h.event, h.event).format(kind=kind), "date": iso(h.date),
               "sourceTitle": h.source_title, "quality": _quality(h.quality or "Unknown"), "downloadId": h.download_id,
               "languages": _languages((h.data or {}).get("languages") or []),
               "data": {k: str(v) for k, v in (h.data or {}).items() if v is not None}}
        rec.update({"movieId": h.movie_id} if flavor == "radarr" else
                   {"seriesId": h.series_id, "episodeId": (h.episode_ids or [0])[0]})
        records.append(rec)
    return {"page": page, "pageSize": size, "sortKey": "date", "sortDirection": "descending", "totalRecords": total,
            "records": records}


# ---------------------------------------------------------------------------------- routes
def register_arrconfig(router: APIRouter, flavor: str) -> None:
    @router.get("/customformat")
    def custom_formats(db: Session = Depends(get_db)):
        return [cf_resource(cf, flavor) for cf in db.query(CustomFormat).order_by(CustomFormat.id).all()]

    @router.get("/customformat/schema")
    def custom_format_schema():
        impls = ["ReleaseTitleSpecification", "ReleaseGroupSpecification", "SourceSpecification",
                 "ResolutionSpecification", "LanguageSpecification", "SizeSpecification", "IndexerFlagSpecification"]
        if flavor == "radarr":
            impls += ["EditionSpecification", "QualityModifierSpecification"]
        return [{"implementation": i, "implementationName": i, "negate": False, "required": False,
                 "fields": [{"order": 0, "name": "value", "value": None}]} for i in impls]

    @router.get("/customformat/{fid}")
    def custom_format(fid: int, db: Session = Depends(get_db)):
        cf = db.get(CustomFormat, fid)
        if not cf:
            raise HTTPException(404, "not found")
        return cf_resource(cf, flavor)

    @router.post("/customformat", status_code=201)
    def create_custom_format(body: dict, db: Session = Depends(get_db)):
        cf = _apply_cf(db, CustomFormat(), body, flavor)
        db.add(cf)
        db.flush()
        return cf_resource(cf, flavor)

    @router.put("/customformat/{fid}", status_code=202)
    def update_custom_format(fid: int, body: dict, db: Session = Depends(get_db)):
        cf = db.get(CustomFormat, fid)
        if not cf:
            raise HTTPException(404, "not found")
        _apply_cf(db, cf, body, flavor)
        db.flush()
        return cf_resource(cf, flavor)

    @router.delete("/customformat/{fid}")
    def delete_custom_format(fid: int, db: Session = Depends(get_db)):
        cf = db.get(CustomFormat, fid)
        if cf:
            for p in db.query(QualityProfile).all():  # drop its score everywhere
                if str(fid) in (p.format_scores or {}):
                    p.format_scores = {k: v for k, v in p.format_scores.items() if k != str(fid)}
            db.delete(cf)
        return {}

    @router.get("/qualitydefinition")
    def get_quality_definitions(db: Session = Depends(get_db)):
        return quality_definitions(db, flavor)

    @router.put("/qualitydefinition/update", status_code=202)
    def put_quality_definitions(body: list[dict], db: Session = Depends(get_db)):
        _save_definitions(db, body)
        return quality_definitions(db, flavor)

    @router.put("/qualitydefinition/{qid}", status_code=202)
    def put_quality_definition(qid: int, body: dict, db: Session = Depends(get_db)):
        _save_definitions(db, [{**body, "id": qid}])
        return next((d for d in quality_definitions(db, flavor) if d["id"] == qid), {})

    @router.post("/qualityprofile", status_code=201)
    def create_quality_profile(body: dict, db: Session = Depends(get_db)):
        if not body.get("name") or db.query(QualityProfile).filter(QualityProfile.name == body["name"]).first():
            raise HTTPException(400, "Name fehlt oder existiert bereits")
        p = QualityProfile(name=body["name"], items=[], cutoff="WEBDL-1080p", languages=[], format_scores={})
        _apply_profile(db, p, body)
        db.add(p)
        db.flush()
        return next(x for x in _profiles(db) if x["id"] == p.id)

    @router.put("/qualityprofile/{pid}", status_code=202)
    def update_quality_profile(pid: int, body: dict, db: Session = Depends(get_db)):
        p = db.get(QualityProfile, pid)
        if not p:
            raise HTTPException(404, "not found")
        _apply_profile(db, p, body)
        db.flush()
        return next(x for x in _profiles(db) if x["id"] == p.id)

    @router.get("/config/naming")
    def get_naming(db: Session = Depends(get_db)):
        return naming(db, flavor)

    @router.put("/config/naming", status_code=202)
    @router.put("/config/naming/{_id}", status_code=202)
    def put_naming(body: dict, db: Session = Depends(get_db), _id: int = 1):
        return save_naming(db, flavor, body)

    @router.get("/config/mediamanagement")
    def get_media_management(db: Session = Depends(get_db)):
        return media_management(db)

    @router.put("/config/mediamanagement", status_code=202)
    @router.put("/config/mediamanagement/{_id}", status_code=202)
    def put_media_management(body: dict, db: Session = Depends(get_db), _id: int = 1):
        return save_media_management(db, body)

    @router.get("/language")
    def languages():
        return [{"id": i, "name": n.capitalize(), "nameLower": n} for n, i in sorted(LANG_IDS.items(), key=lambda x: x[1])]

    @router.get("/history")
    def history(request: Request, db: Session = Depends(get_db)):
        return history_records(db, flavor, request)
