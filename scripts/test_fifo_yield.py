"""Test FIFO dividend yield endpoint."""
import sys, json, urllib.request

try:
    r = urllib.request.urlopen("http://localhost:8000/api/charts/dividend-yield")
    data = json.loads(r.read())
    print(f"{'Company':<36} {'Invested':>12} {'Dividends':>10} {'Qty':>12} {'YoC':>7} {'YoV':>7}")
    print("-" * 90)
    for item in data:
        name = (item["name"] or "")[:35]
        invested = float(item["total_invested"])
        divs = float(item["total_dividends"])
        qty = float(item["qty_remaining"])
        yoc = float(item["yield_on_cost"])
        yov = float(item["yield_on_value"])
        print(f"  {name:<36} {invested:>10.2f}  {divs:>8.2f}  {qty:>10.4f}  {yoc:>6.2f}%  {yov:>6.2f}%")
    print(f"\nTotal ISINs: {len(data)}")
except Exception as e:
    if hasattr(e, "read"):
        body = e.read().decode()
        print(f"HTTP ERROR {e.code}: {body}")
    else:
        print(f"ERROR: {e}")
