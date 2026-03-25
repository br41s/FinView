"""Verify specific ISINs for data correctness."""
import sys, json, urllib.request

r = urllib.request.urlopen("http://localhost:8000/api/charts/dividend-yield")
data = json.loads(r.read())

print("Companies with no remaining shares (fully sold):")
for item in data:
    if float(item["qty_remaining"]) <= 0:
        name = (item["name"] or "")[:35]
        print(f"  {name:<36} inv={float(item['total_invested']):>10.2f}  qty={float(item['qty_remaining']):>10.4f}")

print("\nCompanies with remaining shares (current holdings):")
for item in data:
    if float(item["qty_remaining"]) > 0:
        name = (item["name"] or "")[:35]
        val = float(item["current_value"])
        price = float(item["latest_price"])
        print(f"  {name:<36} qty={float(item['qty_remaining']):>10.4f}  price={price:>8.2f}  value={val:>10.2f}")

# Specific check: Acerinox (user mentioned large invested amount)
acerinox = [x for x in data if "Acerinox" in (x["name"] or "")]
if acerinox:
    a = acerinox[0]
    print(f"\nAcerinox check: inv={a['total_invested']}, qty={a['qty_remaining']}, div={a['total_dividends']}")
