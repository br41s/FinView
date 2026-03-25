"""Debug script to investigate dividend yield calculation issues."""
import sys
sys.path.insert(0, "/Users/brais/VSCODE/FinView")

from backend.database import SessionLocal
from backend.models import Transaction, TaxLot, TransactionType

db = SessionLocal()

# Check a few ISINs of interest
isins_to_check = ["ES0105027009"]  # Logista

for isin in isins_to_check:
    print(f"\n{'='*60}")
    print(f"ISIN: {isin}")
    print(f"{'='*60}")

    # BUY transactions
    buys = (
        db.query(Transaction)
        .filter(Transaction.isin == isin, Transaction.type == TransactionType.BUY.value)
        .order_by(Transaction.trade_date)
        .all()
    )
    print(f"\nBUY transactions ({len(buys)}):")
    total_buy_amount = 0
    total_buy_qty = 0
    for b in buys:
        amt = abs(float(b.net_amount_eur))
        qty = float(b.quantity)
        print(f"  {b.trade_date}  qty={qty:>10.4f}  price={float(b.price):>8.2f}  net={float(b.net_amount_eur):>10.2f}")
        total_buy_amount += amt
        total_buy_qty += qty
    print(f"  TOTAL: qty={total_buy_qty:.4f}, invested={total_buy_amount:.2f}")

    # SELL transactions
    sells = (
        db.query(Transaction)
        .filter(Transaction.isin == isin, Transaction.type == TransactionType.SELL.value)
        .order_by(Transaction.trade_date)
        .all()
    )
    print(f"\nSELL transactions ({len(sells)}):")
    for s in sells:
        print(f"  {s.trade_date}  qty={float(s.quantity):>10.4f}  price={float(s.price):>8.2f}  net={float(s.net_amount_eur):>10.2f}")

    # TaxLots
    lots = db.query(TaxLot).filter(TaxLot.isin == isin).all()
    print(f"\nTaxLots ({len(lots)}):")
    total_cost = 0
    total_remaining = 0
    for l in lots:
        print(f"  buy_tx={l.buy_tx_id}  sell_tx={l.sell_tx_id}  qty_bought={float(l.quantity_bought):>10.4f}  remaining={float(l.quantity_remaining):>10.4f}  cost={float(l.cost_basis_eur):>10.2f}  pl={float(l.realized_pl_eur or 0):>10.2f}")
        total_cost += abs(float(l.cost_basis_eur))
        total_remaining += float(l.quantity_remaining)
    print(f"  TOTAL: cost_basis={total_cost:.2f}, remaining={total_remaining:.6f}")

    # DIVIDEND transactions
    divs = (
        db.query(Transaction)
        .filter(Transaction.isin == isin, Transaction.type == TransactionType.DIVIDEND.value)
        .order_by(Transaction.trade_date)
        .all()
    )
    print(f"\nDIVIDEND transactions ({len(divs)}):")
    for d in divs:
        print(f"  {d.trade_date}  gross={float(d.gross_amount):>10.2f}  wht={float(d.withholding_tax):>8.2f}")

db.close()
