"""Broker sync: keep a user's IBKR data current through the Flex Web Service.

A sync is a *run* of *steps*. Each step imports at most one calendar year and
returns, because production work must finish inside one HTTP request; the
frontend keeps calling while the state is "running". The run lives on the
`BrokerConnection` row (`queue`, `pending_reference`), so a closed tab or a
timed-out request resumes where it stopped instead of starting over.

Each year goes through `import_ibkr_report`, the same path as an uploaded
Activity Statement: it replaces that year's IBKR import (upload or sync, one
source per broker and year) and recalculates FIFO from that year onward, so
every step leaves the ledger consistent, whatever happens to the next one.

Locking: the advisory lock covers the row changes and the one SendRequest that
reserves a statement, never the polling that waits for it. Two concurrent steps
may poll the same reference; whichever re-locks second sees the reference is
gone and returns without importing.
"""

import hashlib
import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from backend.importers.ibkr_flex import FlexQueryError, parse_ibkr_flex, read_date_opened
from backend.models import Broker, BrokerConnection, User
from backend.services.credentials_crypto import decrypt_secret, encrypt_secret
from backend.services.db_locks import advisory_xact_lock
from backend.services.ibkr_flex import FlexError, poll_statement, send_request
from backend.services.import_service import import_ibkr_report

logger = logging.getLogger(__name__)

ORIGIN = "ibkr_flex"
# Leaves room for parsing, the import and FIFO inside one request.
POLL_BUDGET_SECONDS = 20.0
RETRY_AFTER_SECONDS = 5
# Until the end of March the previous year is refreshed too: IBKR posts
# corrections and reclassified dividends during the first quarter.
PREVIOUS_YEAR_REFRESH_UNTIL_MONTH = 3

MISSING_DATE_OPENED = (
    "Para traer todo el historial, añade el campo 'Date Opened' a la sección "
    "Account Information de tu Flex Query."
)


class NotConnected(LookupError):
    pass


def routine_years(today: date) -> list[int]:
    """Years a routine sync refreshes, oldest first. Data runs until yesterday."""
    yesterday = today - timedelta(days=1)
    years = [yesterday.year]
    if today.month <= PREVIOUS_YEAR_REFRESH_UNTIL_MONTH and yesterday.year == today.year:
        years.insert(0, today.year - 1)
    return years


def history_years(opened: date, today: date) -> list[int]:
    """Older years a full-history run adds, oldest first. Never a year with no data
    yet: on 1 January the current year has not had a day."""
    routine = set(routine_years(today))
    last = (today - timedelta(days=1)).year
    return [y for y in range(opened.year, last + 1) if y not in routine]


def statement_period(year: int, today: date, opened: date | None) -> tuple[date, date]:
    start = date(year, 1, 1)
    if opened is not None and opened.year == year:
        start = opened
    end = min(date(year, 12, 31), today - timedelta(days=1))
    return start, end


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _lock(db: Session, user_id: int) -> BrokerConnection | None:
    advisory_xact_lock(db, "broker-sync", user_id, Broker.IBKR.value)
    return (
        db.query(BrokerConnection)
        .filter(BrokerConnection.user_id == user_id, BrokerConnection.broker == Broker.IBKR)
        .populate_existing()
        .one_or_none()
    )


def _require(db: Session, user_id: int) -> BrokerConnection:
    conn = _lock(db, user_id)
    if conn is None:
        raise NotConnected
    return conn


def get_connection(db: Session, user: User) -> BrokerConnection | None:
    return (
        db.query(BrokerConnection)
        .filter(BrokerConnection.user_id == user.id, BrokerConnection.broker == Broker.IBKR)
        .one_or_none()
    )


def connect(
    db: Session, user: User, *, token: str, query_id: str, full_history: bool
) -> BrokerConnection:
    """Store (or replace) the user's IBKR connection. Any run in progress is dropped."""
    conn = _lock(db, user.id)
    if conn is None:
        conn = BrokerConnection(user_id=user.id, broker=Broker.IBKR)
        db.add(conn)
    conn.query_id = query_id
    conn.token_encrypted = encrypt_secret(token)
    conn.token_hint = token[-4:]
    conn.history_pending = full_history
    conn.queue = []
    conn.run_total = 0
    conn.gaps = {}
    conn.pending_reference = None
    conn.pending_year = None
    conn.last_error = None
    # Another token may be another account: what the old one taught does not carry over.
    conn.account_opened_on = None
    conn.last_synced_at = None
    db.commit()
    return conn


def disconnect(db: Session, user: User) -> None:
    """Forget the token. Data already imported stays, like an uploaded file."""
    conn = _lock(db, user.id)
    if conn is not None:
        db.delete(conn)
    db.commit()


def progress(conn: BrokerConnection, state: str, message: str | None = None) -> dict:
    total = conn.run_total or 0
    return {
        "state": state,
        "done": max(total - len(conn.queue or []), 0),
        "total": total,
        "year": conn.pending_year or ((conn.queue or [None])[0]),
        "message": message,
        "gaps": dict(conn.gaps or {}),
        "retry_after": RETRY_AFTER_SECONDS,
    }


def _finish_year(conn: BrokerConnection, year: int) -> None:
    conn.pending_reference = None
    conn.pending_year = None
    conn.queue = [y for y in (conn.queue or []) if y != year]


def _record_gap(conn: BrokerConnection, year: int, message: str) -> None:
    conn.gaps = {**(conn.gaps or {}), str(year): message}
    _finish_year(conn, year)


def _stop_run(conn: BrokerConnection, message: str) -> None:
    conn.pending_reference = None
    conn.pending_year = None
    conn.queue = []
    conn.last_error = message


def _state_after(conn: BrokerConnection) -> str:
    return "running" if conn.queue else "done"


def _learn_opening(conn: BrokerConnection, opened: date | None, today: date) -> None:
    """Record where the account starts and, if history was asked for, queue it.

    Called on every outcome of a statement that arrived — imported, a gap, or an
    import that failed and rolled back — so one bad year cannot hide the rest.
    """
    if opened is not None:
        conn.account_opened_on = opened
    if not conn.history_pending:
        return
    if opened is None:
        conn.gaps = {**(conn.gaps or {}), "historial": MISSING_DATE_OPENED}
        return
    older = [y for y in history_years(opened, today) if y not in (conn.queue or [])]
    conn.queue = [*(conn.queue or []), *older]
    conn.run_total = (conn.run_total or 0) + len(older)
    conn.history_pending = False


def _next_year(conn: BrokerConnection, today: date) -> tuple[int, date, date] | None:
    """First queued year with something to fetch; years with none leave the queue."""
    while conn.queue:
        year = conn.queue[0]
        start, end = statement_period(year, today, conn.account_opened_on)
        opened = conn.account_opened_on
        if start <= end and (opened is None or year >= opened.year):
            return year, start, end
        conn.queue = conn.queue[1:]
        conn.run_total = max((conn.run_total or 1) - 1, 0)
    return None


def _wrong_period(parsed, year: int) -> str | None:
    if parsed.from_date.year == year and parsed.to_date.year == year:
        return None
    return (
        f"IBKR devolvió el periodo {parsed.from_date:%d/%m/%Y}–{parsed.to_date:%d/%m/%Y} "
        f"al pedir {year}. Revisa que la Flex Query no tenga un periodo fijo."
    )


def _on_flex_error(db: Session, conn: BrokerConnection, year: int, exc: FlexError) -> dict:
    """Apply what an IBKR error means to the run, commit, and report it."""
    message = str(exc)
    if exc.transient:
        db.commit()
        return progress(conn, "running", message)
    if exc.stale_reference:
        conn.pending_reference = None  # next step asks for the statement again
        db.commit()
        return progress(conn, "running", message)
    if exc.connection:
        _stop_run(conn, message)
        db.commit()
        return progress(conn, "error", message)
    if exc.code is None:
        # Could not reach IBKR at all: keep the run, the next sync resumes it.
        conn.last_error = message
        db.commit()
        return progress(conn, "error", message)
    _record_gap(conn, year, message)
    state = _state_after(conn)
    db.commit()
    return progress(conn, state, message)


def sync_step(
    db: Session,
    user: User,
    *,
    today: date | None = None,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Advance the user's IBKR sync by at most one year. See the module docstring."""
    today = today or _utcnow().date()

    # 1. Under the lock: start a run if idle, and make sure a statement is requested.
    conn = _require(db, user.id)
    token = decrypt_secret(conn.token_encrypted)
    if conn.pending_reference is None and not conn.queue:
        conn.queue = routine_years(today)
        conn.run_total = len(conn.queue)
        conn.gaps = {}
        conn.last_error = None
    if conn.pending_reference is None:
        nxt = _next_year(conn, today)
        if nxt is None:
            db.commit()
            return progress(conn, "done")
        year, start, end = nxt
        try:
            conn.pending_reference = send_request(token, conn.query_id, start, end, client=client)
        except FlexError as exc:
            return _on_flex_error(db, conn, year, exc)
        conn.pending_year = year
    reference = conn.pending_reference
    year = conn.pending_year
    db.commit()  # releases the lock: the statement is never polled while holding it

    # 2. Without the lock: wait for IBKR, bounded.
    try:
        polled = poll_statement(
            token, reference, budget_seconds=POLL_BUDGET_SECONDS, client=client, sleep=sleep
        )
    except FlexError as exc:
        conn = _require(db, user.id)
        if conn.pending_reference != reference:
            db.rollback()
            return progress(conn, "running" if conn.queue else "done")
        return _on_flex_error(db, conn, year, exc)
    if polled.xml is None:
        return progress(conn, "running", f"IBKR está generando el informe de {year}.")

    # 3. Parse outside the lock: pure work on the downloaded text.
    parsed = None
    parse_error: ValueError | None = None
    try:
        parsed = parse_ibkr_flex(polled.xml)
    except ValueError as exc:
        parse_error = exc
    opened = parsed.date_opened if parsed is not None else read_date_opened(polled.xml)
    query_error = str(parse_error) if isinstance(parse_error, FlexQueryError) else None
    if parsed is not None:
        query_error = _wrong_period(parsed, year)

    # 4. Under the lock again: only the step that still owns the reference imports.
    conn = _require(db, user.id)
    if conn.pending_reference != reference:
        db.rollback()
        return progress(conn, "running" if conn.queue else "done")

    if query_error is not None:
        _stop_run(conn, query_error)
        db.commit()
        return progress(conn, "error", query_error)
    _learn_opening(conn, opened, today)
    if parsed is None:
        _record_gap(conn, year, str(parse_error))
        state = _state_after(conn)
        db.commit()
        return progress(conn, state, str(parse_error))

    _finish_year(conn, year)
    conn.last_synced_at = _utcnow()
    state = _state_after(conn)

    # The import commits, and with it the connection changes above: the year is
    # marked done in the same transaction that stores it.
    digest = hashlib.sha256(polled.xml.encode()).hexdigest()
    try:
        result = import_ibkr_report(
            db,
            parsed.report,
            digest,
            f"IBKR Flex {year}",
            user.id,
            origin=ORIGIN,
        )
    except ValueError as exc:
        db.rollback()  # also undoes the connection changes above
        logger.warning("IBKR Flex import of %s failed for user %s: %s", year, user.id, exc)
        conn = _require(db, user.id)
        if conn.pending_reference != reference:
            db.rollback()
            return progress(conn, "running" if conn.queue else "done")
        _learn_opening(conn, opened, today)
        _record_gap(conn, year, str(exc))
        state = _state_after(conn)
        db.commit()
        return progress(conn, state, str(exc))
    db.commit()  # a duplicate statement returns before the import's own commit
    logger.info(
        "IBKR Flex %s imported for user %s: %s", year, user.id, result.get("status")
    )
    return progress(conn, state, None)


def _as_utc(value: datetime | None) -> datetime | None:
    """DateTime columns come back naive; unstamped, the browser reads them as local time."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def connection_out(conn: BrokerConnection | None, *, enabled: bool) -> dict:
    if conn is None:
        return {"enabled": enabled, "connected": False}
    return {
        "enabled": enabled,
        "connected": True,
        "query_id": conn.query_id,
        "token_hint": conn.token_hint,
        "account_opened_on": conn.account_opened_on,
        "history_pending": conn.history_pending,
        "last_synced_at": _as_utc(conn.last_synced_at),
        "last_error": conn.last_error,
        "in_progress": bool(conn.queue or conn.pending_reference),
        "gaps": dict(conn.gaps or {}),
    }
