"""The one owner of every Ideas row.

Ideas is computed from the same public feeds for everyone, the notification
channels are global env vars, and the frontend keeps no per-user geo state —
so N accounts used to mean N identical copies of every signal and checkpoint
(the cycle was ~2 s per user after the shared half) and, for a while, N pages
of the same event. The pipeline now runs once, under a system user that owns
the rows, and every reader is served that user's rows.

The owner is a ``users`` row because ``geo_signals``, ``geo_checkpoints`` and
``geo_cycle_runs`` carry a NOT NULL foreign key to ``users`` and there is no
Alembic: relaxing the column or dropping it is DDL in prod, while one more row
is not. It is inactive and has no password, so it can neither log in nor be
registered over (the email is taken).

On the boot that creates the owner, the history of the oldest account is
adopted: this deployment was a personal tool whose first account had been the
pipeline's only real reader, and without the adoption the first shared cycle
would re-track every live event as new and page each one again. Other accounts'
copies are left in place and simply never read.
"""

import logging

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import GeoCheckpoint, GeoCycleRun, GeoSignal, User

logger = logging.getLogger(__name__)

GEO_OWNER_EMAIL = "ideas-system@finview.internal"
GEO_OWNER_NAME = "Ideas (sistema)"

_OWNED_TABLES = (GeoSignal, GeoCheckpoint, GeoCycleRun)


def _find(db: Session) -> User | None:
    return db.query(User).filter(User.email == GEO_OWNER_EMAIL).first()


def _adopt_legacy_history(db: Session, owner_id: int) -> None:
    legacy = db.query(func.min(User.id)).filter(User.id != owner_id).scalar()
    if legacy is None:
        return
    moved = {
        table.__tablename__: db.execute(
            update(table).where(table.user_id == legacy).values(user_id=owner_id)
        ).rowcount
        for table in _OWNED_TABLES
    }
    logger.info("geo owner: adopted user %s history %s", legacy, moved)


def geo_owner_id(db: Session) -> int:
    """The owner's id, creating the row (and adopting history) on first use.

    Startup does this once per boot; this is the runtime path for any session
    that gets there first (tests, a fresh database) and it is idempotent under
    concurrency: a lost race on the unique email re-reads the winner's row.
    """
    owner = _find(db)
    if owner is not None:
        return owner.id
    owner = User(email=GEO_OWNER_EMAIL, name=GEO_OWNER_NAME, password_hash=None, is_active=False)
    db.add(owner)
    try:
        db.flush()
        _adopt_legacy_history(db, owner.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        owner = _find(db)
        if owner is None:
            raise
        return owner.id
    logger.info("geo owner: created system user %s", owner.id)
    return owner.id


def ensure_geo_owner() -> None:
    """Startup hook: create the owner before the first request needs it."""
    from backend.database import SessionLocal

    with SessionLocal() as db:
        try:
            geo_owner_id(db)
        except Exception:
            # The next request retries through geo_owner_id; startup must not
            # die on a transient DB error.
            logger.exception("geo owner: could not ensure the system user at startup")
