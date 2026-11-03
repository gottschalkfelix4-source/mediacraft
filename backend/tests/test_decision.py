"""Decision engine and custom formats: what gets accepted, how releases are ranked, when to upgrade."""
from datetime import timedelta

from app.core import customformats, decision as dec
from app.core.parser import parse
from app.db import session_scope
from app.indexers.newznab import Release
from app.models import Blocklist, MediaFile, Movie, QualityProfile, utcnow
from app.services import library, rss

GiB = 1024 ** 3


def _release(title, size=8 * GiB, protocol="usenet", age=10.0, guid=None):
    return Release(guid=guid or f"g-{title}", title=title, indexer_id=0, indexer="Test", protocol=protocol,
                   download_url="http://x", size=size, age_hours=age)


def _movie(db, tmp_root, aid, title, **kw):
    pid = db.query(QualityProfile).filter(QualityProfile.name == kw.pop("profile", "HD-1080p")).first().id
    m = library.add_movie(db, {"anilist": aid}, pid, str(tmp_root / "dec"),
                          meta={"provider": "anilist", "ids": {"anilist": aid}, "title": title, "year": 2010, "runtime": 100})
    m.minimum_availability = "announced"
    for k, v in kw.items():
        setattr(m, k, v)
    db.flush()
    return m


def test_quality_size_title_and_ranking(tmp_root):
    with session_scope() as db:
        m = _movie(db, tmp_root, 993001, "Rangfilm")
        ctx = dec.Context(db)
        ok = dec.evaluate_movie(ctx, m, _release("Rangfilm.2010.German.DL.1080p.BluRay.x264-GRP"))
        web = dec.evaluate_movie(ctx, m, _release("Rangfilm.2010.1080p.WEB-DL.x264-GRP"))
        low = dec.evaluate_movie(ctx, m, _release("Rangfilm.2010.720p.HDTV.x264-GRP", size=2 * GiB))
        tiny = dec.evaluate_movie(ctx, m, _release("Rangfilm.2010.1080p.BluRay.x264-GRP", size=50 * 1024 ** 2))
        other = dec.evaluate_movie(ctx, m, _release("Ganz.Anderer.Film.2010.1080p.BluRay.x264-GRP"))
        assert ok.approved and web.approved
        assert not low.approved and any("nicht erlaubt" in r for r in low.rejections)
        assert not tiny.approved and any("Zu klein" in r for r in tiny.rejections)
        assert not other.approved and any("Titel passt nicht" in r for r in other.rejections)
        ranked = dec.rank([web, ok, low])
        assert ranked[0] is ok  # German DL scores higher in the seeded profiles
        db.rollback()


def test_language_require_blocklist_and_upgrade(tmp_root):
    with session_scope() as db:
        m = _movie(db, tmp_root, 993002, "Sprachfilm")
        profile = db.get(QualityProfile, m.quality_profile_id)
        profile.languages, profile.language_mode = ["german"], "require"
        db.add(Blocklist(media_type="movie", movie_id=m.id, source_title="Sprachfilm.2010.German.1080p.BluRay.x264-BAD",
                         guid="g-blocked"))
        db.flush()
        ctx = dec.Context(db)
        eng = dec.evaluate_movie(ctx, m, _release("Sprachfilm.2010.1080p.BluRay.x264-GRP"))
        ger = dec.evaluate_movie(ctx, m, _release("Sprachfilm.2010.German.1080p.BluRay.x264-GRP"))
        blocked = dec.evaluate_movie(ctx, m, _release("Sprachfilm.2010.German.1080p.BluRay.x264-BAD", guid="g-blocked"))
        assert not eng.approved and ger.approved
        assert not blocked.approved and "Blocklist" in " ".join(blocked.rejections)

        # existing WEB-DL file without German: a German BluRay is an upgrade, another English one isn't
        f = MediaFile(media_type="movie", movie_id=m.id, path="x.mkv", size=GiB, quality="WEBDL-1080p", languages=["german"],
                      format_score=50)
        db.add(f)
        db.flush()
        m.file_id = f.id
        db.flush()
        db.expire(m)
        ctx = dec.Context(db)
        up = dec.evaluate_movie(ctx, m, _release("Sprachfilm.2010.German.DL.1080p.BluRay.x264-GRP"))
        same = dec.evaluate_movie(ctx, m, _release("Sprachfilm.2010.German.1080p.WEB-DL.x264-GRP"))
        assert up.approved, up.rejections
        assert not same.approved
        profile.languages, profile.language_mode = [], "prefer"
        db.rollback()


def test_custom_format_conditions():
    fmt = {"id": 1, "name": "x265 4K HDR", "conditions": [
        {"type": "codec", "value": "x265", "required": True},
        {"type": "resolution", "value": "2160p", "required": True},
        {"type": "hdr", "value": "DV"}, {"type": "hdr", "value": "HDR10"},
        {"type": "title", "value": r"\bHDTV\b", "negate": True, "required": True}]}
    assert customformats.matches(fmt, parse("Film.2020.2160p.WEB-DL.DV.HEVC-GRP"))
    assert customformats.matches(fmt, parse("Film.2020.2160p.BluRay.HDR10.x265-GRP"))
    assert not customformats.matches(fmt, parse("Film.2020.2160p.BluRay.x265-GRP"))  # no HDR variant
    assert not customformats.matches(fmt, parse("Film.2020.1080p.BluRay.HDR10.x265-GRP"))
    assert not customformats.matches(fmt, parse("Film.2020.2160p.HDTV.HDR10.x265-GRP"))
    size = {"id": 2, "name": "klein", "conditions": [{"type": "size", "value": "-2"}]}
    assert customformats.matches(size, parse("x"), size=GiB)
    assert not customformats.matches(size, parse("x"), size=3 * GiB)
    score, names = customformats.evaluate([fmt, size], {"1": 50, "2": -10}, parse("Film.2020.2160p.WEB-DL.DV.HEVC-GRP"),
                                          size=GiB)
    assert (score, names) == (40, ["x265 4K HDR", "klein"])


def test_rss_sync_grabs_best_release_per_movie(tmp_root, monkeypatch):
    from app.models import Indexer

    with session_scope() as db:
        m = _movie(db, tmp_root, 993003, "RSSfilm")
        idx = Indexer(name="RSS-Test", url="http://127.0.0.1:1", movie_categories=[2000], tv_categories=[5000])
        db.add(idx)
        db.flush()
        mid, iid = m.id, idx.id
    releases = [_release(t) for t in ("RSSfilm.2010.1080p.WEB-DL.x264-A", "RSSfilm.2010.German.DL.1080p.BluRay.x264-B",
                                       "Unbekannt.2010.1080p.BluRay.x264-C")]
    for r in releases:
        r.indexer_id, r.indexer = iid, "RSS-Test"
    monkeypatch.setattr(rss.newznab, "search", lambda s, idx, params, kind="query", manual=False: releases if idx.id == iid else [])
    grabbed = []
    monkeypatch.setattr(rss, "grab_decision", lambda db, d, manual=False: grabbed.append((d.movie_id, d.release.title)))
    with session_scope() as db:
        stats = rss.rss_sync(db)
        assert (mid, "RSSfilm.2010.German.DL.1080p.BluRay.x264-B") in grabbed
        assert stats["grabbed"] >= 1
        db.query(Indexer).filter(Indexer.id == iid).delete()
        db.query(Movie).filter(Movie.id == mid).delete()


def test_movie_availability():
    m = Movie(minimum_availability="released", status="announced", in_cinemas=utcnow() - timedelta(days=10))
    assert not dec.movie_available(m)
    m.digital_release = utcnow() - timedelta(days=1)
    assert dec.movie_available(m)
    m2 = Movie(minimum_availability="in_cinemas", status="announced", in_cinemas=utcnow() - timedelta(days=1))
    assert dec.movie_available(m2)
