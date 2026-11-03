"""Recyclarr- and Bazarr-style use of the Sonarr/Radarr compat API."""
from fastapi.testclient import TestClient

from app import config
from app.main import app

H = {"X-Api-Key": config.API_KEY}


def test_recyclarr_custom_format_and_profile_roundtrip():
    c = TestClient(app, headers=H)
    cf = {"name": "TRaSH Test DV", "includeCustomFormatWhenRenaming": False, "specifications": [
        {"name": "DV", "implementation": "ReleaseTitleSpecification", "negate": False, "required": True,
         "fields": [{"name": "value", "value": r"\b(dv|dovi|dolby[ .]?vision)\b"}]},
        {"name": "1080p", "implementation": "ResolutionSpecification", "negate": False, "required": False,
         "fields": {"value": 1080}},
        {"name": "Not Remux", "implementation": "QualityModifierSpecification", "negate": True, "required": True,
         "fields": [{"name": "value", "value": 5}]},
        {"name": "Season pack", "implementation": "ReleaseTypeSpecification", "negate": False, "required": False,
         "fields": [{"name": "value", "value": 3}]}]}
    created = c.post("/radarr/api/v3/customformat", json=cf)
    assert created.status_code == 201, created.text
    fid = created.json()["id"]
    specs = c.get(f"/radarr/api/v3/customformat/{fid}").json()["specifications"]
    assert [s["implementation"] for s in specs] == [s["implementation"] for s in cf["specifications"]]
    assert c.post("/radarr/api/v3/customformat", json=cf).status_code == 400  # duplicate name

    profiles = c.get("/radarr/api/v3/qualityprofile").json()
    p = profiles[0]
    assert any(fi["format"] == fid for fi in p["formatItems"])
    for fi in p["formatItems"]:
        if fi["format"] == fid:
            fi["score"] = 1500
    original_min = p["minFormatScore"]
    p["minFormatScore"] = 10
    r = c.put(f"/radarr/api/v3/qualityprofile/{p['id']}", json=p)
    assert r.status_code == 202, r.text
    again = next(x for x in c.get("/radarr/api/v3/qualityprofile").json() if x["id"] == p["id"])
    assert next(fi["score"] for fi in again["formatItems"] if fi["format"] == fid) == 1500
    assert again["minFormatScore"] == 10
    assert [i["allowed"] for i in again["items"]] == [i["allowed"] for i in p["items"]]  # qualities unchanged

    from app.core.customformats import matches
    from app.core.parser import parse
    from app.db import session_scope
    from app.models import CustomFormat

    with session_scope() as db:
        fmt = db.get(CustomFormat, fid).to_dict()
    assert matches(fmt, parse("Film.2020.German.DL.1080p.WEB-DL.DV.x265-GRP"))
    assert not matches(fmt, parse("Film.2020.German.DL.1080p.BluRay.REMUX.DV.x265-GRP"))
    assert c.delete(f"/radarr/api/v3/customformat/{fid}").status_code == 200
    c.put(f"/radarr/api/v3/qualityprofile/{p['id']}", json={"minFormatScore": original_min})


def test_recyclarr_quality_definitions_and_naming():
    c = TestClient(app, headers=H)
    defs = c.get("/sonarr/api/v3/qualitydefinition").json()
    remux = next(d for d in defs if d["title"] == "Bluray-1080p Remux")  # Sonarr naming
    remux["minSize"], remux["maxSize"] = 20, 300
    c.put("/sonarr/api/v3/qualitydefinition/update", json=[remux])
    sizes = c.get("/api/v1/settings", headers=H).json()["media"]["quality_sizes"]
    assert sizes["Remux-1080p"] == {"min": 20.0, "max": 300.0}

    naming = c.get("/sonarr/api/v3/config/naming").json()
    naming["seasonFolderFormat"] = "Staffel {season:00}"
    assert c.put("/sonarr/api/v3/config/naming", json=naming).json()["seasonFolderFormat"] == "Staffel {season:00}"
    mm = c.get("/radarr/api/v3/config/mediamanagement").json()
    mm["downloadPropersAndRepacks"] = "doNotUpgrade"
    assert c.put("/radarr/api/v3/config/mediamanagement", json=mm).json()["downloadPropersAndRepacks"] == "doNotUpgrade"
    mm["downloadPropersAndRepacks"] = "preferAndUpgrade"
    c.put("/radarr/api/v3/config/mediamanagement", json=mm)
    naming["seasonFolderFormat"] = "Season {season:00}"
    c.put("/sonarr/api/v3/config/naming", json=naming)
    remux["minSize"], remux["maxSize"] = 15, None
    c.put("/sonarr/api/v3/qualitydefinition/update", json=[remux])
    assert "Remux-1080p" not in c.get("/api/v1/settings", headers=H).json()["media"]["quality_sizes"]


def test_bazarr_episode_files(tmp_root):
    from app.db import session_scope
    from app.models import Episode, MediaFile, QualityProfile, Season, Series

    with session_scope() as db:
        pid = db.query(QualityProfile).first().id
        s = Series(title="Bazarrshow", root_folder=str(tmp_root), path=str(tmp_root / "Bazarrshow"), quality_profile_id=pid)
        s.seasons.append(Season(number=1))
        db.add(s)
        db.flush()
        f = MediaFile(media_type="episode", series_id=s.id, path=str(tmp_root / "Bazarrshow" / "S01E01.mkv"), size=10,
                      quality="WEBDL-1080p", languages=["german", "english"], release_name="Bazarrshow.S01E01.German.DL",
                      media_info={"probe": {"audio_tracks": [{"codec": "EAC3", "channels": 6, "language": "ger"}],
                                            "width": 1920, "height": 1080, "subtitle_languages": ["ger"]}})
        db.add(f)
        db.flush()
        e = Episode(series_id=s.id, season=1, number=1, title="Pilot", file_id=f.id)
        db.add(e)
        db.flush()
        sid, fid = s.id, f.id
    from app.services.commands import register_all

    register_all()
    c = TestClient(app, headers=H)
    eps = c.get(f"/sonarr/api/v3/episode?seriesId={sid}&includeEpisodeFile=true").json()
    assert eps[0]["episodeFileId"] == fid and eps[0]["episodeFile"]["sceneName"] == "Bazarrshow.S01E01.German.DL"
    ef = c.get(f"/sonarr/api/v3/episodefile/{fid}").json()
    assert ef["seasonNumber"] == 1 and ef["mediaInfo"]["audioLanguages"] == "ger"
    assert ef["mediaInfo"]["resolution"] == "1920x1080"
    assert [l["name"] for l in ef["languages"]] == ["German", "English"]
    r = c.post("/sonarr/api/v3/command", json={"name": "RescanSeries", "seriesId": sid})
    assert r.status_code == 201 and r.json()["name"] == "RescanSeries"
    hist = c.get("/sonarr/api/v3/history?page=1&pageSize=5").json()
    assert "records" in hist
