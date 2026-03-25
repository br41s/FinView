"""Test the fixed dividend yield calculation."""
import sys
sys.path.insert(0, "/Users/brais/VSCODE/FinView")

from decimal import Decimal
from backend.database import SessionLocal
from backend.models import Transaction, TransactionType
from sqlalchemy import func

db = SessionLocal()

# Test buy_data query
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
print("BUY data sample:")
for r in buy_data[:3]:
    print(f"  ISIN={r.isin}  invested={r.total_invested}  bought={r.total_bought}")

# Test sell_data query
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

# Check Logista (ES0105027009)
logista = [r for r in buy_data if r.isin == "ES0105027009"]
if logista:
    b = logista[0]
    s = sell_map.get("ES0105027009")
    total_sold = s.total_sold if s else Decimal("0")
    remaining = b.total_bought - total_sold
    print("\nLogista:")
    print(f"  total_invested = {b.total_invested}")
    print(f"  total_bought   = {b.total_bought}")
    print(f"  total_sold     = {total_sold}")
    print(f"  qty_remaining  = {remaining}")
    print(f"  Type of invested: {type(b.total_invested)}")
    print(f"  Type of bought:   {type(b.total_bought)}")

# Now test via HTTP
print("\n--- HTTP endpoint test ---")
import urllib.request
import json
try:
    r = urllib.request.urlopen("http://localhost:8000/api/charts/dividend-yield")
    data = json.loads(r.read())
    for item in data:
        name = (item["name"] or "")[:35]
        invested = float(item["total_invested"])
        divs = float(item["total_dividends"])
        qty = float(item["qty_remaining"])
        yoc = float(item["yield_on_cost"])
        print(f"  {name:<36} inv={invested:>10.2f}  div={divs:>8.2f}  qty={qty:>10.4f}  YoC={yoc:>6.2f}%")
except Exception as e:
    if hasattr(e, "read"):
        print(f"HTTP ERROR: {e.read().decode()}")
    else:
        print(f"ERROR: {e}")

db.close()
