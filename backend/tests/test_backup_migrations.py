import zipfile
from datetime import timedelta

import pytest


def test_migration_adds_missing_column():
    from sqlalchemy import inspect

    from app.core.migrations import migrate
    from app.db import engine

    with engine.begin() as conn:
        conn.exec_driver_sql('ALTER TABLE "queue" DROP COLUMN "stalled_since"')
    assert "stalled_since" not in {c["name"] for c in inspect(engine).get_columns("queue")}
    migrate(engine, had_tables=True)
    assert "stalled_since" in {c["name"] for c in inspect(engine).get_columns("queue")}
    with engine.connect() as conn:
        from app.core.migrations import LATEST

        assert conn.exec_driver_sql("PRAGMA user_version").scalar() == LATEST


def test_migration_default_for_not_null_columns():
    from sqlalchemy import inspect

    from app.core.migrations import migrate
    from app.db import engine

    with engine.begin() as conn:
        conn.exec_driver_sql('ALTER TABLE "notifications" DROP COLUMN "on_health"')
        conn.exec_driver_sql("INSERT INTO notifications (name, kind, enabled, on_grab, on_import, on_upgrade, on_failure, on_delete, on_rename, on_limit, settings) "
                             "VALUES ('x', 'webhook', 1, 1, 1, 1, 1, 0, 0, 0, '{}')")
    migrate(engine, had_tables=True)
    assert "on_health" in {c["name"] for c in inspect(engine).get_columns("notifications")}
    with engine.begin() as conn:
        assert conn.exec_driver_sql("SELECT on_health FROM notifications WHERE name='x'").scalar() == 0
        conn.exec_driver_sql("DELETE FROM notifications WHERE name='x'")


def test_backup_create_validate_and_stage(tmp_root):
    from app import config
    from app.services import backup

    info = backup.create_backup("manual")
    assert info["kind"] == "manual"
    path = backup.backup_file(info["name"])
    with zipfile.ZipFile(path) as z:
        assert {"mediacraft.db", "backup.json"} <= set(z.namelist())
    assert any(b["name"] == info["name"] for b in backup.list_backups())

    backup.stage_restore_from(info["name"])
    assert backup.restore_pending()
    (config.CONFIG_DIR / "restore_pending.zip").unlink()

    with pytest.raises(ValueError):
        backup.stage_restore(b"not a zip")
    with pytest.raises(ValueError):
        backup.backup_file("../mediacraft.db")
    backup.delete_backup(info["name"])
    assert not path.exists()


def test_backup_api_roundtrip():
    from fastapi.testclient import TestClient

    from app import config
    from app.main import app

    c = TestClient(app, headers={"X-Api-Key": config.API_KEY})
    created = c.post("/api/v1/system/backups").json()
    listing = c.get("/api/v1/system/backups").json()
    assert created["name"] in [b["name"] for b in listing["backups"]]
    r = c.get(f"/api/v1/system/backups/{created['name']}")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert c.post("/api/v1/system/backups-upload/restore?restart_now=false", content=b"junk").status_code == 400
    assert c.delete(f"/api/v1/system/backups/{created['name']}").json()["ok"]


def test_stall_tracking():
    from app.models import QueueItem, utcnow
    from app.services.queue import _stalled

    q = QueueItem(progress=10.0)
    assert not _stalled(q, "downloading", 10.0, 10.0, 2)  # starts the clock
    assert q.stalled_since is not None
    q.stalled_since = utcnow() - timedelta(hours=3)
    assert _stalled(q, "warning", 10.0, 10.0, 2)
    assert not _stalled(q, "downloading", 11.0, 10.0, 2)  # progress resets
    assert q.stalled_since is None
    _stalled(q, "downloading", 11.0, 11.0, 2)
    q.stalled_since = utcnow() - timedelta(hours=3)
    assert not _stalled(q, "paused", 11.0, 11.0, 2)  # paused on purpose
    q.stalled_since = utcnow() - timedelta(hours=3)
    assert not _stalled(q, "downloading", 11.0, 11.0, 0)  # timeout disabled


def test_migration_fixes_german_dl_format():
    import json

    from app.core.migrations import _m2_german_dl_regex
    from app.core.seed import GERMAN_DL_REGEX, OLD_GERMAN_DL_REGEX
    from app.db import engine

    old = [{"type": "language", "value": "german", "required": True},
           {"type": "title", "value": OLD_GERMAN_DL_REGEX, "required": True}]
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO custom_formats (name, conditions) VALUES ('Alt DL', ?)", (json.dumps(old),))
        _m2_german_dl_regex(conn)
        raw = conn.exec_driver_sql("SELECT conditions FROM custom_formats WHERE name='Alt DL'").scalar()
        assert json.loads(raw)[1]["value"] == GERMAN_DL_REGEX
        conn.exec_driver_sql("DELETE FROM custom_formats WHERE name='Alt DL'")


def test_rescore_files(tmp_root):
    from app.db import session_scope
    from app.models import MediaFile, QualityProfile
    from app.services import library, maintenance

    with session_scope() as db:
        pid = db.query(QualityProfile).first().id
        m = library.add_movie(db, {"anilist": 994001}, pid, str(tmp_root),
                              meta={"provider": "anilist", "ids": {"anilist": 994001}, "title": "Scorefilm", "year": 2000})
        f = MediaFile(media_type="movie", movie_id=m.id, path="x.mkv", size=1, quality="WEBDL-1080p",
                      release_name="Scorefilm.2000.German.1080p.WEB-DL.x264-GRP", format_score=150)
        db.add(f)
        db.flush()
        fid = f.id
    with session_scope() as db:
        assert maintenance.rescore_files(db)["changed"] >= 1
        assert db.get(MediaFile, fid).format_score == 50  # German only, not German DL
