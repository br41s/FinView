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

logger = logging.getLogger(__name__)


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
    issues: list[DataIssue] = []

    issues.extend(_check_rights_as_sells(db, import_id, user_id))
    issues.extend(_check_missing_buys(db, import_id, user_id))
    issues.extend(_check_holdings_mismatch(db, import_id, user_id))
    issues.extend(_check_missing_ticker(db, import_id, user_id))
    issues.extend(_check_split_candidates(db, import_id, user_id))
    issues.extend(_check_price_sanity(db, import_id, user_id))

    # Persist issues, deduplicating against existing needs_input rows so
    # repeated supervisor runs don't create 5× copies of the same warning.
    existing_needs_input = {
        (row.issue_type, row.isin)
        for row in db.query(DataIssue.issue_type, DataIssue.isin)
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
        if issue.status == "needs_input" and (issue.issue_type, issue.isin) in existing_needs_input:
            continue
        issue.user_id = user_id
        db.add(issue)
        persisted.append(issue)
        if issue.status == "needs_input":
            existing_needs_input.add((issue.issue_type, issue.isin))
    db.flush()

    logger.info(
        "Data supervisor: %d issues found, %d persisted (import_id=%s)",
        len(issues),
        len(persisted),
        import_id,
    )
    return persisted


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
    dividend_isins = set(
        row[0]
        for row in dividend_q.distinct().all()
    )

    # Get all ISINs with holdings
    holdings_isin_q = _scope_holding_query(db.query(PortfolioHolding.isin), user_id)
    holding_isins = set(
        row[0]
        for row in holdings_isin_q.distinct().all()
    )

    # Get all ISINs with BUY transactions for active stocks (exclude derivatives)
    buy_q = db.query(Transaction.isin).filter(
        Transaction.type == TransactionType.BUY.value,
        Transaction.isin.isnot(None),
        ~Transaction.name.like("[OPT]%"),
        ~Transaction.name.like("[FX]%"),
    )
    buy_q = _scope_tx_query(buy_q, user_id)
    buy_isins = set(
        row[0]
        for row in buy_q.distinct().all()
    )

    # ISINs with dividends or holdings but no BUY
    missing = (dividend_isins | holding_isins) - buy_isins
    # Exclude empty/None ISINs
    missing = {isin for isin in missing if isin}

    issues = []
    for isin in sorted(missing):
        # Get a representative name
        name_q = db.query(Transaction.name).filter(
            Transaction.isin == isin,
            Transaction.name != "",
        )
        name_row = _scope_tx_query(name_q, user_id).first()
        if not name_row:
            holding_name_q = db.query(PortfolioHolding.name).filter(PortfolioHolding.isin == isin)
            name_row = _scope_holding_query(holding_name_q, user_id).first()
        name = name_row[0] if name_row else isin

        div_count_q = db.query(func.count()).select_from(Transaction).filter(
            Transaction.isin == isin,
            Transaction.type == TransactionType.DIVIDEND.value,
        )
        div_count = _scope_tx_query(div_count_q, user_id).scalar()
        hold_count_q = db.query(func.count()).select_from(PortfolioHolding).filter(
            PortfolioHolding.isin == isin
        )
        hold_count = _scope_holding_query(hold_count_q, user_id).scalar()

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

    issues = []
    for holding in sorted(latest_holdings, key=lambda h: (h.account_id, h.isin)):
        isin = holding.isin
        snap_end = date(holding.fiscal_year, 12, 31)
        # Scope tx sums to this holding's account AND to trade_date ≤ snap year-end,
        # so cross-broker positions and post-snapshot activity don't trigger
        # false positives.
        buys = (
            db.query(func.coalesce(func.sum(Transaction.quantity), 0))
            .filter(
                Transaction.account_id == holding.account_id,
                Transaction.isin == isin,
                Transaction.type == TransactionType.BUY.value,
                Transaction.trade_date <= snap_end,
            )
            .scalar()
        ) or Decimal("0")

        sells = (
            db.query(func.coalesce(func.sum(Transaction.quantity), 0))
            .filter(
                Transaction.account_id == holding.account_id,
                Transaction.isin == isin,
                Transaction.type == TransactionType.SELL.value,
                Transaction.trade_date <= snap_end,
            )
            .scalar()
        ) or Decimal("0")

        net_qty = buys - sells
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

def _check_missing_ticker(db: Session, import_id: int | None, user_id: int | None = None) -> list[DataIssue]:
    """Detect ISINs not in the Yahoo Finance ticker map.

    These will show "—" for current price in the UI.
    Auto-resolution: try yfinance search.
    """
    from backend.services.prices import _ISIN_TICKER_MAP

    # Get all active ISINs (have holdings or open buy positions)
    active_isins = set()

    # From holdings
    holding_isin_q = _scope_holding_query(db.query(PortfolioHolding.isin), user_id)
    for row in holding_isin_q.distinct().all():
        active_isins.add(row[0])

    # From BUY transactions with no matching sell (open positions)
    buy_q = db.query(Transaction.isin).filter(
        Transaction.type == TransactionType.BUY.value,
        Transaction.isin.isnot(None),
    )
    buy_q = _scope_tx_query(buy_q, user_id)
    buy_isins = set(
        row[0]
        for row in buy_q.distinct().all()
    )
    # ISINs with buys but possibly still open
    active_isins |= buy_isins

    missing = []
    for isin in sorted(active_isins):
        if not isin or isin in _ISIN_TICKER_MAP:
            continue

        # Skip derivatives and bonds — they don't have stock tickers
        name = _get_name_for_isin(db, isin, user_id)
        if _DERIVATIVE_PATTERNS.search(name) or _BOND_PATTERNS.search(name):
            continue

        # Try to auto-resolve via yfinance
        ticker = _try_resolve_ticker(isin)
        if ticker:
            issue = DataIssue(
                import_id=import_id,
                issue_type="missing_ticker",
                severity="info",
                isin=isin,
                name=_get_name_for_isin(db, isin, user_id),
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
                name=_get_name_for_isin(db, isin, user_id),
                description=(
                    f"ISIN {isin} ({_get_name_for_isin(db, isin, user_id)}) no tiene ticker de Yahoo Finance. "
                    f"Los precios actuales no se mostrarán en la UI."
                ),
                status="needs_input",
            )
            missing.append(issue)

    return missing


# ---------------------------------------------------------------------------
# Check 5: Stock split candidates
# ---------------------------------------------------------------------------

def _check_split_candidates(db: Session, import_id: int | None, user_id: int | None = None) -> list[DataIssue]:
    """Detect and auto-resolve stock splits using yfinance history.

    Strategy:
    - If the same ticker maps to multiple ISINs → ISIN-change split; data is
      already separated by ISIN and correct, auto-resolve.
    - If qty mismatch on a single ISIN matches the split ratio → auto-adjust
      transaction quantities and mark as auto_resolved.
    - Otherwise flag as needs_input for manual review.
    """
    from backend.services.prices import _ISIN_TICKER_MAP

    # Build reverse map: ticker → [ISINs]
    ticker_to_isins: dict[str, list[str]] = {}
    for isin, ticker in _ISIN_TICKER_MAP.items():
        ticker_to_isins.setdefault(ticker, []).append(isin)

    issues = []
    active_isins = set()
    holding_isin_q = _scope_holding_query(db.query(PortfolioHolding.isin), user_id)
    for row in holding_isin_q.distinct().all():
        if row[0] in _ISIN_TICKER_MAP:
            active_isins.add(row[0])

    processed_tickers: set[str] = set()

    for isin in sorted(active_isins):
        ticker = _ISIN_TICKER_MAP.get(isin)
        if not ticker or ticker in processed_tickers:
            continue
        processed_tickers.add(ticker)

        splits = _get_splits_from_yfinance(ticker)
        if not splits:
            continue

        # First buy across all ISINs for this ticker
        all_isins_for_ticker = ticker_to_isins.get(ticker, [isin])
        first_buy_q = db.query(func.min(Transaction.trade_date)).filter(
            Transaction.isin.in_(all_isins_for_ticker),
            Transaction.type == TransactionType.BUY.value,
        )
        first_buy = _scope_tx_query(first_buy_q, user_id).scalar()
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
                    Transaction.type == TransactionType.BUY.value,
                    Transaction.trade_date < split_date,
                )
                has_old = _scope_tx_query(has_old_q, user_id).first() is not None
                if has_old:
                    issue = DataIssue(
                        import_id=import_id,
                        issue_type="potential_split",
                        severity="info",
                        isin=isin,
                        name=_get_name_for_isin(db, isin, user_id),
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
                Transaction.type == TransactionType.BUY.value,
                Transaction.trade_date < split_date,
            )
            pre_split_qty = _scope_tx_query(pre_split_q, user_id).scalar() or Decimal("0")

            holding_qty_q = db.query(
                func.coalesce(func.sum(PortfolioHolding.quantity), 0)
            ).filter(PortfolioHolding.isin == isin)
            holding_qty = (
                _scope_holding_query(holding_qty_q, user_id).scalar()
            ) or Decimal("0")

            expected_after_split = pre_split_qty * ratio
            tol = expected_after_split * Decimal("0.05")  # 5% tolerance

            if holding_qty > 0 and abs(holding_qty - expected_after_split) <= tol:
                # Auto-apply: adjust pre-split BUY/SELL quantities
                _apply_qty_split(db, isin, split_date, ratio, user_id)
                issue = DataIssue(
                    import_id=import_id,
                    issue_type="potential_split",
                    severity="info",
                    isin=isin,
                    name=_get_name_for_isin(db, isin, user_id),
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
                    name=_get_name_for_isin(db, isin, user_id),
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
) -> None:
    """Adjust pre-split BUY/SELL transaction quantities for a qty-only split.

    Cost basis (gross_amount, net_amount_eur) is preserved — only quantity
    and unit price are adjusted: qty × ratio, price / ratio.
    Rows with price = 0 (scrip/free shares) keep price = 0.
    """
    db.query(Transaction).filter(
        Transaction.account_id.in_(db.query(Account.id).filter(Account.user_id == user_id)),
        Transaction.isin == isin,
        Transaction.trade_date < split_date,
        Transaction.type.in_([TransactionType.BUY.value, TransactionType.SELL.value]),
    ).update(
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

def _get_name_for_isin(db: Session, isin: str, user_id: int | None = None) -> str:
    """Get a human-readable name for an ISIN from existing data."""
    tx_q = db.query(Transaction.name).filter(Transaction.isin == isin, Transaction.name != "")
    row = _scope_tx_query(tx_q, user_id).first()
    if row:
        return row[0]
    holding_q = db.query(PortfolioHolding.name).filter(PortfolioHolding.isin == isin)
    row = _scope_holding_query(holding_q, user_id).first()
    return row[0] if row else isin


def _try_resolve_ticker(isin: str) -> str | None:
    """Try to find a Yahoo Finance ticker for an ISIN."""
    try:
        import yfinance as yf

        stock = yf.Ticker(isin)
        info = stock.info
        if info and info.get("symbol") and info.get("regularMarketPrice"):
            return info["symbol"]
    except Exception:
        pass
    return None


def _get_splits_from_yfinance(ticker: str) -> list[tuple[date, Decimal]]:
    """Get stock split history from yfinance."""
    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        splits = stock.splits
        if splits is not None and not splits.empty:
            result = []
            for dt, ratio in splits.items():
                split_date = dt.date() if hasattr(dt, "date") else dt
                result.append((split_date, Decimal(str(ratio))))
            return result
    except Exception as e:
        logger.debug("Failed to get splits for %s: %s", ticker, e)
    return []
