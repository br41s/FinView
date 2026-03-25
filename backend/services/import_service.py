"""Service to import parsed broker data into the database."""

from decimal import Decimal

from sqlalchemy.orm import Session

from backend.importers.base import (
    ParsedCapitalGain,
    ParsedCasilla,
    ParsedPortfolioHolding,
    ParsedTransaction,
    ParsedWithholding,
    TRTaxReport,
    TxType,
)
from backend.models import (
    Account,
    Broker,
    ImportRecord,
    TaxLot,
    TaxResult,
    Transaction,
    TransactionType,
)


TX_TYPE_MAP = {
    TxType.BUY: TransactionType.BUY,
    TxType.SELL: TransactionType.SELL,
    TxType.DIVIDEND: TransactionType.DIVIDEND,
    TxType.INTEREST: TransactionType.INTEREST,
    TxType.FEE: TransactionType.FEE,
    TxType.SPINOFF: TransactionType.SPINOFF,
}


def _get_or_create_account(db: Session, broker: Broker, account_id: str) -> Account:
    account = (
        db.query(Account)
        .filter(Account.broker == broker.value, Account.account_id == account_id)
        .first()
    )
    if not account:
        account = Account(
            broker=broker.value,
            account_id=account_id,
            name=f"{broker.value} - {account_id}",
        )
        db.add(account)
        db.flush()
    return account


def _check_duplicate(db: Session, file_hash: str, broker: Broker) -> ImportRecord | None:
    return (
        db.query(ImportRecord)
        .filter(ImportRecord.file_hash == file_hash, ImportRecord.broker == broker.value)
        .first()
    )


def _store_transaction(db: Session, tx: ParsedTransaction, account_id: int, import_id: int) -> Transaction:
    db_tx = Transaction(
        account_id=account_id,
        import_id=import_id,
        type=TX_TYPE_MAP.get(tx.tx_type, TransactionType.BUY).value,
        trade_date=tx.trade_date,
        isin=tx.isin,
        name=tx.name,
        country=tx.country,
        quantity=tx.quantity,
        price=tx.price,
        currency=tx.currency,
        exchange_rate=tx.exchange_rate,
        gross_amount=tx.gross_amount,
        fees=tx.fees,
        withholding_tax=tx.withholding_tax,
        net_amount_eur=tx.net_amount_eur,
        withholding_rate=tx.withholding_rate,
        double_taxation_amount=tx.double_taxation_amount,
        casilla=tx.casilla,
        holding_period=tx.holding_period,
    )
    db.add(db_tx)
    return db_tx


def _store_capital_gains_as_lots(
    db: Session, gains: list[ParsedCapitalGain], account_id: int, import_id: int
) -> list[TaxLot]:
    """Store pre-calculated capital gains from TR as TaxLot entries."""
    lots = []
    for g in gains:
        # Create buy transaction
        buy_tx = Transaction(
            account_id=account_id,
            import_id=import_id,
            type=TransactionType.BUY.value,
            trade_date=g.buy_date,
            isin=g.isin,
            name=g.name,
            country=g.country,
            quantity=g.buy_quantity,
            price=g.buy_price,
            currency="EUR",
            gross_amount=g.buy_total_eur,
            fees=g.buy_fees,
            net_amount_eur=g.buy_total_eur,
        )
        db.add(buy_tx)
        db.flush()

        # Create sell transaction
        sell_tx = Transaction(
            account_id=account_id,
            import_id=import_id,
            type=TransactionType.SELL.value,
            trade_date=g.sell_date,
            isin=g.isin,
            name=g.name,
            country=g.country,
            quantity=g.sell_quantity,
            price=g.sell_price,
            currency="EUR",
            gross_amount=g.sell_total_eur,
            fees=g.sell_fees,
            net_amount_eur=g.sell_total_eur,
            casilla=g.casilla,
            holding_period=g.holding_period,
        )
        db.add(sell_tx)
        db.flush()

        lot = TaxLot(
            buy_tx_id=buy_tx.id,
            sell_tx_id=sell_tx.id,
            isin=g.isin,
            quantity_bought=g.buy_quantity,
            quantity_remaining=Decimal("0"),
            cost_basis_eur=g.buy_total_eur,
            quantity_sold=g.sell_quantity,
            proceeds_eur=g.sell_total_eur,
            realized_pl_eur=g.realized_pl_eur,
            close_date=g.sell_date,
            holding_period=g.holding_period,
        )
        db.add(lot)
        lots.append(lot)

    return lots


def _store_casillas(
    db: Session, casillas: list[ParsedCasilla], fiscal_year: int, broker: Broker
) -> list[TaxResult]:
    results = []
    for c in casillas:
        tr = TaxResult(
            fiscal_year=fiscal_year,
            broker=broker.value,
            modelo=c.modelo,
            casilla=c.casilla,
            description=c.description,
            amount_eur=c.amount_eur,
            tr_reference_amount=c.amount_eur,
        )
        db.add(tr)
        results.append(tr)
    return results


def import_tr_report(db: Session, report: TRTaxReport, file_hash: str, filename: str) -> dict:
    """Import a parsed TR Tax Report into the database.

    Returns summary dict with counts and status.
    """
    # Check duplicate
    existing = _check_duplicate(db, file_hash, Broker.TR)
    if existing:
        return {
            "status": "duplicate",
            "message": f"Este archivo ya fue importado el {existing.imported_at.isoformat()}",
            "import_id": existing.id,
        }

    account = _get_or_create_account(db, Broker.TR, report.client_id)

    import_rec = ImportRecord(
        account_id=account.id,
        filename=filename,
        file_hash=file_hash,
        broker=Broker.TR.value,
        fiscal_year=report.fiscal_year,
        record_count=len(report.transactions) + len(report.dividends),
    )
    db.add(import_rec)
    db.flush()

    # Store dividends
    div_count = 0
    for div in report.dividends:
        _store_transaction(db, div, account.id, import_rec.id)
        div_count += 1

    # Store all transactions (buys/sells/etc from Section VI)
    tx_count = 0
    for tx in report.transactions:
        _store_transaction(db, tx, account.id, import_rec.id)
        tx_count += 1

    # Store capital gains as FIFO lots
    lots = _store_capital_gains_as_lots(db, report.capital_gains, account.id, import_rec.id)

    # Store casillas (Modelo 100 + 714)
    all_casillas = report.casillas_modelo_100 + report.casillas_modelo_714
    _store_casillas(db, all_casillas, report.fiscal_year, Broker.TR)

    db.commit()

    return {
        "status": "success",
        "import_id": import_rec.id,
        "fiscal_year": report.fiscal_year,
        "counts": {
            "dividends": div_count,
            "transactions": tx_count,
            "capital_gains": len(lots),
            "casillas": len(all_casillas),
            "holdings": len(report.holdings),
            "withholdings": len(report.withholdings),
        },
    }
