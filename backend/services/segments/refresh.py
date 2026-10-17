"""Keep each held issuer's segment report current with its latest annual report.

US ISINs go to SEC EDGAR, everything else to ESEF via GLEIF and filings.xbrl.org.
ETFs and funds publish no segment note, so they end as `no_filing` or
`no_revenue` like any other issuer without one: no special case.

Runs inside an HTTP request (Cloud Run, request-scoped), so every loop is
bounded by a wall-clock budget. A recheck that finds the same filing id as last
time costs one or two small requests and no model call.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import SegmentCheck, SegmentReport
from backend.services.segments import esef, sec
from backend.services.segments.classify import REGIONS, SECTORS, ClassificationError, classify
from backend.services.segments.numbers import pick_partition
from backend.services.segments.sec import SourceUnavailable

logger = logging.getLogger(__name__)

RECHECK_DAYS = 7

# A user waiting on the portfolio page vs the daily reference-data cron.
REQUEST_SECONDS = 40.0
CRON_SECONDS = 120.0

# Outcomes cached until the next recheck. "ok" means at least one axis was published.
# The text is looked up when the exposure is read, so rewording it needs no migration.
OUTCOME_DETAIL = {
    "ok": "Informe anual leído",
    "no_issuer": "Sin emisor identificable en GLEIF ni en la SEC (ETF, fondo u otro producto)",
    "no_filing": "Sin informe anual estructurado publicado (ETF, fondo o emisor no cotizado en la UE/EE. UU.)",
    "no_revenue": "El informe no etiqueta un total con el que cuadrar el desglose (ingresos, margen bruto, ingresos de seguros o por alquiler)",
    "no_segments": "El informe no desglosa los ingresos por segmento ni por región",
    "unreconciled": "El desglose no cuadra con el total del informe",
}


def due_isins(
    db: Session, isins: Iterable[str], now: datetime | None = None, model=SegmentCheck
) -> list[str]:
    """ISINs never checked first, then those whose last check is older than RECHECK_DAYS.

    `model` is the check table: `SegmentCheck` here, `AiMentionCheck` for the AI reader.
    """
    now = now or datetime.now(timezone.utc)
    wanted = sorted(set(isins))
    checks = {c.isin: c for c in db.query(model).filter(model.isin.in_(wanted)).all()}
    cutoff = (now - timedelta(days=RECHECK_DAYS)).replace(tzinfo=None)
    never = [i for i in wanted if i not in checks]
    stale = sorted(
        (i for i in wanted if i in checks and _naive(checks[i].checked_at) < cutoff),
        key=lambda i: _naive(checks[i].checked_at),
    )
    return never + stale


def refresh(
    db: Session, holdings: dict[str, tuple[str | None, str]], budget_seconds: float
) -> dict:
    """Check the due ISINs in `holdings` ({isin: (ticker, name)}) until the budget is spent.

    Returns {"checked": n, "pending": m}; `pending` is what is still due.
    """
    due = due_isins(db, holdings)
    if not settings.openrouter_api_key:
        # Every report needs the classifier, so without a key each attempt would
        # download a filing only to fail at the last step, on every page load.
        return {"checked": 0, "pending": len(due)}
    deadline = time.monotonic() + budget_seconds
    checked = 0
    cik_by_ticker: dict[str, int] | None = None
    with sec.client() as sec_http, esef.client() as esef_http:
        for isin in due:
            if time.monotonic() >= deadline:
                break
            ticker, name = holdings[isin]
            try:
                if isin.startswith("US"):
                    if cik_by_ticker is None:
                        cik_by_ticker = sec.ticker_to_cik(sec_http)
                    _check_sec(db, isin, ticker, name, sec_http, cik_by_ticker)
                else:
                    _check_esef(db, isin, name, esef_http)
                db.commit()
                checked += 1
            except (SourceUnavailable, ClassificationError, esef.ExtractionError) as exc:
                # Not a fact about the issuer: leave no trace, retry next run.
                db.rollback()
                logger.warning("[segments] %s skipped: %s", isin, exc)
            except IntegrityError:
                # A concurrent refresh wrote the same row first; its answer stands.
                db.rollback()
            except Exception:
                db.rollback()
                logger.exception("[segments] %s failed", isin)
    return {"checked": checked, "pending": len(due_isins(db, holdings))}


def _record(
    db: Session, isin: str, outcome: str, filing_id: str | None = None, model=SegmentCheck
) -> None:
    row = db.query(model).filter(model.isin == isin).one_or_none()
    if row is None:
        row = model(isin=isin, outcome=outcome)
        db.add(row)
    row.outcome = outcome
    row.filing_id = filing_id
    row.checked_at = datetime.now(timezone.utc)


# Answers that say how well FinView read the filing, not what the filing says. They
# are re-read at each weekly recheck: an improvement to the reader (the table fix of
# 2026-10-17 turned unreadable notes into readable rows; the bank, insurance and rental
# totals the same day gave `no_revenue` filings a total) must reach a report already
# checked, not wait a year for the issuer's next one.
REREAD_OUTCOMES = frozenset({"unreconciled", "no_segments", "no_revenue"})


def _already_read(db: Session, isin: str, filing_id: str, model=SegmentCheck) -> bool:
    """Same filing as the last check: refresh the timestamp, keep the answer."""
    row = db.query(model).filter(model.isin == isin).one_or_none()
    if row is None or row.filing_id != filing_id or row.outcome in REREAD_OUTCOMES:
        return False
    row.checked_at = datetime.now(timezone.utc)
    return True


def _check_sec(db, isin, ticker, name, http, cik_by_ticker) -> None:
    cik = cik_by_ticker.get((ticker or "").upper())
    if cik is None:
        return _record(db, isin, "no_issuer")
    filing = sec.latest_10k(http, cik)
    if filing is None:
        return _record(db, isin, "no_filing")
    if _already_read(db, isin, filing.filing_id):
        return None
    files = sec.xbrl_files(http, filing)
    xml = sec.fetch_instance(http, filing, files)
    instance = sec.parse_instance(xml) if xml else None
    if instance is None:
        return _record(db, isin, "no_revenue", filing.filing_id)

    labels = sec.fetch_labels(http, filing, files)
    candidates: dict[str, list[list[tuple[str, Decimal]]]] = {"business": [], "geography": []}
    for axis_name, by_member in instance.axes.items():
        chosen = pick_partition(by_member, instance.total)
        if not chosen:
            continue
        lines = [(labels.get(m) or sec.member_label(m), by_member[m]) for m in chosen]
        if axis_name in sec.BUSINESS_AXES:
            candidates["business"].append(lines)
        if axis_name in sec.GEOGRAPHY_AXES:
            candidates["geography"].append(lines)

    _store(
        db,
        isin,
        name,
        "sec",
        filing.filing_id,
        filing.url,
        filing.period_end,
        instance.currency,
        instance.total,
        "revenue",
        candidates,
        {"business": "absent", "geography": "absent"},
    )


def _check_esef(db, isin, name, http) -> None:
    lei = esef.isin_to_lei(http, isin)
    if lei is None:
        return _record(db, isin, "no_issuer")
    filing = esef.latest_filing(http, lei)
    if filing is None:
        return _record(db, isin, "no_filing")
    if _already_read(db, isin, filing.filing_id):
        return None
    report = esef.fetch_report(http, filing)
    if report is None:
        return _record(db, isin, "no_revenue", filing.filing_id)
    if not report.note:
        return _record(db, isin, "no_segments", filing.filing_id)

    rows = esef.extract(name, report, report.period_end)
    candidates: dict[str, list[list[tuple[str, Decimal]]]] = {"business": [], "geography": []}
    status: dict[str, str] = {}
    for axis in ("business", "geography"):
        lines, status[axis] = esef.verify(rows[axis], report)
        if lines:
            candidates[axis].append(lines)

    _store(
        db,
        isin,
        name,
        "esef",
        filing.filing_id,
        filing.url,
        report.period_end,
        report.currency,
        report.total,
        report.measure,
        candidates,
        status,
    )


def _store(
    db, isin, name, source, filing_id, url, period_end, currency, total, measure, candidates, status
) -> None:
    """Classify the candidate breakdowns, keep the best per axis, write the report."""
    labels = {
        axis: sorted({label for lines in candidates[axis] for label, _ in lines})
        for axis in ("business", "geography")
    }
    categories = classify(name, labels["business"], labels["geography"])

    stored: list[dict] = []
    for axis, taxonomy in (("business", SECTORS), ("geography", REGIONS)):
        if not candidates[axis]:
            continue
        best = min(candidates[axis], key=lambda lines: _unassigned_share(lines, categories[axis]))
        status[axis] = "ok"
        for label, value in best:
            category = categories[axis].get(label, "unassigned")
            stored.append(
                {
                    "axis": axis,
                    "label": label,
                    "value": str(value),
                    "category": category if category in taxonomy else "unassigned",
                }
            )

    if not stored:
        failed = {s for s in status.values() if s != "absent"}
        return _record(db, isin, "unreconciled" if failed else "no_segments", filing_id)

    row = (
        db.query(SegmentReport)
        .filter(SegmentReport.isin == isin, SegmentReport.fiscal_year == period_end.year)
        .one_or_none()
    )
    if row is None:
        row = SegmentReport(isin=isin, fiscal_year=period_end.year)
        db.add(row)
    row.period_end = period_end
    row.source = source
    row.filing_id = filing_id
    row.source_url = url
    row.currency = currency
    row.total_revenue = total
    row.measure = measure
    row.lines = json.dumps(stored, ensure_ascii=False)
    row.axis_status = json.dumps(status)
    _record(db, isin, "ok", filing_id)


def _unassigned_share(lines: list[tuple[str, Decimal]], categories: dict[str, str]) -> Decimal:
    """Of a breakdown's positive revenue, the part the classifier could not place.

    Apple tags its segments by region and its revenue by product; for sectors the
    product breakdown places everything, the regional one nothing. Choosing the
    candidate that places the most turns that into one rule for both axes.
    """
    positive = [(label, v) for label, v in lines if v > 0]
    total = sum((v for _, v in positive), Decimal(0))
    if total <= 0:
        return Decimal(1)
    lost = sum(
        (v for label, v in positive if categories.get(label, "unassigned") == "unassigned"),
        Decimal(0),
    )
    return lost / total


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt
