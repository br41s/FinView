"""Apply data corrections for resolved DataIssues."""

import json
import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from backend.models import DataIssue, ImportRecord, Transaction, TransactionType

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_Q = Decimal("0.000001")


def resolve_zero_price(db: Session, issue: DataIssue, price_per_share: Decimal) -> None:
    """Set the correct price on a zero-price BUY transaction."""
    data = json.loads(issue.resolution_data or "{}")
    tx_id = data.get("tx_id")
    if not tx_id:
        raise ValueError("resolution_data missing tx_id")

    tx = db.query(Transaction).filter(Transaction.id == int(tx_id)).first()
    if not tx:
        raise ValueError(f"Transaction {tx_id} not found")

    tx.price = price_per_share
    tx.gross_amount = (price_per_share * tx.quantity).quantize(_Q, ROUND_HALF_UP)
    rate = tx.exchange_rate or Decimal("1")
    tx.net_amount_eur = (tx.gross_amount * rate + tx.fees).quantize(_Q, ROUND_HALF_UP)

    issue.status = "resolved"
    issue.resolution_data = json.dumps({**data, "applied_price": str(price_per_share)})
    logger.info("Resolved zero_price issue %d: tx %d price → %s", issue.id, tx_id, price_per_share)


def resolve_add_buy(
    db: Session,
    issue: DataIssue,
    qty: Decimal,
    price: Decimal,
    acquisition_date: date,
) -> None:
    """Create a synthetic BUY transaction for a missing acquisition."""
    # Determine account_id: import record → resolution_data → ISIN lookup
    account_id: int | None = None

    if issue.import_id:
        rec = db.query(ImportRecord).filter(ImportRecord.id == issue.import_id).first()
        if rec:
            account_id = rec.account_id

    if account_id is None:
        try:
            stored = json.loads(issue.resolution_data or "{}")
            account_id = stored.get("account_id")
        except Exception:
            pass

    if account_id is None:
        row = db.query(Transaction.account_id).filter(Transaction.isin == issue.isin).first()
        if row:
            account_id = row[0]

    if account_id is None:
        raise ValueError(f"No se puede determinar la cuenta para ISIN {issue.isin}")

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
    logger.info(
        "Resolved missing_buy issue %d: created BUY tx %d (%s × %s on %s)",
        issue.id, tx.id, qty, price, acquisition_date,
    )


def resolve_apply_split(db: Session, issue: DataIssue) -> None:
    """Adjust pre-split quantities and prices for a detected stock split."""
    data = json.loads(issue.resolution_data or "{}")
    split_date_str = data.get("split_date")
    ratio_str = data.get("ratio")

    if not split_date_str or not ratio_str:
        raise ValueError("resolution_data missing split_date or ratio")

    split_date = date.fromisoformat(split_date_str)
    ratio = Decimal(ratio_str)

    txs = (
        db.query(Transaction)
        .filter(
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
