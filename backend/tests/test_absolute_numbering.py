"""Long runners like One Piece: season order in the library, releases with absolute numbers only."""
import pytest

from app.core import decision as dec
from app.core.parser import find_absolute, normalize_title, parse
from app.db import session_scope
from app.indexers.newznab import Release
from app.models import Episode, QualityProfile, Season, Series
from app.services import library

GiB = 1024 ** 3


def _release(title):
    return Release(guid=f"g-{title}", title=title, indexer_id=0, indexer="Test", protocol="usenet",
                   download_url="http://x", size=GiB, age_hours=10.0)


def _series(db, root, series_type):
    pid = db.query(QualityProfile).filter(QualityProfile.name == "HD-1080p").first().id
    se = Series(title="One Piece", year=1999, quality_profile_id=pid, root_folder=str(root), path=str(root / "One Piece"),
                series_type=series_type, runtime=24)
    se.seasons.append(Season(number=1, monitored=True))
    se.seasons.append(Season(number=21, monitored=True))
    se.episodes.append(Episode(season=1, number=1, absolute_number=1, title="Romance Dawn", monitored=True,
                               air_date_utc=library._dt("1999-10-20T20:00:00")))
    for n, absolute in ((1, 1015), (2, 1016), (3, 1017)):
        se.episodes.append(Episode(season=21, number=n, absolute_number=absolute, title=f"Folge {absolute}",
                                   monitored=True, air_date_utc=library._dt(f"2022-04-0{n}T20:00:00")))
    db.add(se)
    db.flush()
    return se


@pytest.mark.parametrize("name,nums", [
    ("One.Piece.1017.German.1080p.WEB.x264-GRP", [1017]),
    ("One.Piece.E1017.German.DL.1080p.WEB.h264-GRP", [1017]),
    ("One Piece Folge 1017 German 1080p WEB h264-GRP", [1017]),
    ("One.Piece.1017.Ein.Feuerwerk.der.maechtigen.Techniken.German.720p.WEB.h264-GRP", [1017]),
    ("One.Piece.1015-1017.German.1080p.WEB.h264-GRP", [1015, 1016, 1017]),
])
def test_find_absolute_after_known_title(name, nums):
    assert parse(name).is_tv is False  # without context this reads like a movie
    hit = find_absolute(name, {normalize_title("One Piece")})
    assert hit and hit[0] == "onepiece" and hit[1] == nums


def test_find_absolute_needs_the_title_and_two_digits():
    assert find_absolute("Apollo.13.German.1080p.BluRay.x264-GRP", {normalize_title("One Piece")}) is None
    assert find_absolute("Zoomania.2.German.1080p.WEB.h264-GRP", {normalize_title("Zoomania")}) is None


@pytest.mark.parametrize("series_type", ["standard", "anime"])
@pytest.mark.parametrize("title", [
    "One.Piece.1017.German.1080p.WEB.x264-GRP",
    "One.Piece.E1017.German.DL.1080p.WEB.h264-GRP",
    "One.Piece.S21E1017.German.1080p.WEB.h264-GRP",
    "One.Piece.S01E1017.German.1080p.WEB.h264-GRP",
])
def test_absolute_release_maps_to_season_episode(tmp_root, series_type, title):
    with session_scope() as db:
        se = _series(db, tmp_root / "abs", series_type)
        d = dec.evaluate_episodes(dec.Context(db), se, _release(title))
        ep = next(e for e in se.episodes if e.absolute_number == 1017)
        assert d.episode_ids == [ep.id]
        assert d.parsed.is_tv and d.parsed.title == "One Piece" and "german" in d.parsed.languages
        assert not any("passt nicht" in r or "Keine passenden" in r or "Keine Episoden" in r for r in d.rejections)
        db.rollback()


def test_standard_series_does_not_guess_absolute_for_small_numbers(tmp_root):
    with session_scope() as db:
        se = _series(db, tmp_root / "abs2", "standard")
        se.episodes.append(Episode(season=1, number=2, absolute_number=2, title="Früh", monitored=True,
                                   air_date_utc=library._dt("1999-10-27T20:00:00")))
        db.flush()
        # S21E02 is a regular episode, never absolute 2
        p = parse("One.Piece.S21E02.German.1080p.WEB.h264-GRP")
        assert [(e.season, e.number) for e in dec.map_episodes(se, p)] == [(21, 2)]
        # season 22 isn't in the library yet: must not fall back to absolute numbers
        assert dec.map_episodes(se, parse("One.Piece.S22E02.German.1080p.WEB.h264-GRP")) == []
        db.rollback()


def test_rss_sync_finds_series_for_absolute_release(tmp_root, monkeypatch):
    from app.models import Indexer
    from app.services import rss

    with session_scope() as db:
        se = _series(db, tmp_root / "abs-rss", "standard")
        idx = Indexer(name="RSS-Abs", url="http://127.0.0.1:1", movie_categories=[2000], tv_categories=[5000])
        db.add(idx)
        db.flush()
        sid, iid = se.id, idx.id
        ep_id = next(e.id for e in se.episodes if e.absolute_number == 1016)
    r = _release("One.Piece.1016.German.1080p.WEB.h264-GRP")
    r.indexer_id, r.indexer = iid, "RSS-Abs"
    monkeypatch.setattr(rss.newznab, "search", lambda s, idx, params, kind="query", manual=False: [r] if idx.id == iid else [])
    grabbed = []
    monkeypatch.setattr(rss, "grab_decision", lambda db, d, manual=False: grabbed.append((d.series_id, d.episode_ids)))
    with session_scope() as db:
        rss.rss_sync(db)
        assert (sid, [ep_id]) in grabbed
        db.query(Indexer).filter(Indexer.id == iid).delete()
        db.delete(db.get(Series, sid))
