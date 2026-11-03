"""Schema migrations for SQLite.

``create_all()`` only creates missing *tables*. Columns that newer versions add to existing tables are
added here (``ALTER TABLE … ADD COLUMN`` with the model default), missing indexes are created, and
versioned data migrations run once (tracked in ``PRAGMA user_version``). Before anything changes on an
existing database a backup is written to ``/config/backups``.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Callable

from sqlalchemy import Engine, inspect
from sqlalchemy.engine import Connection

log = logging.getLogger("migrations")


def _literal(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        value = value.strftime("%Y-%m-%d %H:%M:%S.%f")
    elif isinstance(value, (list, dict)):
        value = json.dumps(value)
    return "'" + str(value).replace("'", "''") + "'"


def _default_sql(col) -> str | None:
    d = col.default
    if d is None:
        return None
    if getattr(d, "is_scalar", False):
        return _literal(d.arg)
    if getattr(d, "is_callable", False):
        try:
            return _literal(d.arg(None))  # list / dict / utcnow wrapped by SQLAlchemy
        except Exception:
            return None
    return None


def _missing_columns(engine: Engine) -> list[tuple[str, object]]:
    from ..db import Base

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    out = []
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        out += [(table.name, col) for col in table.columns if col.name not in have]
    return out


def _add_column(conn: Connection, engine: Engine, table: str, col) -> None:
    ddl = f'ALTER TABLE "{table}" ADD COLUMN "{col.name}" {col.type.compile(dialect=engine.dialect)}'
    default = _default_sql(col)
    if default is not None:
        ddl += f" DEFAULT {default}"
    conn.exec_driver_sql(ddl)
    log.info("Migration: Spalte %s.%s hinzugefügt", table, col.name)


# ---------------------------------------------------------------------------------- data migrations
# (version, description, fn) – append only, never reorder. Each fn must be safe on a fresh database.
def _m1_noop(conn: Connection) -> None:
    """Baseline: databases from before the migration system."""


def _m2_german_dl_regex(conn: Connection) -> None:
    """The seeded "German DL" format matched every German WEB-DL (the "DL" in "WEB-DL")."""
    from .seed import GERMAN_DL_REGEX, OLD_GERMAN_DL_REGEX

    for fid, raw in conn.exec_driver_sql("SELECT id, conditions FROM custom_formats").fetchall():
        conds = json.loads(raw) if isinstance(raw, str) else (raw or [])
        changed = False
        for c in conds:
            if c.get("type") == "title" and c.get("value") == OLD_GERMAN_DL_REGEX:
                c["value"] = GERMAN_DL_REGEX
                changed = True
        if changed:
            conn.exec_driver_sql("UPDATE custom_formats SET conditions = ? WHERE id = ?", (json.dumps(conds), fid))
            request_rescore()


def request_rescore() -> None:
    """Stored custom format scores of library files are stale – recompute them after start-up."""
    from ..config import CONFIG_DIR

    (CONFIG_DIR / ".rescore").write_text("1", "utf-8")


MIGRATIONS: list[tuple[int, str, Callable[[Connection], None]]] = [
    (1, "Baseline", _m1_noop),
    (2, "German-DL-Format trifft nicht mehr auf WEB-DL zu", _m2_german_dl_regex),
]
LATEST = MIGRATIONS[-1][0]


def _user_version(conn: Connection) -> int:
    return int(conn.exec_driver_sql("PRAGMA user_version").scalar() or 0)


def pending(engine: Engine) -> bool:
    with engine.connect() as conn:
        return bool(_missing_columns(engine)) or _user_version(conn) < LATEST


def migrate(engine: Engine, had_tables: bool) -> None:
    """Bring an existing database up to the current models. ``had_tables``: the DB existed before start."""
    from ..db import Base

    if had_tables and pending(engine):
        try:
            from ..services.backup import create_backup

            info = create_backup("migration")
            log.info("Backup vor Migration angelegt: %s", info["name"])
        except Exception:
            log.exception("Backup vor der Migration fehlgeschlagen – Migration läuft trotzdem")
    with engine.begin() as conn:
        for table, col in _missing_columns(engine):
            _add_column(conn, engine, table, col)
        for table in Base.metadata.sorted_tables:
            for idx in table.indexes:
                idx.create(conn, checkfirst=True)
        current = _user_version(conn)
        for version, desc, fn in MIGRATIONS:
            if version > current:
                if had_tables:
                    log.info("Migration %s: %s", version, desc)
                fn(conn)
                conn.exec_driver_sql(f"PRAGMA user_version = {int(version)}")
