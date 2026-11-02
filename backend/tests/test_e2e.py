"""End-to-end: fake newznab indexer -> decision -> grab (blackhole) -> completed download -> import."""
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app.core import decision as dec
from app.db import session_scope
from app.models import DownloadClient, Episode, Indexer, Movie, QueueItem, RootFolder, Season, Series
from app.services import library, queue, search

GiB = 1024 ** 3

ITEMS = {
    "movie": [
        ("Inception.2010.German.DL.1080p.BluRay.x264-GROUP", 9 * GiB),
        ("Inception.2010.720p.HDTV.x264-OTHER", 3 * GiB),
        ("Inception.2010.TS.x264-CAM", 1 * GiB),
        ("Totally.Different.Movie.2010.1080p.BluRay.x264-GRP", 8 * GiB),
    ],
    "tv": [
        ("Testshow.S01.German.DL.1080p.WEB.h264-PACK", 12 * GiB),
        ("Testshow.S01E02.German.DL.1080p.WEB.h264-SINGLE", 2 * GiB),
    ],
}


def _feed(items, limits=True):
    rows = "".join(
        f"""<item><title>{t}</title><guid>guid-{t}</guid><link>http://127.0.0.1:{{port}}/getnzb?id={t}</link>
        <pubDate>Mon, 02 Nov 2026 10:00:00 +0000</pubDate><enclosure url="http://127.0.0.1:{{port}}/getnzb?id={t}" length="{s}" type="application/x-nzb"/>
        <newznab:attr name="size" value="{s}"/><newznab:attr name="category" value="2040"/></item>"""
        for t, s in items)
    lim = '<newznab:apilimits apicurrent="5" apimax="1000" grabcurrent="1" grabmax="400"/>' if limits else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">
    <channel>{lim}{rows}</channel></rss>"""


CAPS = """<?xml version="1.0"?><caps><limits max="100" default="100"/>
<searching><search available="yes" supportedParams="q"/><tv-search available="yes" supportedParams="q,season,ep"/>
<movie-search available="yes" supportedParams="q,imdbid"/></searching>
<categories><category id="2000" name="Movies"><subcat id="2040" name="HD"/></category><category id="5000" name="TV"/></categories></caps>"""


class Handler(BaseHTTPRequestHandler):
    calls: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        Handler.calls.append((u.path, q))
        port = self.server.server_address[1]
        if u.path == "/getnzb":
            body = b'<?xml version="1.0"?><nzb xmlns="http://www.newzbin.com/DTD/2003/nzb"><file subject="x"/></nzb>'
            self.send_response(200)
            self.send_header("Content-Type", "application/x-nzb")
        elif q.get("t") == "caps":
            body = CAPS.encode()
            self.send_response(200)
        else:
            items = ITEMS["tv"] if q.get("t") == "tvsearch" or "Testshow" in q.get("q", "") else ITEMS["movie"]
            body = _feed(items).replace("{port}", str(port)).encode()
            self.send_response(200)
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def indexer_server():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


@pytest.fixture(scope="module")
def setup(indexer_server, tmp_root: Path):
    media = tmp_root / "media"
    watch, done = tmp_root / "watch", tmp_root / "done"
    for p in (media / "movies", media / "tv", watch, done):
        p.mkdir(parents=True, exist_ok=True)
    with session_scope() as s:
        s.add(RootFolder(path=str(media / "movies"), media_type="movie"))
        s.add(RootFolder(path=str(media / "tv"), media_type="series"))
        idx = Indexer(name="FakeTM", url=f"http://127.0.0.1:{indexer_server}", api_key="k", kind="newznab",
                      movie_categories=[2000], tv_categories=[5000], grab_limit=2, limit_window_hours=24,
                      sync_remote_limits=False)
        s.add(idx)
        s.add(DownloadClient(name="Blackhole", kind="blackhole_usenet", movie_category="movies", tv_category="tv",
                             settings={"watch_folder": str(watch), "completed_folder": str(done)}))
        s.flush()
        meta = {"provider": "test", "ids": {"tmdb": 27205, "imdb": "tt1375666"}, "title": "Inception",
                "year": 2010, "runtime": 148, "status": "released", "in_cinemas": "2010-07-15",
                "digital_release": "2010-12-07", "alt_titles": []}
        m = library.add_movie(s, {}, 2, str(media / "movies"), meta=meta)
        series = Series(title="Testshow", year=2020, quality_profile_id=2, root_folder=str(media / "tv"),
                        path=str(media / "tv" / "Testshow (2020)"), runtime=45, tvdb_id=999)
        series.seasons.append(Season(number=1, monitored=True))
        for n in (1, 2, 3):
            series.episodes.append(Episode(season=1, number=n, title=f"Folge {n}", air_date=f"2020-01-0{n}",
                                           air_date_utc=library._dt(f"2020-01-0{n}T20:00:00"), monitored=True))
        s.add(series)
        s.flush()
        return {"movie_id": m.id, "series_id": series.id, "watch": watch, "done": done, "media": media}


def test_movie_flow(setup):
    with session_scope() as s:
        movie = s.get(Movie, setup["movie_id"])
        res = search.search_movie(s, movie, manual=True)
        by_title = {d.release.title: d for d in res["decisions"]}
        best = res["decisions"][0]
        assert best.release.title.startswith("Inception.2010.German.DL.1080p")
        assert best.approved, best.rejections
        assert not by_title["Inception.2010.TS.x264-CAM"].approved
        assert not by_title["Totally.Different.Movie.2010.1080p.BluRay.x264-GRP"].approved
        assert "German DL" in best.formats

    with session_scope() as s:
        movie = s.get(Movie, setup["movie_id"])
        grabbed = search.auto_search_movie(s, movie)
        assert grabbed and grabbed["title"].startswith("Inception.2010.German.DL")
    assert any(p.suffix == ".nzb" for p in setup["watch"].iterdir())

    # simulate the download finishing
    title = grabbed["title"]
    out = setup["done"] / title
    out.mkdir()
    (out / f"{title}.mkv").write_bytes(b"x" * 4096)
    (out / "sample.mkv").write_bytes(b"x" * 10)
    (out / f"{title}.de.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHallo\n")

    with session_scope() as s:
        stats = queue.check_downloads(s)
        assert stats["imported"] == 1, stats
    with session_scope() as s:
        movie = s.get(Movie, setup["movie_id"])
        assert movie.has_file
        f = movie.file
        assert os.path.exists(f.path)
        assert f.quality == "Bluray-1080p" and "german" in f.languages
        assert os.path.basename(f.path) == "Inception (2010) [Bluray-1080p]-GROUP.mkv"
        assert os.path.exists(f.path[:-4] + ".de.srt")
        q = s.query(QueueItem).filter(QueueItem.movie_id == movie.id).one()
        assert q.status == "imported"

    # now at/above cutoff? HD-720p/1080p cutoff is Bluray-1080p and German DL >= cutoff score 100 -> no upgrade
    with session_scope() as s:
        movie = s.get(Movie, setup["movie_id"])
        res = search.search_movie(s, movie, manual=False)
        assert not any(d.approved for d in res["decisions"])


def test_series_season_pack_and_grab_limit(setup):
    with session_scope() as s:
        series = s.get(Series, setup["series_id"])
        eps = search.wanted_episodes(series)
        assert len(eps) == 3
        res = search.search_episodes(s, series, eps, manual=False)
        approved = [d for d in res["decisions"] if d.approved]
        assert approved and approved[0].parsed.full_season
        assert len(approved[0].episode_ids) == 3
        grabbed = search.auto_search_episodes(s, series, eps)
        assert len(grabbed) == 1  # the pack covers everything

    with session_scope() as s:
        idx = s.query(Indexer).filter(Indexer.name == "FakeTM").one()
        from app.indexers import usage
        st = usage.state(s, idx, "grab")
        assert st.used == 2 and st.remaining == 0  # movie + pack -> limit of 2 reached
        assert st.next_slot is not None

    # with the grab limit exhausted, further decisions are rejected temporarily
    with session_scope() as s:
        movie = s.get(Movie, setup["movie_id"])
        ctx = dec.Context(s)
        assert not ctx.grab_allowed(s.query(Indexer).filter(Indexer.name == "FakeTM").one().id)
