"""Add missing ING buy transactions from broker app screenshots.

These are buy transactions that were not captured by PDF imports because
ING PDFs only contain dividend/settlement info, not buy confirmations.

Data source: User-provided screenshots from ING broker app (2026-04-10).
"""

from datetime import date
from decimal import Decimal

from backend.database import SessionLocal
from backend.models import Account, Transaction, TransactionType


MISSING_BUYS = [
    # (trade_date, isin, name, qty, price, net_amount)
    # Inherited Iberdrola — user-provided cost basis (not from ING app)
    (date(2023, 11, 13), "ES0144580Y14", "Iberdrola", Decimal("2812"), Decimal("5.298"), Decimal("14897.976")),
    # Banco Santander — 13.11.2022
    (date(2022, 11, 13), "ES0113900J37", "Banco Santander", Decimal("4809"), Decimal("2.528"), Decimal("12154.752")),
    # Repsol — 13.07.2020
    (date(2020, 7, 13), "ES0173516115", "Repsol", Decimal("100"), Decimal("7.861"), Decimal("786.100")),
    # Endesa — 28.05.2020
    (date(2020, 5, 28), "ES0130670112", "Endesa", Decimal("50"), Decimal("21.487"), Decimal("1074.350")),
    # Amadeus IT Group — 20.05.2020
    (date(2020, 5, 20), "ES0109067019", "Amadeus IT Group", Decimal("50"), Decimal("50.942"), Decimal("2547.100")),
    # AENA SME S.A. — 04.05.2020
    (date(2020, 5, 4), "ES0105046009", "AENA SME S.A.", Decimal("10"), Decimal("129.500"), Decimal("1295.000")),
    # Inditex — 24.03.2020
    (date(2020, 3, 24), "ES0148396007", "Inditex", Decimal("100"), Decimal("24.921"), Decimal("2492.100")),
    # Colonial SFL — 02.01.2026 (missing from recent imports)
    (date(2026, 1, 2), "ES0139140174", "Colonial SFL SOCIMI SA", Decimal("10"), Decimal("5.697"), Decimal("56.970")),
]

# Country mapping
ISIN_COUNTRY = {
    "ES0144580Y14": "España",
    "ES0113900J37": "España",
    "ES0173516115": "España",
    "ES0130670112": "España",
    "ES0109067019": "España",
    "ES0105046009": "España",
    "ES0148396007": "España",
    "ES0139140174": "España",
}


def main():
    db = SessionLocal()
    try:
        ing_account = db.query(Account).filter(Account.broker == "ING").first()
        if not ing_account:
            print("ERROR: No ING account found in database")
            return

        added = 0
        skipped = 0

        for trade_dt, isin, name, qty, price, net_amount in MISSING_BUYS:
            # Check if already exists (same date, isin, quantity)
            existing = (
                db.query(Transaction)
                .filter(
                    Transaction.account_id == ing_account.id,
                    Transaction.isin == isin,
                    Transaction.trade_date == trade_dt,
                    Transaction.type == TransactionType.BUY,
                    Transaction.quantity == qty,
                )
                .first()
            )
            if existing:
                print(f"  SKIP (exists): {trade_dt} {name} x{qty}")
                skipped += 1
                continue

            tx = Transaction(
                account_id=ing_account.id,
                type=TransactionType.BUY,
                trade_date=trade_dt,
                isin=isin,
                name=name,
                country=ISIN_COUNTRY.get(isin, ""),
                quantity=qty,
                price=price,
                currency="EUR",
                exchange_rate=Decimal("1"),
                gross_amount=net_amount,
                fees=Decimal("0"),
                withholding_tax=Decimal("0"),
                net_amount_eur=net_amount,
            )
            db.add(tx)
            print(f"  ADD: {trade_dt} {name} x{qty} @ €{price} = €{net_amount}")
            added += 1

        db.commit()
        print(f"\nDone: {added} added, {skipped} skipped")
    finally:
        db.close()


if __name__ == "__main__":
    main()
