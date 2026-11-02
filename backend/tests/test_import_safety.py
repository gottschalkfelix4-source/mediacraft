"""Imports must not run twice at once, and an error mid season pack must not lose files already moved."""
from app.db import session_scope
from app.models import Episode, MediaFile, QualityProfile, QueueItem, Season, Series
from app.services import importer, library, queue


def _series(s, root, title):
    pid = s.query(QualityProfile).first().id
    se = Series(title=title, year=2020, quality_profile_id=pid, root_folder=str(root), path=str(root / title))
    se.seasons.append(Season(number=1, monitored=True))
    for n in (1, 2, 3):
        se.episodes.append(Episode(season=1, number=n, title=f"Folge {n}", monitored=True,
                                   air_date_utc=library._dt(f"2020-01-0{n}T20:00:00")))
    s.add(se)
    s.flush()
    return se


def test_running_import_is_not_started_twice(tmp_root):
    with session_scope() as s:
        se = _series(s, tmp_root / "safety", "Doppelshow")
        q = QueueItem(download_client_id=1, download_id="x1", protocol="usenet", title="Doppelshow.S01-GRP",
                      media_type="series", series_id=se.id, status="importing")
        s.add(q)
        s.flush()
        queue._importing.add(q.id)
        try:
            assert queue.import_running(q.id)
            assert queue._import(s, q, None) is False  # second caller backs off without touching the item
            assert q.status == "importing" and not q.messages
            # a different download has to wait too: only one import at a time overall
            other = QueueItem(download_client_id=1, download_id="x9", protocol="usenet", title="Andere.Show.S01-GRP",
                              media_type="series", series_id=se.id, status="downloading")
            s.add(other)
            s.flush()
            assert queue._import(s, other, None) is False and other.status == "downloading"
        finally:
            queue._importing.discard(q.id)
        s.rollback()


def test_error_mid_season_pack_keeps_files_already_imported(tmp_root, monkeypatch):
    dl = tmp_root / "safety-dl" / "Packshow.S01.1080p.WEB-DL-GRP"
    dl.mkdir(parents=True)
    for n in (1, 2, 3):
        (dl / f"Packshow.S01E0{n}.1080p.WEB-DL-GRP.mkv").write_bytes(b"\0" * 2048)
    with session_scope() as s:
        se = _series(s, tmp_root / "safety", "Packshow")
        q = QueueItem(download_client_id=1, download_id="x2", protocol="usenet", title="Packshow.S01.1080p.WEB-DL-GRP",
                      media_type="series", series_id=se.id, episode_ids=[e.id for e in se.episodes])
        s.add(q)
        s.commit()
        sid = se.id
        real, calls = importer.transfer, []

        def flaky(src, dest, mode, use_hardlinks=True):
            calls.append(src)
            if "S01E02" in src:
                raise OSError("Netzlaufwerk weg")
            return real(src, dest, mode, use_hardlinks)

        monkeypatch.setattr(importer, "transfer", flaky)
        ok, messages = importer.process_download(s, q, str(dl), "move")
        assert not ok and any("Netzlaufwerk weg" in m for m in messages)
        s.rollback()  # whatever the caller does afterwards: E01 and E03 are already committed
    with session_scope() as s:
        have = sorted(e.number for e in s.get(Series, sid).episodes if e.file_id)
        assert have == [1, 3]
        assert s.query(MediaFile).filter(MediaFile.series_id == sid).count() == 2


def test_empty_download_counts_as_imported_when_all_episodes_have_files(tmp_root):
    empty = tmp_root / "safety-dl" / "Leershow.S01-GRP"
    (empty / "Leershow.S01E01-GRP").mkdir(parents=True)
    (empty / "Leershow.S01E01-GRP" / "House-of-Usenet.com.url").write_text("x")
    with session_scope() as s:
        se = _series(s, tmp_root / "safety", "Leershow")
        q = QueueItem(download_client_id=1, download_id="x3", protocol="usenet", title="Leershow.S01-GRP",
                      media_type="series", series_id=se.id, episode_ids=[e.id for e in se.episodes])
        s.add(q)
        s.flush()
        assert importer.process_download(s, q, str(empty), "move")[0] is False  # nothing there, nothing linked
        for e in se.episodes:
            f = MediaFile(media_type="episode", series_id=se.id, path=str(tmp_root / f"l{e.number}.mkv"), size=1)
            s.add(f)
            s.flush()
            e.file_id = f.id
        ok, messages = importer.process_download(s, q, str(empty), "move")
        assert ok and "Bereits importiert" in messages[0]
        s.rollback()


def test_completed_without_output_path_waits_instead_of_blocking(monkeypatch):
    from app.downloadclients.base import ClientItem
    from app.models import DownloadClient

    with session_scope() as s:
        c = DownloadClient(name="SAB-Test", kind="sabnzbd", tv_category="tv", movie_category="movies")
        s.add(c)
        s.flush()
        q = QueueItem(download_client_id=c.id, download_id="nzo_wait", protocol="usenet", title="Warteshow.S01E01-GRP",
                      media_type="series", status="downloading")
        s.add(q)
        s.flush()

        class Fake:
            def items(self, cats):
                return [ClientItem(download_id="nzo_wait", title=q.title, category="tv", status="completed",
                                   size=10, size_left=0, progress=100.0, output_path=None)]

        monkeypatch.setattr(queue, "get_client", lambda cfg: Fake())
        monkeypatch.setattr(queue, "_import", lambda *a: (_ for _ in ()).throw(AssertionError("must not import")))
        queue.check_downloads(s)
        assert q.status == "downloading" and not q.messages
        s.rollback()
