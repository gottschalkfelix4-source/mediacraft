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
