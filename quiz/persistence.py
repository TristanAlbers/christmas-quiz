"""Short SQLite transaction boundaries for commands and projections."""

import sqlite3
import uuid
from contextlib import contextmanager

from django.db import OperationalError, connection
from django.db.backends.signals import connection_created

from quiz.contracts import ApplicationError


def configure_sqlite(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA busy_timeout = 5000")
        # WAL persists in the database and allows readers during a writer transaction.
        if connection.settings_dict["NAME"] != ":memory:":
            cursor.execute("PRAGMA journal_mode")
            if cursor.fetchone()[0].lower() != "wal":
                cursor.execute("PRAGMA journal_mode = WAL")


connection_created.connect(
    configure_sqlite, dispatch_uid="quiz_sqlite_policy", weak=False
)


@contextmanager
def _transaction(begin):
    # A nested call uses a savepoint, so controlled tests and application helpers
    # can join an existing writer transaction on this same connection.
    connection.ensure_connection()
    raw = connection.connection
    nested = raw.in_transaction
    prior_rollback = connection.needs_rollback
    savepoint = f"quiz_{uuid.uuid4().hex}" if nested else None
    try:
        raw.execute(f"SAVEPOINT {savepoint}" if nested else f"BEGIN {begin}")
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise ApplicationError("temporarily_busy") from exc
        raise
    try:
        yield
    except BaseException:
        if nested:
            raw.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            raw.execute(f"RELEASE SAVEPOINT {savepoint}")
        else:
            raw.execute("ROLLBACK")
        connection.needs_rollback = prior_rollback
        raise
    else:
        raw.execute(f"RELEASE SAVEPOINT {savepoint}" if nested else "COMMIT")


def immediate_transaction():
    """Acquire the SQLite writer slot before any mutable-state read."""
    return _transaction("IMMEDIATE")


def read_snapshot():
    """Use one short, consistent DEFERRED read transaction for a projection."""
    return _transaction("DEFERRED")


def is_busy_error(exc):
    return isinstance(exc, (sqlite3.OperationalError, OperationalError)) and any(
        word in str(exc).lower() for word in ("locked", "busy")
    )
