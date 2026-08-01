"""Transaction-scoped PostgreSQL advisory locks for financial mutations."""

import hashlib

from sqlalchemy import text
from sqlalchemy.orm import Session


def _lock_key(namespace: str, *parts: object) -> int:
    payload = "\x1f".join([namespace, *(str(part) for part in parts)])
    return int.from_bytes(
        hashlib.sha256(payload.encode()).digest()[:8],
        byteorder="big",
        signed=True,
    )


def advisory_xact_lock(db: Session, namespace: str, *parts: object) -> None:
    """Serialize a logical mutation until the current transaction ends.

    SQLite is used by tests and local tooling and has its own write locking, so
    this is intentionally a no-op outside PostgreSQL.
    """
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _lock_key(namespace, *parts)},
    )


def lock_fifo_recalculation(db: Session, user_id: int) -> None:
    """Allow only one FIFO rebuild per user in a database transaction."""
    advisory_xact_lock(db, "fifo-recalculation", user_id)


def lock_import_slot(
    db: Session,
    user_id: int | None,
    broker: str,
    fiscal_year: int | str,
    file_hash: str,
) -> None:
    """Serialize an import before it reads or mutates financial state.

    The stable account and file locks protect account creation and the legacy
    globally-unique file hash across fiscal years and tenants.  The FIFO lock
    is deliberately acquired here, before any import writes, so a concurrent
    rebuild cannot deadlock while waiting on rows already changed by us.
    """
    owner = user_id if user_id is not None else "legacy"
    advisory_xact_lock(db, "import-account", owner, broker)
    advisory_xact_lock(db, "import-file", broker, file_hash)
    advisory_xact_lock(
        db,
        "import-slot",
        owner,
        broker,
        fiscal_year,
    )
    if user_id is not None:
        lock_fifo_recalculation(db, user_id)
