"""Apply data corrections for resolved DataIssues."""

import json
import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

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
from backend.services.fifo_engine import recalculate_fifo_from_year
from backend.services.transaction_amounts import trade_net_amount

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_Q = Decimal("0.000001")


def _issue_owner(db: Session, issue: DataIssue) -> tuple[int | None, int]:
    """Return the trusted account (when known) and user for an issue."""
    if issue.import_id is None:
        if issue.user_id is None:
            raise ValueError("Issue has no owning user")
        return None, issue.user_id

    owner_row = (
        db.query(ImportRecord.account_id, Account.user_id)
        .join(Account, ImportRecord.account_id == Account.id)
        .filter(ImportRecord.id == issue.import_id)
        .one_or_none()
    )
    if owner_row is None:
        raise ValueError(f"ImportRecord {issue.import_id} not found")
    account_id, user_id = owner_row
    if user_id is None:
        raise ValueError(f"ImportRecord {issue.import_id} has no owning user")
    if issue.user_id is not None and issue.user_id != user_id:
        raise ValueError(f"Issue {issue.id} owner does not match its import")
    return account_id, user_id


def resolve_zero_price(db: Session, issue: DataIssue, price_per_share: Decimal) -> None:
    """Set a missing per-share acquisition price and refresh dependent FIFO."""
    if not price_per_share.is_finite() or price_per_share <= _ZERO:
        raise ValueError("El precio por acción debe ser un número finito mayor que cero")
    _, user_id = _issue_owner(db, issue)
    lock_fifo_recalculation(db, user_id)
    data = json.loads(issue.resolution_data or "{}")
    tx_id = data.get("tx_id")
    if not tx_id:
        raise ValueError("resolution_data missing tx_id")

    tx = (
        db.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(Transaction.id == int(tx_id), Account.user_id == user_id)
        .first()
    )
    if not tx:
        raise ValueError(f"Transaction {tx_id} not found")

    normalized_type = tx.type.value if hasattr(tx.type, "value") else tx.type
    allowed_types = {
        "zero_price": {TransactionType.BUY.value, TransactionType.SELL.value},
        "missing_cost_basis": {TransactionType.SPINOFF.value},
    }
    if issue.issue_type not in allowed_types or normalized_type not in allowed_types[issue.issue_type]:
        raise ValueError(
            f"La incidencia {issue.issue_type} no permite fijar precio en una transacción {normalized_type}"
        )

    tx.price = price_per_share
    tx.gross_amount = (price_per_share * abs(tx.quantity)).quantize(_Q, ROUND_HALF_UP)
    tx.net_amount_eur = trade_net_amount(
        normalized_type,
        tx.gross_amount,
        abs(tx.fees or _ZERO),
        abs(tx.withholding_tax or _ZERO),
    ).quantize(_Q, ROUND_HALF_UP)

    issue.status = "resolved"
    issue.resolution_data = json.dumps({**data, "applied_price": str(price_per_share)})
    recalculate_fifo_from_year(db, tx.trade_date.year, user_id)
    logger.info("Resolved zero_price issue %d: tx %d price → %s", issue.id, tx_id, price_per_share)


def resolve_add_buy(
    db: Session,
    issue: DataIssue,
    qty: Decimal,
    price: Decimal,
    acquisition_date: date,
) -> None:
    """Create a synthetic BUY transaction for a missing acquisition."""
    if issue.issue_type not in {"missing_buy", "holdings_mismatch"}:
        raise ValueError(f"La incidencia {issue.issue_type} no permite crear una compra")
    if not qty.is_finite() or qty <= _ZERO:
        raise ValueError("La cantidad debe ser un número finito mayor que cero")
    if not price.is_finite() or price <= _ZERO:
        raise ValueError("El precio debe ser un número finito mayor que cero")
    account_id, user_id = _issue_owner(db, issue)
    lock_fifo_recalculation(db, user_id)
    if account_id is None:
        tx_accounts = (
            db.query(Transaction.account_id)
            .join(Account, Transaction.account_id == Account.id)
            .filter(Transaction.isin == issue.isin, Account.user_id == user_id)
            .distinct()
            .all()
        )
        holding_accounts = (
            db.query(PortfolioHolding.account_id)
            .join(Account, PortfolioHolding.account_id == Account.id)
            .filter(PortfolioHolding.isin == issue.isin, Account.user_id == user_id)
            .distinct()
            .all()
        )
        candidates = {row[0] for row in tx_accounts + holding_accounts}
        if len(candidates) != 1:
            raise ValueError("La incidencia no identifica una única cuenta para la compra")
        account_id = candidates.pop()

    gross = (qty * price).quantize(_Q, ROUND_HALF_UP)
    tx = Transaction(
        account_id=account_id,
        import_id=issue.import_id,
        type=TransactionType.BUY.value,
        trade_date=acquisition_date,
        isin=issue.isin,
        name=issue.name,
        quantity=qty,
        price=price,
        currency="EUR",
        exchange_rate=Decimal("1"),
        gross_amount=gross,
        fees=_ZERO,
        withholding_tax=_ZERO,
        net_amount_eur=gross,
    )
    db.add(tx)
    db.flush()

    issue.status = "resolved"
    issue.resolution_data = json.dumps({
        "created_tx_id": tx.id,
        "qty": str(qty),
        "price": str(price),
        "acquisition_date": acquisition_date.isoformat(),
        "account_id": account_id,
    })
    recalculate_fifo_from_year(db, acquisition_date.year, user_id)
    logger.info(
        "Resolved missing_buy issue %d: created BUY tx %d (%s × %s on %s)",
        issue.id, tx.id, qty, price, acquisition_date,
    )


def resolve_apply_split(db: Session, issue: DataIssue) -> None:
    """Adjust pre-split quantities and prices for a detected stock split."""
    if issue.issue_type != "potential_split":
        raise ValueError(f"La incidencia {issue.issue_type} no permite aplicar un split")
    _, user_id = _issue_owner(db, issue)
    lock_fifo_recalculation(db, user_id)
    data = json.loads(issue.resolution_data or "{}")
    split_date_str = data.get("split_date")
    ratio_str = data.get("ratio")

    if not split_date_str or not ratio_str:
        raise ValueError("resolution_data missing split_date or ratio")

    split_date = date.fromisoformat(split_date_str)
    ratio = Decimal(ratio_str)
    if not ratio.is_finite() or ratio <= _ZERO:
        raise ValueError("El ratio del split debe ser un número finito mayor que cero")

    txs = (
        db.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Account.user_id == user_id,
            Transaction.isin == issue.isin,
            Transaction.type.in_([TransactionType.BUY.value, TransactionType.SELL.value]),
            Transaction.trade_date < split_date,
        )
        .all()
    )

    for tx in txs:
        tx.quantity = (tx.quantity * ratio).quantize(_Q, ROUND_HALF_UP)
        if tx.price > _ZERO:
            tx.price = (tx.price / ratio).quantize(_Q, ROUND_HALF_UP)
        # gross_amount and net_amount_eur represent total cost — they stay the same

    issue.status = "resolved"
    issue.resolution_data = json.dumps({**data, "transactions_adjusted": len(txs)})
    logger.info(
        "Resolved potential_split issue %d: ratio %s on %s, adjusted %d txs",
        issue.id, ratio, split_date, len(txs),
    )
    if txs:
        recalculate_fifo_from_year(db, min(tx.trade_date.year for tx in txs), user_id)
