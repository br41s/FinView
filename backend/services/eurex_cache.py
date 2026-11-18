"""Eurex option products, cached per symbol and day for the options cycle.

Production runs on Cloud Run with `--min-instances=0`, so every cron cycle is a
cold start: the in-memory RDF of the day is always empty and each cycle
re-downloaded and re-parsed the 29 MB zip. In the DB the day's answer survives
the process. A failed download is never cached, only the day's real answer,
including "Eurex does not list this symbol".
"""

import json
import logging
from datetime import date, datetime, timezone

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import sessionmaker

from backend.database import SessionLocal
from backend.models import EurexProductCache

logger = logging.getLogger(__name__)

_UPDATE_COLUMNS = ("product", "fetched_at")


def load(
    sym: str, day: date, session_factory: sessionmaker | None = None
) -> tuple[bool, dict | None]:
    """The cached product for (sym, day): (hit, product).

    `(True, None)` is a stored "not listed today" and keeps the caller from
    touching the RDF. `(False, None)` is a miss, or any failure — the caller
    then downloads as before, so a broken cache costs a download, never a cycle.
    """
    session = None
    try:
        session = (session_factory or SessionLocal)()
        row = (
            session.query(EurexProductCache)
            .filter(EurexProductCache.sym == sym, EurexProductCache.rdf_date == day)
            .one_or_none()
        )
        if row is None:
            return (False, None)
        if row.product is None:
            return (True, None)
        product = json.loads(row.product)
        if not isinstance(product, dict):
            return (False, None)
        return (True, product)
    except Exception:
        logger.warning("Eurex cache read failed for %s", sym, exc_info=True)
        return (False, None)
    finally:
        if session is not None:
            session.close()


def store(
    sym: str, day: date, product: dict | None, session_factory: sessionmaker | None = None
) -> None:
    """Upsert the day's answer for `sym`, keeping the table to that one day.

    Later writes win and a concurrent duplicate does not raise. `product=None`
    stores NULL, the real answer for a symbol Eurex does not list; a failed
    download never reaches here.
    """
    session = None
    try:
        session = (session_factory or SessionLocal)()
        insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
        stmt = insert(EurexProductCache).values(
            sym=sym,
            rdf_date=day,
            product=json.dumps(product) if product is not None else None,
            fetched_at=datetime.now(timezone.utc),
        )
        session.execute(stmt.on_conflict_do_update(
            index_elements=["sym", "rdf_date"],
            set_={c: stmt.excluded[c] for c in _UPDATE_COLUMNS},
        ))
        session.execute(delete(EurexProductCache).where(EurexProductCache.rdf_date < day))
        session.commit()
        logger.info("Eurex product cached: %s (%s)", sym, "listed" if product else "not listed")
    except Exception:
        if session is not None:
            session.rollback()
        logger.warning("Eurex cache write failed for %s", sym, exc_info=True)
    finally:
        if session is not None:
            session.close()
