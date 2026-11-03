"""Delay profiles, tag based client choice and the mass editor."""
from datetime import timedelta

from app.core import decision as dec
from app.core.parser import parse
from app.db import session_scope
from app.indexers.newznab import Release
from app.models import DelayProfile, DownloadClient, Indexer, Movie, PendingRelease, QualityProfile, utcnow
from app.services import delay, library


def _movie(db, tmp_root, anilist_id, title, tags=None):
    pid = db.query(QualityProfile).filter(QualityProfile.name == "Any").first().id
    m = library.add_movie(db, {"anilist": anilist_id}, pid, str(tmp_root / "delay"),
                          meta={"provider": "anilist", "ids": {"anilist": anilist_id}, "title": title, "year": 2001},
                          tags=tags or [])
    m.minimum_availability = "announced"
    db.flush()
    return m


def _decision(db, m, title, protocol="usenet", age_hours=0.1):
    idx = db.query(Indexer).first()
    if idx is None:
        idx = Indexer(name="Delay-Test", url="http://127.0.0.1:1", movie_categories=[2000], tv_categories=[5000])
        db.add(idx)
        db.flush()
    r = Release(guid=f"guid-{title}", title=title, indexer_id=idx.id, indexer=idx.name, protocol=protocol,
                download_url="http://x/nzb", size=8 * 1024 ** 3, age_hours=age_hours,
                publish_date=(utcnow() - timedelta(hours=age_hours)).isoformat() + "Z")
    return dec.evaluate_movie(dec.Context(db), m, r, parse(title))


def test_delay_holds_then_grabs_best(tmp_root, monkeypatch):
    with session_scope() as db:
        default = db.query(DelayProfile).filter(DelayProfile.tags == []).first() or \
            next(p for p in db.query(DelayProfile).all() if not p.tags)
        default.usenet_delay = 60
        default.bypass_highest_quality = False
        m = _movie(db, tmp_root, 990300, "Delayfilm")
        qp = db.get(QualityProfile, m.quality_profile_id)
        d = _decision(db, m, "Delayfilm.2001.720p.HDTV.x264-GRP")
        assert d.approved, d.rejections
        profile = delay.profile_for(db, m.tags)
        assert delay.hold(db, d, profile, qp)
        assert db.query(PendingRelease).filter(PendingRelease.movie_id == m.id).count() == 1

        better = _decision(db, m, "Delayfilm.2001.German.DL.1080p.BluRay.x264-GRP")
        assert delay.hold(db, better, profile, qp)  # still inside the delay
        assert db.query(PendingRelease).filter(PendingRelease.movie_id == m.id).count() == 2

        old = _decision(db, m, "Delayfilm.2001.1080p.WEB-DL.x264-OLD", age_hours=5)
        assert not delay.hold(db, old, profile, qp)  # already older than the delay

        grabbed = []
        monkeypatch.setattr("app.services.grab.grab_decision", lambda db, d, manual=False: grabbed.append(d.release.title))
        assert delay.process_pending(db)["grabbed"] == 0  # nothing due yet
        for p in db.query(PendingRelease).filter(PendingRelease.movie_id == m.id).all():
            p.release_at = utcnow() - timedelta(minutes=1)
        res = delay.process_pending(db)
        assert grabbed == ["Delayfilm.2001.German.DL.1080p.BluRay.x264-GRP"]
        assert res["processed"] == 2
        assert db.query(PendingRelease).filter(PendingRelease.movie_id == m.id).count() == 0
        default.usenet_delay = 0
        db.rollback()


def test_delay_bypass_and_preferred_protocol(tmp_root):
    with session_scope() as db:
        m = _movie(db, tmp_root, 990301, "Bypassfilm")
        qp = db.get(QualityProfile, m.quality_profile_id)
        profile = DelayProfile(usenet_delay=60, torrent_delay=60, bypass_highest_quality=False, bypass_min_score=100,
                               preferred_protocol="torrent", tags=[])
        d = _decision(db, m, "Bypassfilm.2001.German.DL.1080p.BluRay.x264-GRP")
        assert d.format_score >= 100
        assert not delay.hold(db, d, profile, qp)  # score bypass
        u = _decision(db, m, "Bypassfilm.2001.1080p.BluRay.x264-GRP", protocol="usenet")
        t = _decision(db, m, "Bypassfilm.2001.1080p.BluRay.x264-GRP", protocol="torrent")
        assert delay.prefer([u, t], profile)[0] is t
        db.rollback()


def test_pick_client_respects_tags():
    from app.downloadclients.manager import pick_client

    with session_scope() as db:
        plain = DownloadClient(name="plain", kind="sabnzbd", priority=1, tags=[])
        anime = DownloadClient(name="anime", kind="sabnzbd", priority=5, tags=[42])
        db.add_all([plain, anime])
        db.flush()
        assert pick_client(db, "usenet", tags=[42]).name == "anime"
        assert pick_client(db, "usenet", tags=[]).name == "plain"
        assert pick_client(db, "usenet", tags=[7]).name == "plain"
        db.rollback()


def test_bulk_editor_tags_and_move(tmp_root):
    from fastapi.testclient import TestClient

    from app import config
    from app.main import app

    c = TestClient(app, headers={"X-Api-Key": config.API_KEY})
    with session_scope() as db:
        m = _movie(db, tmp_root, 990302, "Bulkfilm", tags=[1])
        (tmp_root / "delay" / "Bulkfilm (2001)").mkdir(parents=True, exist_ok=True)
        m.path = str(tmp_root / "delay" / "Bulkfilm (2001)")
        (tmp_root / "delay" / "Bulkfilm (2001)" / "film.mkv").write_bytes(b"x")
        mid = m.id
    r = c.put("/api/v1/movies", json={"ids": [mid], "changes": {"tags": [2], "monitored": False}, "tags_mode": "add"})
    assert r.json()["updated"] == 1
    new_root = tmp_root / "other-root"
    new_root.mkdir(exist_ok=True)
    r = c.put("/api/v1/movies", json={"ids": [mid], "changes": {"root_folder": str(new_root)}, "move_files": True})
    assert r.json()["errors"] == []
    with session_scope() as db:
        m = db.get(Movie, mid)
        assert m.tags == [1, 2] and m.monitored is False
        assert m.root_folder == str(new_root)
        assert (new_root / "Bulkfilm (2001)" / "film.mkv").exists()
    assert c.post("/api/v1/movies/delete", json={"ids": [mid], "delete_files": True}).json()["deleted"] == 1
    assert not (new_root / "Bulkfilm (2001)").exists()
