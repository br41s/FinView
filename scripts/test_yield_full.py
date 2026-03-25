"""Simulate the full endpoint logic to find the crash."""
import sys
sys.path.insert(0, "/Users/brais/VSCODE/FinView")

from decimal import Decimal
from backend.database import SessionLocal
from backend.models import Transaction, TransactionType
from sqlalchemy import func

db = SessionLocal()

# Step 1: dividend rows
div_rows = (
    db.query(
        Transaction.isin,
        Transaction.name,
        Transaction.country,
        func.sum(Transaction.gross_amount).label("total_dividends"),
        func.count().label("payment_count"),
    )
    .filter(Transaction.type == TransactionType.DIVIDEND.value)
    .group_by(Transaction.isin, Transaction.name, Transaction.country)
    .all()
)

# Step 2: buy data
buy_data = (
    db.query(
        Transaction.isin,
        func.sum(func.abs(Transaction.net_amount_eur)).label("total_invested"),
        func.sum(Transaction.quantity).label("total_bought"),
    )
    .filter(Transaction.type == TransactionType.BUY.value)
    .group_by(Transaction.isin)
    .all()
)
buy_map = {r.isin: r for r in buy_data}

# Step 3: sell data
sell_data = (
    db.query(
        Transaction.isin,
        func.sum(func.abs(Transaction.quantity)).label("total_sold"),
    )
    .filter(Transaction.type == TransactionType.SELL.value)
    .group_by(Transaction.isin)
    .all()
)
sell_map = {r.isin: r for r in sell_data}

# Step 4: price data
latest_prices_q = (
    db.query(Transaction.isin, func.abs(Transaction.price).label("price"))
    .filter(Transaction.type.in_([TransactionType.BUY.value, TransactionType.SELL.value]))
    .filter(Transaction.isin.isnot(None))
    .order_by(Transaction.isin, Transaction.trade_date.desc())
    .all()
)
price_map = {}
for r in latest_prices_q:
    if r.isin not in price_map:
        price_map[r.isin] = r.price

# Step 5: Process each dividend ISIN
for d in div_rows:
    isin = d.isin or ""
    total_div = d.total_dividends or Decimal("0")
    buy = buy_map.get(isin)
    sell = sell_map.get(isin)

    try:
        total_invested = buy.total_invested if buy else Decimal("0")
        total_bought = buy.total_bought if buy else Decimal("0")
        total_sold = sell.total_sold if sell else Decimal("0")
        qty_remaining = total_bought - total_sold
        latest_price = price_map.get(isin, Decimal("0"))
        current_value = abs(qty_remaining * latest_price) if qty_remaining else Decimal("0")

        yield_on_cost = (total_div / total_invested * 100) if total_invested > 0 else Decimal("0")
        yield_on_value = (total_div / current_value * 100) if current_value > 0 else Decimal("0")

        # Test serialization
        result = {
            "isin": isin,
            "name": d.name,
            "total_dividends": str(total_div),
            "total_invested": str(total_invested),
            "qty_remaining": str(qty_remaining),
            "latest_price": str(latest_price),
            "current_value": str(current_value),
            "yield_on_cost": str(round(yield_on_cost, 2)),
            "yield_on_value": str(round(yield_on_value, 2)),
        }
        print(f"OK: {isin} {(d.name or '')[:30]} inv={total_invested:.2f} qty={qty_remaining:.4f}")
    except Exception as e:
        print(f"CRASH: {isin} {(d.name or '')[:30]}")
        print(f"  Error: {type(e).__name__}: {e}")
        print(f"  total_div={total_div!r} ({type(total_div).__name__})")
        print(f"  total_invested={buy.total_invested if buy else 'N/A'!r} ({type(buy.total_invested).__name__ if buy else 'N/A'})")
        print(f"  total_bought={buy.total_bought if buy else 'N/A'!r} ({type(buy.total_bought).__name__ if buy else 'N/A'})")
        print(f"  total_sold={sell.total_sold if sell else 'N/A'!r} ({type(sell.total_sold).__name__ if sell else 'N/A'})")
        if isin in price_map:
            print(f"  latest_price={price_map[isin]!r} ({type(price_map[isin]).__name__})")

db.close()
