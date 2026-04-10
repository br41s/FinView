"""One-time migration: normalize withholding_tax to always be negative (or zero)."""
import sqlite3

DB = "finview.db"

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Before
    print("Before fix:")
    for row in cur.execute(
        "SELECT ir.broker, "
        "SUM(CASE WHEN t.withholding_tax > 0 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN t.withholding_tax < 0 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN t.withholding_tax = 0 THEN 1 ELSE 0 END) "
        "FROM transactions t JOIN import_records ir ON t.import_id = ir.id "
        "WHERE t.type = 'DIVIDEND' GROUP BY ir.broker"
    ):
        print(f"  {row[0]}: pos={row[1]}, neg={row[2]}, zero={row[3]}")

    # 1. Flip sign of withholding_tax for brokers that stored positive values
    cur.execute(
        "UPDATE transactions SET withholding_tax = -withholding_tax "
        "WHERE type = 'DIVIDEND' AND withholding_tax > 0 "
        "AND import_id IN (SELECT id FROM import_records WHERE broker IN ('IBKR', 'ETORO', 'TR'))"
    )
    print(f"\nFlipped withholding sign: {cur.rowcount} rows")

    # 2. Fix TR net_amount_eur: was stored as gross (wrong), should be gross + wh (wh now negative)
    cur.execute(
        "UPDATE transactions SET net_amount_eur = gross_amount + withholding_tax "
        "WHERE type = 'DIVIDEND' AND withholding_tax != 0 "
        "AND import_id IN (SELECT id FROM import_records WHERE broker = 'TR')"
    )
    print(f"Fixed TR net_amount_eur: {cur.rowcount} rows")

    conn.commit()

    # After
    print("\nAfter fix:")
    for row in cur.execute(
        "SELECT ir.broker, "
        "SUM(CASE WHEN t.withholding_tax > 0 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN t.withholding_tax < 0 THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN t.withholding_tax = 0 THEN 1 ELSE 0 END) "
        "FROM transactions t JOIN import_records ir ON t.import_id = ir.id "
        "WHERE t.type = 'DIVIDEND' GROUP BY ir.broker"
    ):
        print(f"  {row[0]}: pos={row[1]}, neg={row[2]}, zero={row[3]}")

    print("\nTR samples:")
    for row in cur.execute(
        "SELECT t.name, t.gross_amount, t.withholding_tax, t.net_amount_eur "
        "FROM transactions t JOIN import_records ir ON t.import_id = ir.id "
        "WHERE ir.broker = 'TR' AND t.type = 'DIVIDEND' AND t.withholding_tax != 0 LIMIT 3"
    ):
        print(f"  {row[0]}: gross={row[1]}, wh={row[2]}, net={row[3]}")

    conn.close()

if __name__ == "__main__":
    main()
