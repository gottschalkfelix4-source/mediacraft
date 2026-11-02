from datetime import timedelta

import pytest

from app.db import session_scope
from app.indexers import usage
from app.models import Indexer, IndexerEvent, utcnow


def _indexer(s, **kw):
    i = Indexer(name="TreasureMaps", url="http://tm.invalid", api_key="x", **kw)
    s.add(i)
    s.flush()
    return i


def _events(s, idx, kind, ages_hours):
    now = utcnow()
    for h in ages_hours:
        s.add(IndexerEvent(indexer_id=idx.id, kind=kind, timestamp=now - timedelta(hours=h)))
    s.flush()


def test_rolling_grab_limit_and_next_slot():
    with session_scope() as s:
        idx = _indexer(s, grab_limit=3, limit_window_hours=24, limit_mode="rolling")
        _events(s, idx, "grab", [23.5, 10, 1, 30])  # 30h old one is outside the window
        st = usage.state(s, idx, "grab")
        assert st.used == 3 and st.remaining == 0 and st.percent == 100.0
        # oldest in-window event (23.5h ago) frees its slot in ~30 minutes
        nxt = usage.next_slot(s, idx, "grab", 3)
        assert timedelta(minutes=25) < nxt - utcnow() < timedelta(minutes=35)
        with pytest.raises(usage.LimitReached):
            usage.check(s, idx, "grab")
        # queries are unlimited and unaffected
        usage.check(s, idx, "query")


def test_reserve_only_blocks_automatic_use():
    with session_scope() as s:
        idx = _indexer(s, grab_limit=5, grab_reserve=2)
        _events(s, idx, "grab", [1, 2, 3])
        with pytest.raises(usage.LimitReached):
            usage.check(s, idx, "grab", manual=False)
        usage.check(s, idx, "grab", manual=True)
        assert usage.state(s, idx, "grab").remaining_auto == 0


def test_failed_grabs_do_not_count_but_failed_queries_do():
    with session_scope() as s:
        idx = _indexer(s, grab_limit=2, query_limit=2)
        s.add(IndexerEvent(indexer_id=idx.id, kind="grab", success=False))
        s.add(IndexerEvent(indexer_id=idx.id, kind="query", success=False))
        s.add(IndexerEvent(indexer_id=idx.id, kind="rss"))
        s.flush()
        assert usage.count(s, idx, "grab") == 0
        assert usage.count(s, idx, "query") == 2


def test_fixed_window_resets_at_hour():
    with session_scope() as s:
        now = utcnow()
        idx = _indexer(s, query_limit=10, limit_mode="fixed", limit_reset_hour=now.hour, limit_window_hours=24)
        start, end = usage.window_bounds(idx, now)
        assert start <= now < end and end - start == timedelta(days=1)
        assert start.hour == now.hour


def test_remote_limits_are_merged():
    with session_scope() as s:
        idx = _indexer(s, grab_limit=400)
        usage.apply_remote_limits(idx, {"apiCurrent": "12", "apiMax": "1000", "grabCurrent": "399", "grabMax": "400",
                                        "grabOldestTime": "Mon, 02 Nov 2026 10:00:00 +0000"})
        st = usage.state(s, idx, "grab")
        assert st.used == 399 and st.remote_used == 399 and st.remaining == 1
        assert usage.effective_limit(idx, "query") == 1000


def test_forecast_rolling():
    with session_scope() as s:
        idx = _indexer(s, grab_limit=2)
        _events(s, idx, "grab", [23, 22])
        fc = usage.forecast(s, idx, "grab", steps=3)
        assert fc[0]["available"] == 0
        assert fc[-1]["available"] == 2


def test_remote_counter_plus_own_grabs_since_report():
    """TreasureMaps counts grabs from every tool on the account; ours after its report come on top."""
    with session_scope() as s:
        idx = _indexer(s, grab_limit=400, limit_window_hours=24, limit_mode="rolling")
        _events(s, idx, "grab", [5, 3])  # our own, already included in the indexer's number
        usage.apply_remote_limits(idx, {"grabCurrent": "395", "grabMax": "400",
                                        "grabNextAvailable": "Tue, 16 Jul 2030 20:56:54 +0000"})
        assert usage.state(s, idx, "grab").used == 395
        s.add(IndexerEvent(indexer_id=idx.id, kind="grab"))
        s.add(IndexerEvent(indexer_id=idx.id, kind="grab", success=False))  # failed: no grab consumed
        s.flush()
        st = usage.state(s, idx, "grab")
        assert st.used == 396 and st.remaining == 4
        assert idx.remote_limits["grab_next"] == "2030-07-16T20:56:54"


def test_remote_max_without_current_means_zero_used():
    with session_scope() as s:
        idx = _indexer(s, limit_window_hours=24)
        usage.apply_remote_limits(idx, {"apimax": "100", "grabmax": "5"})  # DrunkenSlug/TM style, nothing used yet
        st = usage.state(s, idx, "grab")
        assert (st.limit, st.used, st.remaining, st.remote_used) == (5, 0, 5, 0)


def test_remote_exhausted_without_times_still_gives_next_slot():
    with session_scope() as s:
        idx = _indexer(s, limit_window_hours=24, limit_mode="rolling")
        usage.apply_remote_limits(idx, {"grabCurrent": "400", "grabMax": "400"})
        with pytest.raises(usage.LimitReached) as e:
            usage.check(s, idx, "grab")
        assert e.value.until is not None and e.value.until > utcnow() + timedelta(hours=23)
        # forecast must not promise free grabs before the indexer's units can have expired
        fc = usage.forecast(s, idx, "grab")
        assert fc[0]["available"] == 0 and fc[23]["available"] == 0 and fc[24]["available"] == 400


def test_probe_marks_indexers_without_apilimits(monkeypatch):
    from app.indexers import newznab

    rss = b'<?xml version="1.0"?><rss xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/"><channel>%s</channel></rss>'
    with session_scope() as s:
        idx = _indexer(s, limit_window_hours=24)
        monkeypatch.setattr(newznab, "_request", lambda db, i, params, kind, manual: (rss % b"", 5))
        newznab.probe_limits(s, idx)
        assert idx.remote_limits["supported"] is False
        body = b'<newznab:apilimits apicurrent="7" apimax="1000" grabcurrent="12" grabmax="400" graboldesttime="Thu, 30 Apr 2020 19:54:30 +0200"/>'
        monkeypatch.setattr(newznab, "_request", lambda db, i, params, kind, manual: (rss % body, 5))
        rl = newznab.probe_limits(s, idx)
        assert (rl["supported"], rl["grab_current"], rl["grab_max"], rl["grab_oldest"]) == (True, 12, 400, "2020-04-30T17:54:30")
        # the probe itself is a query (one API call), never a grab
        assert usage.state(s, idx, "query").used == 8 and usage.state(s, idx, "grab").used == 12
