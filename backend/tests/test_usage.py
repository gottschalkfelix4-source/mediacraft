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
