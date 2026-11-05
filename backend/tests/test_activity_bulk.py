"""Deleting several activity entries (queue, pending, history, blocklist) at once."""
from app.api.routes import media
from app.db import session_scope
from app.models import Blocklist, History, PendingRelease, QueueItem, utcnow


def test_bulk_delete_activity_entries():
    with session_scope() as db:
        hist = [History(event="grabbed", media_type="movie", source_title=f"Bulk.H{i}") for i in range(3)]
        blocks = [Blocklist(media_type="movie", source_title=f"Bulk.B{i}") for i in range(3)]
        pend = [PendingRelease(release_at=utcnow(), media_type="movie", title=f"Bulk.P{i}", indexer_id=1,
                               guid=f"bulk-p{i}", protocol="usenet") for i in range(3)]
        queue = [QueueItem(download_client_id=999999, download_id=f"bulk-q{i}", protocol="usenet",
                           title=f"Bulk.Q{i}", media_type="movie") for i in range(3)]
        db.add_all(hist + blocks + pend + queue)
        db.flush()

        assert media.bulk_delete_history({"ids": [hist[0].id, hist[1].id]}, db) == {"deleted": 2}
        assert media.bulk_delete_blocklist({"ids": [blocks[2].id]}, db) == {"deleted": 1}
        assert media.bulk_delete_pending({"ids": [p.id for p in pend]}, db) == {"deleted": 3}
        assert media.bulk_remove_queue({"ids": [queue[0].id, queue[2].id], "remove_from_client": True}, db) == {"deleted": 2}
        assert media.bulk_delete_history({"ids": []}, db) == {"deleted": 0}
        db.flush()

        assert [h.source_title for h in db.query(History).filter(History.source_title.like("Bulk.H%"))] == ["Bulk.H2"]
        assert sorted(b.source_title for b in db.query(Blocklist).filter(Blocklist.source_title.like("Bulk.B%"))) == ["Bulk.B0", "Bulk.B1"]
        assert db.query(PendingRelease).filter(PendingRelease.title.like("Bulk.P%")).count() == 0
        assert [q.title for q in db.query(QueueItem).filter(QueueItem.title.like("Bulk.Q%"))] == ["Bulk.Q1"]
