"""Data Supervisor — post-import validation and auto-resolution.

Runs after each broker import to detect and fix data inconsistencies:
- Missing buy transactions for dividends/holdings
- Rights (derechos) misclassified as SELL
- Stock splits (ISIN changes, qty mismatches)
- Scrip dividends needing conversion ratio verification
- Holdings qty mismatch vs calculated qty from transactions
- Missing Yahoo Finance ticker for ISIN
- Price sanity checks (extreme deviations)
"""

import json
import logging
import re
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from backend.models import (
    Account,
    DataIssue,
    ImportRecord,
    PortfolioHolding,
    Transaction,
    TransactionType,
)
from backend.services.db_locks import lock_fifo_recalculation
from backend.services.yahoo_budget import IMPORT_SECONDS, Budget

logger = logging.getLogger(__name__)

_ACQUISITION_TYPES = [
    TransactionType.BUY.value,
    TransactionType.SPINOFF.value,
]


def _issue_dedupe_key(issue: DataIssue) -> tuple[str, str | None, int | None]:
    """Keep transaction-specific basis issues distinct for the same ISIN."""
    tx_id = None
    if issue.issue_type == "missing_cost_basis":
        try:
            tx_id = int(json.loads(issue.resolution_data or "{}").get("tx_id"))
        except (TypeError, ValueError, json.JSONDecodeError):
            tx_id = None
    return issue.issue_type, issue.isin, tx_id


def _scope_tx_query(q, user_id: int | None):
    """Add user-scoping via Account join if user_id is provided."""
    if user_id is not None:
        q = q.join(Account, Transaction.account_id == Account.id).filter(Account.user_id == user_id)
    return q


def _scope_holding_query(q, user_id: int | None):
    """Add user-scoping to a PortfolioHolding query."""
    if user_id is not None:
        q = q.join(Account, PortfolioHolding.account_id == Account.id).filter(
            Account.user_id == user_id
        )
    return q


def _resolve_user_scope(db: Session, import_id: int | None, user_id: int | None) -> int:
    """Resolve and validate the owner for a supervisor run."""
    if import_id is None:
        if user_id is None:
            raise ValueError("run_checks requires import_id or user_id")
        return user_id

    owner_row = (
        db.query(Account.user_id)
        .select_from(ImportRecord)
        .join(Account, ImportRecord.account_id == Account.id)
        .filter(ImportRecord.id == import_id)
        .one_or_none()
    )
    if owner_row is None:
        raise ValueError(f"ImportRecord {import_id} not found")
    owner_user_id = owner_row[0]
    if owner_user_id is None:
        raise ValueError(f"ImportRecord {import_id} has no owning user")
    if user_id is not None and user_id != owner_user_id:
        raise ValueError(f"ImportRecord {import_id} does not belong to user {user_id}")
    return owner_user_id

# Patterns that indicate rights/derechos (not actual share sales)
_RIGHTS_PATTERNS = re.compile(
    r"\b(derechos?|rights?|drets?|bezugsrecht)\b",
    re.IGNORECASE,
)

# Scrip dividend indicators in transaction names
_SCRIP_PATTERNS = re.compile(
    r"\b(scrip|script|liberada|ampliaci[oó]n liberada)\b",
    re.IGNORECASE,
)

# Options/derivatives patterns in names — skip for ticker checks
_DERIVATIVE_PATTERNS = re.compile(
    r"\b[CP]\d+\.?\d*\s+\d{2}(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OKT|OCT|NOV|DEC|ENE|FEB|ABR|AGO|DIC)\d{2}\b",
    re.IGNORECASE,
)

# Bond/note indicators
_BOND_PATTERNS = re.compile(
    r"\b(bond|bono|note|letra|pagaré|pagare)\b",
    re.IGNORECASE,
)


def run_checks(db: Session, import_id: int | None = None, user_id: int | None = None) -> list[DataIssue]:
    """Run all data quality checks and return issues found.

    If import_id is given, focus checks on transactions from that import.
    If user_id is given (full audit), scope to that user's accounts.
    """
    user_id = _resolve_user_scope(db, import_id, user_id)
    lock_fifo_recalculation(db, user_id)
    issues: list[DataIssue] = []

    # One allowance for every Yahoo call this run makes. Both checks below loop
    # over securities one network call at a time, and a stalled Yahoo costs ~30s
    # per call whatever timeout the call site asks for — see yahoo_budget.
    budget = Budget(IMPORT_SECONDS, f"supervisor run (import {import_id})")

    issues.extend(_check_rights_as_sells(db, import_id, user_id))
    issues.extend(_check_missing_buys(db, import_id, user_id))
    issues.extend(_check_missing_cost_basis(db, import_id, user_id))
    issues.extend(_check_holdings_mismatch(db, import_id, user_id))
    issues.extend(_check_missing_ticker(db, import_id, user_id, budget=budget))
    issues.extend(_check_split_candidates(db, import_id, user_id, budget=budget))
    issues.extend(_check_price_sanity(db, import_id, user_id))

    # Persist issues, deduplicating against existing needs_input rows so
    # repeated supervisor runs don't create 5× copies of the same warning.
    existing_needs_input = {
        _issue_dedupe_key(row)
        for row in db.query(DataIssue)
        .outerjoin(ImportRecord, DataIssue.import_id == ImportRecord.id)
        .outerjoin(Account, ImportRecord.account_id == Account.id)
        .filter(
            DataIssue.status == "needs_input",
            and_(
                DataIssue.user_id == user_id,
                or_(DataIssue.import_id.is_(None), Account.user_id == user_id),
            ),
        )
        .all()
    }
    persisted: list[DataIssue] = []
    for issue in issues:
        issue_key = _issue_dedupe_key(issue)
        if issue.status == "needs_input" and issue_key in existing_needs_input:
            continue
        issue.user_id = user_id
        db.add(issue)
        persisted.append(issue)
        if issue.status == "needs_input":
            existing_needs_input.add(issue_key)
    db.flush()

    recalculate_from_years = []
    for issue in persisted:
        if issue.status != "auto_resolved":
            continue
        try:
            year = json.loads(issue.resolution_data or "{}").get(
                "recalculate_from_year"
            )
        except json.JSONDecodeError:
            year = None
        if year is not None:
            recalculate_from_years.append(int(year))
    if recalculate_from_years:
        from backend.services.fifo_engine import recalculate_fifo_from_year

        recalculate_fifo_from_year(db, min(recalculate_from_years), user_id)

    logger.info(
        "Data supervisor: %d issues found, %d persisted (import_id=%s)",
        len(issues),
        len(persisted),
        import_id,
    )
    return persisted


def _check_missing_cost_basis(
    db: Session,
    import_id: int | None,
    user_id: int | None = None,
) -> list[DataIssue]:
    """Flag spin-off acquisitions whose inherited basis is not in the source."""
    q = db.query(Transaction).filter(
        Transaction.type == TransactionType.SPINOFF.value,
        Transaction.price <= 0,
        Transaction.isin.isnot(None),
        Transaction.isin != "",
    )
    if import_id is not None:
        q = q.filter(Transaction.import_id == import_id)
    q = _scope_tx_query(q, user_id)

    return [
        DataIssue(
            import_id=tx.import_id,
            issue_type="missing_cost_basis",
            severity="warning",
            isin=tx.isin,
            name=tx.name,
            description=(
                "Acciones recibidas por spin-off sin coste de adquisición. "
                "La cantidad participa en la cronología FIFO, pero una venta que "
                "alcance este lote no tendrá ajuste fiscal hasta completar el coste."
            ),
            status="needs_input",
            resolution_data=json.dumps({
                "tx_id": tx.id,
                "trade_date": tx.trade_date.isoformat(),
                "quantity": str(tx.quantity),
            }),
        )
        for tx in q.order_by(Transaction.trade_date.asc(), Transaction.id.asc()).all()
    ]


# ---------------------------------------------------------------------------
# Check 1: Rights misclassified as SELL
# ---------------------------------------------------------------------------

def _check_rights_as_sells(db: Session, import_id: int | None, user_id: int | None = None) -> list[DataIssue]:
    """Detect SELL transactions whose name contains 'derechos/rights'.

    These are typically scrip dividend rights sold for cash — they should
    be DIVIDEND type with qty=0, not SELL (which would imply shares sold).
    """
    q = db.query(Transaction).filter(
        Transaction.type == TransactionType.SELL.value,
    )
    if import_id:
        q = q.filter(Transaction.import_id == import_id)
    q = _scope_tx_query(q, user_id)

    issues = []
    for tx in q.all():
        if _RIGHTS_PATTERNS.search(tx.name):
            # Auto-fix: reclassify as DIVIDEND
            tx.type = TransactionType.DIVIDEND.value
            old_qty = tx.quantity
            tx.quantity = Decimal("0")

            issue = DataIssue(
                import_id=import_id,
                issue_type="rights_as_sell",
                severity="warning",
                isin=tx.isin,
                name=tx.name,
                description=(
                    f"SELL '{tx.name}' reclasificada como DIVIDEND (derechos vendidos por efectivo, "
                    f"no acciones). qty {old_qty} → 0, importe {tx.net_amount_eur}€"
                ),
                status="auto_resolved",
                auto_resolution="Reclasificada SELL → DIVIDEND con qty=0",
                resolution_data=json.dumps({
                    "tx_id": tx.id,
                    "old_type": "SELL",
                    "new_type": "DIVIDEND",
                    "old_qty": str(old_qty),
                    "amount": str(tx.net_amount_eur),
                    "recalculate_from_year": tx.trade_date.year,
                }),
            )
            issues.append(issue)
            logger.info("Auto-fixed: rights SELL → DIVIDEND for tx %d (%s)", tx.id, tx.name)

    return issues


# ---------------------------------------------------------------------------
# Check 2: Missing buy transactions
# ---------------------------------------------------------------------------

def _check_missing_buys(db: Session, import_id: int | None, user_id: int | None = None) -> list[DataIssue]:
    """Detect ISINs that have dividends/holdings but no BUY transaction.

    This means the buy happened outside imported data — user needs to provide it.
    """
    # Get all ISINs with dividends
    dividend_q = db.query(Transaction.isin).filter(
        Transaction.type == TransactionType.DIVIDEND.value,
        Transaction.isin.isnot(None),
        Transaction.isin != "",
    )
    dividend_q = _scope_tx_query(dividend_q, user_id)
    dividend_isins = {row[0] for row in dividend_q.distinct().all()}

    # Get all ISINs with holdings
    holdings_isin_q = _scope_holding_query(db.query(PortfolioHolding.isin), user_id)
    holding_isins = {row[0] for row in holdings_isin_q.distinct().all()}

    # Get all ISINs with BUY transactions for active stocks (exclude derivatives)
    buy_q = db.query(Transaction.isin).filter(
        Transaction.type.in_(_ACQUISITION_TYPES),
        Transaction.isin.isnot(None),
        ~Transaction.name.like("[OPT]%"),
        ~Transaction.name.like("[FX]%"),
    )
    buy_q = _scope_tx_query(buy_q, user_id)
    buy_isins = {row[0] for row in buy_q.distinct().all()}

    # ISINs with dividends or holdings but no BUY
    missing = (dividend_isins | holding_isins) - buy_isins
    # Exclude empty/None ISINs
    missing = {isin for isin in missing if isin}

    # Name, dividend count and holding count were four queries per ISIN inside
    # this loop; they are four queries in total now.
    ordered = sorted(missing)
    names = _names_for_isins(db, ordered, user_id)
    div_counts = _counts_by_isin(
        db.query(Transaction.isin, func.count())
        .filter(Transaction.isin.in_(ordered), Transaction.type == TransactionType.DIVIDEND.value)
        .group_by(Transaction.isin),
        _scope_tx_query,
        user_id,
    )
    hold_counts = _counts_by_isin(
        db.query(PortfolioHolding.isin, func.count())
        .filter(PortfolioHolding.isin.in_(ordered))
        .group_by(PortfolioHolding.isin),
        _scope_holding_query,
        user_id,
    )

    issues = []
    for isin in ordered:
        name = names.get(isin, isin)
        div_count = div_counts.get(isin, 0)
        hold_count = hold_counts.get(isin, 0)

        issue = DataIssue(
            import_id=import_id,
            issue_type="missing_buy",
            severity="warning",
            isin=isin,
            name=name,
            description=(
                f"ISIN {isin} ({name}) tiene {div_count} dividendo(s) y {hold_count} "
                f"holding(s) pero ninguna transacción de COMPRA. "
                f"Puede que la compra se hiciera en otro broker o antes de los datos importados."
            ),
            status="needs_input",
        )
        issues.append(issue)

    return issues


# ---------------------------------------------------------------------------
# Check 3: Portfolio holdings vs calculated qty mismatch
# ---------------------------------------------------------------------------

def _check_holdings_mismatch(db: Session, import_id: int | None, user_id: int | None = None) -> list[DataIssue]:
    """Compare portfolio holdings qty with net qty from transactions.

    If a holding says 100 shares but transactions show net 80,
    something is missing (BUY, split, scrip, etc.).

    Scoped to each account's own latest fiscal_year so that ISINs no longer
    held (Twitter 2021, AENA pre-split, etc.) don't generate false positives.
    """
    # Latest fiscal_year per account
    max_fy_by_acct: dict[int, int] = {}
    holdings_q = db.query(PortfolioHolding)
    holdings_q = _scope_holding_query(holdings_q, user_id)
    all_holdings = holdings_q.all()
    for h in all_holdings:
        if h.account_id not in max_fy_by_acct or h.fiscal_year > max_fy_by_acct[h.account_id]:
            max_fy_by_acct[h.account_id] = h.fiscal_year

    # Keep only holdings from each account's latest year
    latest_holdings = [
        h for h in all_holdings
        if h.fiscal_year == max_fy_by_acct.get(h.account_id) and h.quantity > 0
    ]

    # Two sums per holding used to be two queries per holding, on every run.
    # The snapshot cut-off only varies by the account's latest fiscal year, so
    # one grouped query per distinct year covers every holding in it — in
    # practice one query for the whole check.
    net_by_key = _net_quantities_at_year_end(db, latest_holdings)

    issues = []
    for holding in sorted(latest_holdings, key=lambda h: (h.account_id, h.isin)):
        isin = holding.isin
        # Sums are scoped to this holding's account AND to trade_date ≤ snap
        # year-end, so cross-broker positions and post-snapshot activity don't
        # trigger false positives.
        net_qty = net_by_key.get((holding.account_id, isin, holding.fiscal_year), Decimal("0"))
        expected_qty = holding.quantity

        # Allow small floating point tolerance
        if abs(net_qty - expected_qty) > Decimal("0.01"):
            diff = expected_qty - net_qty
            severity = "warning" if abs(diff) / max(expected_qty, Decimal("1")) > Decimal("0.1") else "info"

            issue = DataIssue(
                import_id=import_id,
                issue_type="holdings_mismatch",
                severity=severity,
                isin=isin,
                name=holding.name,
                description=(
                    f"Holdings de {holding.name} ({isin}) en cuenta {holding.account_id}: "
                    f"broker reporta {expected_qty} uds a cierre {holding.fiscal_year}, "
                    f"pero transacciones dan {net_qty} (diferencia: {diff:+}). "
                    f"Posible split, scrip dividend, o transacción faltante."
                ),
                status="needs_input",
                resolution_data=json.dumps({
                    "account_id": holding.account_id,
                    "expected_qty": str(expected_qty),
                    "calculated_qty": str(net_qty),
                    "difference": str(diff),
                    "fiscal_year": holding.fiscal_year,
                }),
            )
            issues.append(issue)

    return issues


# ---------------------------------------------------------------------------
# Check 4: Missing Yahoo Finance ticker
# ---------------------------------------------------------------------------

def _check_missing_ticker(
    db: Session,
    import_id: int | None,
    user_id: int | None = None,
    budget: Budget | None = None,
) -> list[DataIssue]:
    """Detect ISINs not in the Yahoo Finance ticker map.

    These will show "—" for current price in the UI.
    Auto-resolution: try yfinance search, and persist the answer so the price
    layer can use it and the next import does not repeat the lookup.
    """
    from backend.services import ticker_map

    known = ticker_map.effective_map(db)

    # Get all active ISINs (have holdings or open buy positions)
    active_isins = set()

    # From holdings
    holding_isin_q = _scope_holding_query(db.query(PortfolioHolding.isin), user_id)
    for row in holding_isin_q.distinct().all():
        active_isins.add(row[0])

    # From BUY transactions with no matching sell (open positions)
    buy_q = db.query(Transaction.isin).filter(
        Transaction.type.in_(_ACQUISITION_TYPES),
        Transaction.isin.isnot(None),
    )
    buy_q = _scope_tx_query(buy_q, user_id)
    buy_isins = {row[0] for row in buy_q.distinct().all()}
    # ISINs with buys but possibly still open
    active_isins |= buy_isins

    unresolved = sorted(i for i in active_isins if i and i not in known)
    names = _names_for_isins(db, unresolved, user_id)

    missing = []
    for isin in unresolved:
        # Skip derivatives and bonds — they don't have stock tickers
        name = names.get(isin, isin)
        if _DERIVATIVE_PATTERNS.search(name) or _BOND_PATTERNS.search(name):
            continue

        # Try to auto-resolve via yfinance. `name` is already in hand from the
        # derivative check above — it used to be re-queried three more times
        # per ISIN to build these two issues.
        # A spent budget degrades to the same outcome an unresolvable ISIN
        # already produces: flagged needs_input, retried on the next import.
        ticker = None if (budget is not None and budget.spent()) else _try_resolve_ticker(isin)
        if ticker:
            ticker_map.remember(db, isin, ticker, name=name)
            known[isin] = ticker
            issue = DataIssue(
                import_id=import_id,
                issue_type="missing_ticker",
                severity="info",
                isin=isin,
                name=name,
                description=(
                    f"ISIN {isin} no estaba en el mapa de tickers. "
                    f"Resuelto automáticamente: {ticker}"
                ),
                status="auto_resolved",
                auto_resolution=f"Ticker {ticker} encontrado vía yfinance",
                resolution_data=json.dumps({"isin": isin, "ticker": ticker}),
            )
            missing.append(issue)
        else:
            issue = DataIssue(
                import_id=import_id,
                issue_type="missing_ticker",
                severity="warning",
                isin=isin,
                name=name,
                description=(
                    f"ISIN {isin} ({name}) no tiene ticker de Yahoo Finance. "
                    f"Los precios actuales no se mostrarán en la UI."
                ),
                status="needs_input",
            )
            missing.append(issue)

    return missing


# ---------------------------------------------------------------------------
# Check 5: Stock split candidates
# ---------------------------------------------------------------------------

def _check_split_candidates(
    db: Session,
    import_id: int | None,
    user_id: int | None = None,
    budget: Budget | None = None,
) -> list[DataIssue]:
    """Detect and auto-resolve stock splits using yfinance history.

    Strategy:
    - If the same ticker maps to multiple ISINs → ISIN-change split; data is
      already separated by ISIN and correct, auto-resolve.
    - If qty mismatch on a single ISIN matches the split ratio → auto-adjust
      transaction quantities and mark as auto_resolved.
    - Otherwise flag as needs_input for manual review.
    """
    from backend.services import split_history, ticker_map

    # Every ISIN the installation can resolve, not just the curated ones —
    # this check used to be blind to anything outside the hardcoded map, so a
    # split in a security the supervisor had itself resolved went undetected.
    known = ticker_map.effective_map(db)

    # Build reverse map: ticker → [ISINs]
    ticker_to_isins: dict[str, list[str]] = {}
    for isin, ticker in known.items():
        ticker_to_isins.setdefault(ticker, []).append(isin)

    issues = []
    active_isins = set()
    holding_isin_q = _scope_holding_query(db.query(PortfolioHolding.isin), user_id)
    for row in holding_isin_q.distinct().all():
        if row[0] in known:
            active_isins.add(row[0])

    # One ISIN per ticker drives the check; the rest of a ticker's ISINs are
    # corporate-action siblings handled together below.
    isin_for_ticker: dict[str, str] = {}
    for isin in sorted(active_isins):
        ticker = known.get(isin)
        if ticker and ticker not in isin_for_ticker:
            isin_for_ticker[ticker] = isin

    # Split history for every ticker at once — this was a network call per
    # ticker, uncached, on the import path.
    splits_by_ticker = split_history.prefetch(db, list(isin_for_ticker), budget)

    # Most runs find no split anywhere, so the rest of the prefetching only
    # happens when at least one ticker actually has one.
    tickers_with_splits = {t for t, s in splits_by_ticker.items() if s}
    if not tickers_with_splits:
        return issues

    relevant_isins = sorted(
        {i for t, i in isin_for_ticker.items() if t in tickers_with_splits}
        | {i for t in tickers_with_splits for i in ticker_to_isins.get(t, [])}
    )
    first_buy_by_isin = _first_acquisition_dates(db, relevant_isins, user_id)
    held_qty_by_isin = _held_quantities(db, relevant_isins, user_id)
    names = _names_for_isins(db, relevant_isins, user_id)

    for ticker, isin in isin_for_ticker.items():
        splits = splits_by_ticker.get(ticker) or []
        if not splits:
            continue

        # First buy across all ISINs for this ticker
        all_isins_for_ticker = ticker_to_isins.get(ticker, [isin])
        candidates = [
            first_buy_by_isin[i] for i in all_isins_for_ticker if first_buy_by_isin.get(i)
        ]
        first_buy = min(candidates) if candidates else None
        if not first_buy:
            continue

        for split_date, ratio in splits:
            if split_date <= first_buy:
                continue
            if Decimal("0.9") <= ratio <= Decimal("1.1"):
                continue  # scrip dividend, not a real split

            # ── Case 1: ISIN-change split (same ticker, multiple ISINs) ──────
            # Both old and new ISINs are in our map. Data is already split by
            # ISIN with correct quantities. Just log it as auto_resolved.
            if len(all_isins_for_ticker) > 1:
                # Verify transactions exist on both sides
                old_isins = [i for i in all_isins_for_ticker if i != isin]
                has_old_q = db.query(Transaction).filter(
                    Transaction.isin.in_(old_isins),
                    Transaction.type.in_(_ACQUISITION_TYPES),
                    Transaction.trade_date < split_date,
                )
                has_old = _scope_tx_query(has_old_q, user_id).first() is not None
                if has_old:
                    issue = DataIssue(
                        import_id=import_id,
                        issue_type="potential_split",
                        severity="info",
                        isin=isin,
                        name=names.get(isin, isin),
                        description=(
                            f"Split de {ticker} (ratio {ratio}, {split_date.isoformat()}) "
                            f"detectado y gestionado: ISINs separados antes/después del split. "
                            f"Los datos son correctos."
                        ),
                        status="auto_resolved",
                        auto_resolution="Split por cambio de ISIN detectado automáticamente. No requiere acción.",
                        resolution_data=json.dumps({
                            "ticker": ticker,
                            "split_date": split_date.isoformat(),
                            "ratio": str(ratio),
                            "isins": all_isins_for_ticker,
                        }),
                    )
                    issues.append(issue)
                    continue

            # ── Case 2: Qty-only split (same ISIN, quantities need adjustment) ─
            # Check if existing BUY quantities are pre-split (need × ratio)
            handled_q = db.query(Transaction).filter(
                Transaction.isin == isin,
                Transaction.trade_date == split_date,
                Transaction.type == TransactionType.SELL.value,
            )
            already_handled = _scope_tx_query(handled_q, user_id).first()
            if already_handled:
                continue

            pre_split_q = db.query(func.coalesce(func.sum(Transaction.quantity), 0)).filter(
                Transaction.isin == isin,
                Transaction.type.in_(_ACQUISITION_TYPES),
                Transaction.trade_date < split_date,
            )
            pre_split_qty = _scope_tx_query(pre_split_q, user_id).scalar() or Decimal("0")

            holding_qty = held_qty_by_isin.get(isin, Decimal("0"))

            expected_after_split = pre_split_qty * ratio
            tol = expected_after_split * Decimal("0.05")  # 5% tolerance

            if holding_qty > 0 and abs(holding_qty - expected_after_split) <= tol:
                # Auto-apply: adjust pre-split BUY/SELL quantities
                recalculate_from_year = _apply_qty_split(
                    db, isin, split_date, ratio, user_id
                )
                issue = DataIssue(
                    import_id=import_id,
                    issue_type="potential_split",
                    severity="info",
                    isin=isin,
                    name=names.get(isin, isin),
                    description=(
                        f"Split de {ticker} ({isin}) ratio {ratio} el {split_date.isoformat()} "
                        f"detectado y aplicado automáticamente. "
                        f"Transacciones anteriores al split ajustadas ({pre_split_qty} → {expected_after_split} uds)."
                    ),
                    status="auto_resolved",
                    auto_resolution=f"Cantidades ajustadas automáticamente: ×{ratio} antes del {split_date.isoformat()}.",
                    resolution_data=json.dumps({
                        "ticker": ticker,
                        "split_date": split_date.isoformat(),
                        "ratio": str(ratio),
                        "pre_split_qty": str(pre_split_qty),
                        "post_split_qty": str(expected_after_split),
                        "recalculate_from_year": recalculate_from_year,
                    }),
                )
                issues.append(issue)
                logger.info("Auto-applied split for %s (%s): ratio %s on %s", ticker, isin, ratio, split_date)
            else:
                # Cannot confirm — ask user
                issue = DataIssue(
                    import_id=import_id,
                    issue_type="potential_split",
                    severity="warning",
                    isin=isin,
                    name=names.get(isin, isin),
                    description=(
                        f"Split de {ticker} ({isin}): ratio {ratio} el {split_date.isoformat()}. "
                        f"No se pudo confirmar automáticamente (holdings: {holding_qty}, "
                        f"esperado post-split: {expected_after_split}). Verificación manual necesaria."
                    ),
                    status="needs_input",
                    resolution_data=json.dumps({
                        "ticker": ticker,
                        "split_date": split_date.isoformat(),
                        "ratio": str(ratio),
                        "pre_split_qty": str(pre_split_qty),
                        "holding_qty": str(holding_qty),
                    }),
                )
                issues.append(issue)

    return issues


def _apply_qty_split(
    db: Session,
    isin: str,
    split_date: date,
    ratio: Decimal,
    user_id: int,
) -> int | None:
    """Adjust pre-split BUY/SELL transaction quantities for a qty-only split.

    Cost basis (gross_amount, net_amount_eur) is preserved — only quantity
    and unit price are adjusted: qty × ratio, price / ratio.
    Rows with price = 0 (scrip/free shares) keep price = 0.
    """
    affected_q = db.query(Transaction).filter(
        Transaction.account_id.in_(db.query(Account.id).filter(Account.user_id == user_id)),
        Transaction.isin == isin,
        Transaction.trade_date < split_date,
        Transaction.type.in_([*_ACQUISITION_TYPES, TransactionType.SELL.value]),
    )
    earliest_date = db.query(func.min(Transaction.trade_date)).filter(
        Transaction.id.in_(affected_q.with_entities(Transaction.id))
    ).scalar()
    affected_q.update(
        {
            "quantity": Transaction.quantity * ratio,
            "price": case(
                (Transaction.price != 0, Transaction.price / ratio),
                else_=Transaction.price,
            ),
        },
        synchronize_session=False,
    )
    db.flush()
    return earliest_date.year if earliest_date is not None else None


# ---------------------------------------------------------------------------
# Check 6: Price sanity
# ---------------------------------------------------------------------------

def _check_price_sanity(db: Session, import_id: int | None, user_id: int | None = None) -> list[DataIssue]:
    """Flag transactions with suspicious prices (0 or negative)."""
    q = db.query(Transaction).filter(
        Transaction.type.in_([TransactionType.BUY.value, TransactionType.SELL.value]),
    )
    if import_id:
        q = q.filter(Transaction.import_id == import_id)
    q = _scope_tx_query(q, user_id)
    issues = []
    for tx in q.all():
        if tx.price == 0 and tx.quantity > 0:
            # Skip derivatives/options — they can expire worthless at price 0
            if _DERIVATIVE_PATTERNS.search(tx.name) or _BOND_PATTERNS.search(tx.name):
                continue
            # Skip IBKR-style options [OPT] and FX [FX] entries
            if tx.name.startswith("[OPT]") or tx.name.startswith("[FX]"):
                continue

            # Synthetic split adjustments we insert manually: name includes
            # "(split" — already acknowledged, skip entirely.
            if "(split" in tx.name.lower():
                continue

            # Could be a scrip dividend (free shares) — check name
            if _SCRIP_PATTERNS.search(tx.name):
                # Scrip dividends at €0 are normal and expected; emit as
                # auto_resolved so they don't nag the user.
                issue = DataIssue(
                    import_id=import_id,
                    issue_type="scrip_dividend",
                    severity="info",
                    isin=tx.isin,
                    name=tx.name,
                    description=(
                        f"Scrip dividend: {tx.type} {tx.quantity} uds de {tx.name} "
                        f"a precio {tx.price}€."
                    ),
                    status="auto_resolved",
                    resolution_data=json.dumps({
                        "tx_id": tx.id,
                        "quantity": str(tx.quantity),
                        "trade_date": tx.trade_date.isoformat(),
                    }),
                )
                issues.append(issue)
            else:
                issue = DataIssue(
                    import_id=import_id,
                    issue_type="zero_price",
                    severity="warning",
                    isin=tx.isin,
                    name=tx.name,
                    description=(
                        f"Transacción {tx.type} de {tx.name} ({tx.isin}) con precio "
                        f"{tx.price}€ el {tx.trade_date}. Precio sospechoso."
                    ),
                    status="needs_input",
                    resolution_data=json.dumps({
                        "tx_id": tx.id,
                        "price": str(tx.price),
                    }),
                )
                issues.append(issue)

    return issues


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _net_quantities_at_year_end(
    db: Session, holdings: list[PortfolioHolding]
) -> dict[tuple[int, str, int], Decimal]:
    """Net (acquired − sold) quantity per (account, ISIN, fiscal year) cut-off.

    Keyed by fiscal year because the cut-off is that year's 31 December, and
    grouped one query per distinct year — a portfolio normally has exactly one
    latest year, so this is one query where it used to be two per holding.
    """
    if not holdings:
        return {}

    by_year: dict[int, tuple[set[int], set[str]]] = {}
    for h in holdings:
        accounts, isins = by_year.setdefault(h.fiscal_year, (set(), set()))
        accounts.add(h.account_id)
        isins.add(h.isin)

    out: dict[tuple[int, str, int], Decimal] = {}
    for fiscal_year, (accounts, isins) in by_year.items():
        rows = (
            db.query(
                Transaction.account_id,
                Transaction.isin,
                func.coalesce(
                    func.sum(
                        case(
                            (Transaction.type.in_(_ACQUISITION_TYPES), Transaction.quantity),
                            (Transaction.type == TransactionType.SELL.value, -Transaction.quantity),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .filter(
                Transaction.account_id.in_(accounts),
                Transaction.isin.in_(isins),
                Transaction.trade_date <= date(fiscal_year, 12, 31),
                Transaction.type.in_([*_ACQUISITION_TYPES, TransactionType.SELL.value]),
            )
            .group_by(Transaction.account_id, Transaction.isin)
            .all()
        )
        for account_id, isin, net in rows:
            out[(account_id, isin, fiscal_year)] = Decimal(str(net or 0))
    return out


def _counts_by_isin(query, scope, user_id: int | None) -> dict[str, int]:
    """Run a `(isin, count)` grouped query through the caller's scoping helper."""
    return dict(scope(query, user_id).all())


def _names_for_isins(
    db: Session, isins: list[str], user_id: int | None = None
) -> dict[str, str]:
    """Display name per ISIN, in two queries rather than two per ISIN.

    A transaction name wins, a holding name is the fallback, the ISIN itself is
    the last resort. Every check that builds issues for a set of ISINs needs
    this, and each was resolving it one row at a time inside its loop.
    """
    if not isins:
        return {}

    names: dict[str, str] = {}
    holding_q = db.query(PortfolioHolding.isin, PortfolioHolding.name).filter(
        PortfolioHolding.isin.in_(isins), PortfolioHolding.name != ""
    )
    for isin, name in _scope_holding_query(holding_q, user_id).all():
        names.setdefault(isin, name)

    # Transactions win, so they are applied last.
    tx_q = db.query(Transaction.isin, Transaction.name).filter(
        Transaction.isin.in_(isins), Transaction.name != ""
    )
    names.update(_scope_tx_query(tx_q, user_id).all())

    return {isin: names.get(isin) or isin for isin in isins}


def _first_acquisition_dates(
    db: Session, isins: list[str], user_id: int | None = None
) -> dict[str, date]:
    """Earliest acquisition date per ISIN, in one grouped query."""
    if not isins:
        return {}
    q = (
        db.query(Transaction.isin, func.min(Transaction.trade_date))
        .filter(Transaction.isin.in_(isins), Transaction.type.in_(_ACQUISITION_TYPES))
        .group_by(Transaction.isin)
    )
    return {isin: first for isin, first in _scope_tx_query(q, user_id).all() if first}


def _held_quantities(
    db: Session, isins: list[str], user_id: int | None = None
) -> dict[str, Decimal]:
    """Total held quantity per ISIN across holdings, in one grouped query."""
    if not isins:
        return {}
    q = (
        db.query(PortfolioHolding.isin, func.coalesce(func.sum(PortfolioHolding.quantity), 0))
        .filter(PortfolioHolding.isin.in_(isins))
        .group_by(PortfolioHolding.isin)
    )
    return {
        isin: Decimal(str(qty or 0)) for isin, qty in _scope_holding_query(q, user_id).all()
    }




def _try_resolve_ticker(isin: str) -> str | None:
    """Try to find a Yahoo Finance ticker for an ISIN (see ticker_map.lookup)."""
    from backend.services import ticker_map

    return ticker_map.lookup(isin)


