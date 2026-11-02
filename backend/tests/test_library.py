"""Library: duplicate detection must also work for titles that only carry an AniList ID."""
import pytest

from app.db import session_scope
from app.models import MediaFile, Movie, QualityProfile
from app.services import library


def test_anilist_only_movie_is_not_added_twice(tmp_root):
    meta = {"provider": "anilist", "ids": {"anilist": 990199}, "title": "Testfilm AniList", "year": 2001}
    with session_scope() as db:
        pid = db.query(QualityProfile).first().id
        m = library.add_movie(db, {"anilist": 990199}, pid, str(tmp_root), meta=dict(meta))
        assert m.anilist_id == 990199
        with pytest.raises(library.LibraryError):
            library.add_movie(db, {"anilist": 990199}, pid, str(tmp_root), meta=dict(meta))
        assert db.query(Movie).filter(Movie.anilist_id == 990199).count() == 1
        db.rollback()


def test_disk_scan_sets_custom_format_score(tmp_root):
    from app.services import maintenance

    folder = tmp_root / "scan" / "Scanfilm (2001)"
    folder.mkdir(parents=True)
    (folder / "Scanfilm.2001.German.DL.1080p.BluRay.x264-GRP.mkv").write_bytes(b"\0" * 1024)
    meta = {"provider": "anilist", "ids": {"anilist": 990200}, "title": "Scanfilm", "year": 2001}
    with session_scope() as db:
        pid = db.query(QualityProfile).first().id
        m = library.add_movie(db, {"anilist": 990200}, pid, str(tmp_root / "scan"), meta=meta, path=str(folder))
        assert maintenance.scan_movie(db, m)["linked"] == 1
        assert db.get(MediaFile, m.file_id).format_score > 0  # German DL is scored in every seeded profile
        db.rollback()


class FakeMeta:
    """Stands in for MetadataManager: returns fixed data for the requested IDs."""

    def __init__(self, movie=None, series=None):
        self.movie, self.series = movie, series

    def get_movie(self, ids, anime=False):
        return self.movie

    def get_series(self, ids, with_episodes=True, anime=False, preferred_source=""):
        return self.series


def _series_meta(tvmaze, title, episodes, **extra):
    return {"provider": "tvmaze", "ids": {"tvmaze": tvmaze}, "title": title, "year": 2010, "status": "ended",
            "episode_source": "tvmaze", "metadata_sources": ["tvmaze"], "seasons": [],
            "episodes": [{"season": s, "number": n, "title": f"{title} {s}x{n}"} for s, n in episodes], **extra}


def test_rematch_movie_replaces_ids_and_keeps_folder(tmp_root):
    with session_scope() as db:
        pid = db.query(QualityProfile).first().id
        wrong = {"provider": "tmdb", "ids": {"tmdb": 990301, "imdb": "tt0990301"}, "title": "Falscher Film",
                 "year": 1999, "runtime": 95}
        m = library.add_movie(db, wrong["ids"], pid, str(tmp_root), meta=dict(wrong), path=str(tmp_root / "Ordner"))
        right = {"provider": "anilist", "ids": {"anilist": 990302}, "title": "Richtiger Film"}
        library.rematch_movie(db, m, {"anilist": 990302}, mgr=FakeMeta(movie=right))
        assert (m.title, m.anilist_id, m.tmdb_id, m.imdb_id, m.year) == ("Richtiger Film", 990302, None, None, None)
        assert m.path == str(tmp_root / "Ordner")
        db.rollback()


def test_rematch_movie_rejects_title_already_in_library(tmp_root):
    with session_scope() as db:
        pid = db.query(QualityProfile).first().id
        a = library.add_movie(db, {"tmdb": 990311}, pid, str(tmp_root),
                              meta={"provider": "tmdb", "ids": {"tmdb": 990311}, "title": "A"})
        library.add_movie(db, {"tmdb": 990312}, pid, str(tmp_root),
                          meta={"provider": "tmdb", "ids": {"tmdb": 990312}, "title": "B"})
        with pytest.raises(library.LibraryError):
            library.rematch_movie(db, a, {"tmdb": 990312},
                                  mgr=FakeMeta(movie={"provider": "tmdb", "ids": {"tmdb": 990312}, "title": "B"}))
        # re-matching to its own entry is fine (e.g. to pull fresh data)
        library.rematch_movie(db, a, {"tmdb": 990311},
                              mgr=FakeMeta(movie={"provider": "tmdb", "ids": {"tmdb": 990311}, "title": "A"}))
        db.rollback()


def test_rematch_series_keeps_files_by_episode_number(tmp_root):
    from app.models import Series

    with session_scope() as db:
        pid = db.query(QualityProfile).first().id
        s = Series(quality_profile_id=pid, root_folder=str(tmp_root), title="?", path=str(tmp_root / "Serie"))
        library.apply_series_meta(db, s, _series_meta(990401, "Falsche Serie", [(1, 1), (1, 2), (2, 1), (3, 1)],
                                                      network="Falsch TV"), initial=True)
        db.add(s)
        db.flush()
        eps = {(e.season, e.number): e for e in s.episodes}
        for key in ((1, 1), (3, 1)):
            f = MediaFile(media_type="episode", series_id=s.id, path=str(tmp_root / f"x{key}.mkv"), size=1)
            db.add(f)
            db.flush()
            eps[key].file_id = f.id
        kept_file = eps[(1, 1)].file_id

        stats = library.rematch_series(db, s, {"tvmaze": 990402},
                                       mgr=FakeMeta(series=_series_meta(990402, "Richtige Serie", [(1, 1), (1, 2), (1, 3)])))
        db.flush()
        eps = {(e.season, e.number): e for e in s.episodes}
        assert (s.title, s.tvmaze_id, s.network) == ("Richtige Serie", 990402, None)
        assert sorted(eps) == [(1, 1), (1, 2), (1, 3)]
        assert eps[(1, 1)].file_id == kept_file and eps[(1, 1)].title == "Richtige Serie 1x1"
        assert sorted(se.number for se in s.seasons) == [1]
        assert stats["unlinked"] == 1
        assert db.query(MediaFile).filter(MediaFile.series_id == s.id).count() == 1
        db.rollback()
