"""Clean up stale supervisor warnings in Neon.

- Delete Pescanova (ES0169350016) and Twitter (US90184L1026) holdings and txs
  (user confirmed: old positions from years ago, remove entirely).
- Purge all status='needs_input' DataIssue rows (they'll be regenerated fresh
  by the next supervisor run with the new per-account, date-scoped check).

Idempotent. Run:
  FINVIEW_DATABASE_URL='postgresql://...' .venv/bin/python scripts/cleanup_stale_issues.py
"""

from backend.database import SessionLocal
from backend.models import DataIssue, PortfolioHolding, Transaction


DELIST_ISINS = ["ES0169350016", "US90184L1026"]  # Pescanova, Twitter


def main() -> None:
    db = SessionLocal()
    try:
        holdings = db.query(PortfolioHolding).filter(
            PortfolioHolding.isin.in_(DELIST_ISINS),
        ).all()
        for h in holdings:
            print(f"  DEL holding: {h.isin} acct={h.account_id} fy={h.fiscal_year} qty={h.quantity}")
            db.delete(h)

        txs = db.query(Transaction).filter(Transaction.isin.in_(DELIST_ISINS)).all()
        for t in txs:
            print(f"  DEL tx: {t.isin} acct={t.account_id} {t.type} {t.trade_date} qty={t.quantity}")
            db.delete(t)

        stale = db.query(DataIssue).filter(DataIssue.status == "needs_input").all()
        for i in stale:
            db.delete(i)
        print(f"\nPurged {len(stale)} stale needs_input issues")

        db.commit()
        print(f"Done: holdings={len(holdings)}, txs={len(txs)}, issues={len(stale)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
