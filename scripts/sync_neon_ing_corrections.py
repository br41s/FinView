"""Sync user-confirmed ING corrections to prod (Neon).

Previous runs of add_ing_buys.py and manual fixes targeted the local SQLite
DB, not Neon. This script is idempotent and safe to re-run.

Scope:
- Iberdrola: drop 4 stale scrips (38/2/66/32), insert 2269 @ €10.35 on
  2022-11-13 and the 39-share scrip on 2024-07-29.
- Repsol: drop the 3-share scrip (rights were sold to market), insert 100
  @ €7.861 on 2020-07-13, correct snapshots 103 → 100 across all years.
- Santander / Endesa / Amadeus / Inditex: insert real acquisition BUYs.
- Colonial: insert the post-snapshot 2026-01-02 BUY (10 @ €5.697).
- AENA is intentionally skipped (pre/post-split ISIN change handled separately).

Run:
  FINVIEW_DATABASE_URL='postgresql://...' .venv/bin/python scripts/sync_neon_ing_corrections.py
"""

from datetime import date
from decimal import Decimal

from backend.database import SessionLocal
from backend.models import Account, PortfolioHolding, Transaction, TransactionType


ISIN_IBE = "ES0144580Y14"
ISIN_REP = "ES0173516115"
ISIN_AENA_OLD = "ES0105046009"
ISIN_AENA_NEW = "ES0105046017"
AENA_SPLIT_DATE = date(2025, 6, 19)  # 1:10 stock split


# (trade_date, isin, name, qty, price, net_amount)
MISSING_BUYS: list[tuple[date, str, str, Decimal, Decimal, Decimal]] = [
    (date(2022, 11, 13), ISIN_IBE, "Iberdrola", Decimal("2269"), Decimal("10.35"), Decimal("23484.15")),
    (date(2024, 7, 29), ISIN_IBE, "Iberdrola (scrip)", Decimal("39"), Decimal("0"), Decimal("0")),
    (date(2022, 11, 13), "ES0113900J37", "Banco Santander", Decimal("4809"), Decimal("2.528"), Decimal("12154.752")),
    (date(2020, 7, 13), ISIN_REP, "Repsol", Decimal("100"), Decimal("7.861"), Decimal("786.100")),
    (date(2020, 5, 28), "ES0130670112", "Endesa", Decimal("50"), Decimal("21.487"), Decimal("1074.350")),
    (date(2020, 5, 20), "ES0109067019", "Amadeus IT Group", Decimal("50"), Decimal("50.942"), Decimal("2547.100")),
    (date(2020, 3, 24), "ES0148396007", "Inditex", Decimal("100"), Decimal("24.921"), Decimal("2492.100")),
    (date(2026, 1, 2), "ES0139140174", "Colonial SFL SOCIMI SA", Decimal("10"), Decimal("5.697"), Decimal("56.970")),
    # AENA pre-split acquisition (old ISIN, pre-split price €129.50 × 10 = €1295)
    (date(2020, 5, 4), ISIN_AENA_OLD, "AENA SME S.A.", Decimal("10"), Decimal("129.500"), Decimal("1295.000")),
    # AENA split (1:10) on 2025-06-19 — preserve cost basis across ISIN change
    (AENA_SPLIT_DATE, ISIN_AENA_NEW, "AENA SME S.A.", Decimal("100"), Decimal("12.95"), Decimal("1295.000")),
]

ISIN_COUNTRY = {
    ISIN_IBE: "España",
    "ES0113900J37": "España",
    ISIN_REP: "España",
    "ES0130670112": "España",
    "ES0109067019": "España",
    "ES0148396007": "España",
    "ES0139140174": "España",
    ISIN_AENA_OLD: "España",
    ISIN_AENA_NEW: "España",
}


def _delete_stale(db, ing_id: int) -> int:
    """Drop stale scrip BUYs that user has clarified should not exist."""
    deleted = 0
    # Iberdrola: all existing BUYs are stale scrips. Real history is the
    # 2269 real BUY + 39 scrip being inserted below.
    ibe_buys = (
        db.query(Transaction)
        .filter(
            Transaction.account_id == ing_id,
            Transaction.isin == ISIN_IBE,
            Transaction.type == TransactionType.BUY,
        )
        .all()
    )
    for t in ibe_buys:
        print(f"  DEL Iberdrola scrip: {t.trade_date} qty={t.quantity}")
        db.delete(t)
        deleted += 1
    # Repsol: the 3-share scrip (rights should have been sold, not subscribed).
    rep_scrip = (
        db.query(Transaction)
        .filter(
            Transaction.account_id == ing_id,
            Transaction.isin == ISIN_REP,
            Transaction.type == TransactionType.BUY,
            Transaction.quantity == Decimal("3"),
        )
        .all()
    )
    for t in rep_scrip:
        print(f"  DEL Repsol scrip: {t.trade_date} qty={t.quantity}")
        db.delete(t)
        deleted += 1
    return deleted


def _upsert_aena_split(db, ing_id: int) -> int:
    """Insert the AENA 1:10 split as a SELL of old ISIN on split date.

    The BUY side (100 shares on new ISIN) is inserted via MISSING_BUYS.
    Together they zero out the old-ISIN position and transfer the full
    €1295 cost basis to the new ISIN. Idempotent.
    """
    existing = (
        db.query(Transaction)
        .filter(
            Transaction.account_id == ing_id,
            Transaction.isin == ISIN_AENA_OLD,
            Transaction.trade_date == AENA_SPLIT_DATE,
            Transaction.type == TransactionType.SELL,
        )
        .first()
    )
    if existing:
        print("  SKIP AENA split SELL (exists)")
        return 0
    db.add(Transaction(
        account_id=ing_id,
        type=TransactionType.SELL,
        trade_date=AENA_SPLIT_DATE,
        isin=ISIN_AENA_OLD,
        name="AENA SME S.A. (split 1:10)",
        country="España",
        quantity=Decimal("10"),
        price=Decimal("0"),
        currency="EUR",
        exchange_rate=Decimal("1"),
        gross_amount=Decimal("0"),
        fees=Decimal("0"),
        withholding_tax=Decimal("0"),
        net_amount_eur=Decimal("0"),
    ))
    print(f"  ADD: {AENA_SPLIT_DATE} AENA split SELL x10 on old ISIN")
    return 1


def _fix_repsol_snapshots(db, ing_id: int) -> int:
    """Repsol qty should be 100 (rights sold to market), not 103."""
    fixed = 0
    snaps = (
        db.query(PortfolioHolding)
        .filter(
            PortfolioHolding.account_id == ing_id,
            PortfolioHolding.isin == ISIN_REP,
            PortfolioHolding.quantity == Decimal("103"),
        )
        .all()
    )
    for s in snaps:
        print(f"  FIX Repsol snap fy={s.fiscal_year}: 103 → 100")
        s.quantity = Decimal("100")
        fixed += 1
    return fixed


def _upsert_buys(db, ing_id: int) -> tuple[int, int]:
    added = 0
    skipped = 0
    for trade_dt, isin, name, qty, price, net_amount in MISSING_BUYS:
        existing = (
            db.query(Transaction)
            .filter(
                Transaction.account_id == ing_id,
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
        db.add(Transaction(
            account_id=ing_id,
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
        ))
        print(f"  ADD: {trade_dt} {name} x{qty} @ €{price} = €{net_amount}")
        added += 1
    return added, skipped


def main() -> None:
    db = SessionLocal()
    try:
        ing = db.query(Account).filter(Account.broker == "ING").first()
        if not ing:
            print("ERROR: No ING account in DB")
            return
        print(f"Using ING account id={ing.id}")
        print("\n[1/3] Deleting stale scrip BUYs …")
        deleted = _delete_stale(db, ing.id)
        print("\n[2/3] Correcting Repsol snapshots …")
        fixed = _fix_repsol_snapshots(db, ing.id)
        print("\n[3/4] Inserting canonical BUYs …")
        added, skipped = _upsert_buys(db, ing.id)
        print("\n[4/4] Inserting AENA split SELL on old ISIN …")
        split_added = _upsert_aena_split(db, ing.id)
        db.commit()
        print(
            f"\nDone: deleted={deleted}, snaps_fixed={fixed}, "
            f"added={added + split_added}, skipped={skipped}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
