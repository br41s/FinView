"""Canonical net-amount semantics for normalized transactions."""

from decimal import Decimal

from backend.models import TransactionType


def trade_net_amount(
    tx_type: str | TransactionType,
    gross_amount: Decimal,
    fees: Decimal,
    withholding_tax: Decimal = Decimal("0"),
) -> Decimal:
    """Return the cash-adjusted amount before currency conversion.

    Acquisitions capitalize fees into cost. Every other transaction uses the
    cash received after fees and withholding.
    """
    normalized_type = tx_type.value if hasattr(tx_type, "value") else tx_type
    if normalized_type in {
        TransactionType.BUY.value,
        TransactionType.SPINOFF.value,
    }:
        return gross_amount + fees
    return gross_amount - fees - withholding_tax
