"""Recycle bin with restore, and editable quality size definitions."""
import os
import time


def test_recycle_remove_restore_and_empty(tmp_root):
    from app.services import recycle

    rb = tmp_root / "recycle"
    cfg = {"recycle_bin": str(rb)}
    show = tmp_root / "lib" / "Show (2020)" / "Season 01"
    show.mkdir(parents=True)
    f = show / "Show - S01E01.mkv"
    f.write_bytes(b"x" * 10)
    old = time.time() - 30 * 86400
    os.utime(f, (old, old))

    recycle.remove(str(f), cfg)
    assert not f.exists()
    entries = recycle.entries(cfg)
    assert len(entries) == 1 and entries[0]["original"] == os.path.normpath(str(f))
    assert recycle.empty(cfg, older_than_days=7) == 0  # deletion just happened, old mtime doesn't count

    assert recycle.restore(entries[0]["path"], cfg) == os.path.normpath(str(f))
    assert f.exists() and recycle.entries(cfg) == []

    recycle.remove(str(tmp_root / "lib" / "Show (2020)"), cfg)  # whole folder
    assert recycle.entries(cfg)[0]["folder"] is True
    assert recycle.empty(cfg) >= 1
    assert recycle.entries(cfg) == []


def test_recycle_without_bin_deletes(tmp_root):
    from app.services import recycle

    f = tmp_root / "gone.mkv"
    f.write_bytes(b"x")
    recycle.remove(str(f), {"recycle_bin": ""})
    assert not f.exists()


def test_quality_definitions_api():
    from fastapi.testclient import TestClient

    from app import config
    from app.main import app

    c = TestClient(app, headers={"X-Api-Key": config.API_KEY})
    defs = c.get("/api/v1/qualitydefinitions").json()
    hd = next(d for d in defs if d["name"] == "WEBDL-1080p")
    hd["min"], hd["max"] = 7, 90
    res = c.put("/api/v1/qualitydefinitions", json=defs).json()
    assert next(d for d in res if d["name"] == "WEBDL-1080p")["custom"] is True
    assert c.get("/api/v1/settings").json()["media"]["quality_sizes"] == {"WEBDL-1080p": {"min": 7.0, "max": 90.0}}
    hd["min"], hd["max"] = hd["default_min"], hd["default_max"]
    c.put("/api/v1/qualitydefinitions", json=defs)
    assert c.get("/api/v1/settings").json()["media"]["quality_sizes"] == {}
    bad = [dict(hd, min=50, max=10)]
    assert c.put("/api/v1/qualitydefinitions", json=bad).status_code == 400
