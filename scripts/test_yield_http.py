"""Quick HTTP test for dividend-yield endpoint."""
import sys, json, urllib.request

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
    print(f"\nTotal ISINs: {len(data)}")
except Exception as e:
    if hasattr(e, "read"):
        body = e.read().decode()
        print(f"HTTP ERROR {e.code}: {body}")
    else:
        print(f"ERROR: {e}")
