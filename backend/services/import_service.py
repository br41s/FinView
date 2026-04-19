"""Service to import parsed broker data into the database."""

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.importers.base import (
    BBVAAnnualReport,
    DGAnnualReport,
    EToroAnnualReport,
    IBKRAnnualReport,
    INGAnnualReport,
    ParsedCapitalGain,
    ParsedCasilla,
    ParsedGainLoss,
    ParsedPortfolioHolding,
    ParsedTransaction,
    ParsedWithholding,
    TRTaxReport,
    TxType,
    country_from_isin,
)
from backend.models import (
    Account,
    Broker,
    CrossBrokerLot,
    FIFOAdjustment,
    ImportRecord,
    OptionAssignmentRecord,
    PortfolioHolding,
    TaxLot,
    TaxResult,
    Transaction,
    TransactionType,
)
from backend.services.fifo_engine import recalculate_cross_broker_fifo
from backend.services.sql_compat import year_str

logger = logging.getLogger(__name__)


def _run_supervisor(db: Session, import_id: int) -> list[dict]:
    """Run data supervisor checks and return serialized issues."""
    from backend.services.data_supervisor import run_checks

    try:
        issues = run_checks(db, import_id=import_id)
        return [
            {
                "id": i.id,
                "issue_type": i.issue_type,
                "severity": i.severity,
                "isin": i.isin,
                "name": i.name,
                "description": i.description,
                "status": i.status,
                "auto_resolution": i.auto_resolution,
            }
            for i in issues
        ]
    except Exception:
        logger.exception("Data supervisor failed for import %d", import_id)
        return []


TX_TYPE_MAP = {
    TxType.BUY: TransactionType.BUY,
    TxType.SELL: TransactionType.SELL,
    TxType.DIVIDEND: TransactionType.DIVIDEND,
    TxType.INTEREST: TransactionType.INTEREST,
    TxType.FEE: TransactionType.FEE,
    TxType.SPINOFF: TransactionType.SPINOFF,
}


def _get_or_create_account(db: Session, broker: Broker, account_id: str, user_id: int | None = None) -> Account:
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
            user_id=user_id,
        )
        db.add(account)
        db.flush()
    elif account.user_id is None and user_id is not None:
        account.user_id = user_id
        db.flush()
    return account


def _check_duplicate(db: Session, file_hash: str, broker: Broker) -> ImportRecord | None:
    return (
        db.query(ImportRecord)
        .filter(ImportRecord.file_hash == file_hash, ImportRecord.broker == broker.value)
        .first()
    )


def _check_year_duplicate(db: Session, broker: Broker, fiscal_year: int) -> ImportRecord | None:
    """Check if an import already exists for this broker + fiscal year."""
    return (
        db.query(ImportRecord)
        .filter(ImportRecord.broker == broker.value, ImportRecord.fiscal_year == fiscal_year)
        .first()
    )


def _delete_import_data(db: Session, import_id: int) -> None:
    """Cascade-delete all data from a previous import.

    Order: TaxLots (via buy/sell tx) → Transactions → TaxResults → ImportRecord.
    """
    import_rec = db.query(ImportRecord).filter(ImportRecord.id == import_id).first()
    if not import_rec:
        return

    # Get all transaction IDs from this import
    tx_ids = [
        t.id for t in
        db.query(Transaction.id).filter(Transaction.import_id == import_id).all()
    ]

    if tx_ids:
        # Delete TaxLots that reference these transactions
        db.query(TaxLot).filter(
            (TaxLot.buy_tx_id.in_(tx_ids)) | (TaxLot.sell_tx_id.in_(tx_ids))
        ).delete(synchronize_session="fetch")

        # Delete the transactions themselves
        db.query(Transaction).filter(Transaction.import_id == import_id).delete(
            synchronize_session="fetch"
        )

    # Delete TaxResults for this broker + year
    if import_rec.fiscal_year:
        db.query(TaxResult).filter(
            TaxResult.broker == import_rec.broker,
            TaxResult.fiscal_year == import_rec.fiscal_year,
        ).delete(synchronize_session="fetch")

        # Delete cross-broker FIFO data for this year (will be recalculated)
        db.query(CrossBrokerLot).filter(
            CrossBrokerLot.fiscal_year == import_rec.fiscal_year,
        ).delete(synchronize_session="fetch")
        db.query(FIFOAdjustment).filter(
            FIFOAdjustment.fiscal_year == import_rec.fiscal_year,
        ).delete(synchronize_session="fetch")

    # Delete option assignment records for this import
    db.query(OptionAssignmentRecord).filter(
        OptionAssignmentRecord.import_id == import_id,
    ).delete(synchronize_session="fetch")

    # Delete portfolio holdings for this import
    db.query(PortfolioHolding).filter(
        PortfolioHolding.import_id == import_id,
    ).delete(synchronize_session="fetch")

    # Delete the import record
    db.delete(import_rec)
    db.flush()


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
    db: Session, casillas: list[ParsedCasilla], fiscal_year: int, broker: Broker, user_id: int | None = None
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
            user_id=user_id or 1,
        )
        db.add(tr)
        results.append(tr)
    return results


def import_tr_report(db: Session, report: TRTaxReport, file_hash: str, filename: str, user_id: int | None = None) -> dict:
    """Import a parsed TR Tax Report into the database.

    Returns summary dict with counts and status.
    """
    # Check exact file duplicate
    existing = _check_duplicate(db, file_hash, Broker.TR)
    if existing:
        return {
            "status": "duplicate",
            "message": f"Este archivo ya fue importado el {existing.imported_at.isoformat()}",
            "import_id": existing.id,
        }

    # Check if same broker+year already imported → auto-replace
    replaced_id = None
    year_dup = _check_year_duplicate(db, Broker.TR, report.fiscal_year)
    if year_dup:
        replaced_id = year_dup.id
        _delete_import_data(db, year_dup.id)

    account = _get_or_create_account(db, Broker.TR, report.client_id, user_id)

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
    _store_casillas(db, all_casillas, report.fiscal_year, Broker.TR, user_id=user_id)

    # Recalculate cross-broker FIFO
    fifo_result = recalculate_cross_broker_fifo(db, report.fiscal_year, user_id=user_id)

    # Run data supervisor checks
    issues = _run_supervisor(db, import_rec.id)

    db.commit()

    return {
        "status": "replaced" if replaced_id else "success",
        "message": f"Reemplazó importación anterior (ID {replaced_id})" if replaced_id else None,
        "import_id": import_rec.id,
        "fiscal_year": report.fiscal_year,
        "counts": {
            "dividends": div_count,
            "transactions": tx_count,
            "capital_gains": len(lots),
            "casillas": len(all_casillas),
            "holdings": len(report.holdings),
            "withholdings": len(report.withholdings),
            "fifo_cross_broker": fifo_result["lots_created"],
        },
        "issues": issues,
    }


def _create_dg_tax_lots(
    db: Session,
    gains: list[ParsedGainLoss],
    transactions: list[ParsedTransaction],
    account_id: int,
    import_id: int,
    fiscal_year: int,
) -> list[TaxLot]:
    """Create TaxLot entries from DEGIRO gains summary.

    For each product with gains/losses, creates synthetic buy/sell
    transactions and links them in a TaxLot. Cost basis is derived
    from: cost = proceeds - realized_pl.
    """
    # Index sell transactions by ISIN (for dates and proceeds)
    sells_by_isin: dict[str, list[ParsedTransaction]] = {}
    for tx in transactions:
        if tx.tx_type == TxType.SELL:
            sells_by_isin.setdefault(tx.isin, []).append(tx)

    lots = []
    for g in gains:
        # Find sell date and proceeds from transaction list
        sells = sells_by_isin.get(g.isin, [])
        if sells:
            last_sell = max(sells, key=lambda t: t.trade_date)
            sell_date = last_sell.trade_date
            total_proceeds = sum(s.gross_amount for s in sells)
            total_qty = sum(s.quantity for s in sells)
        else:
            sell_date = date(fiscal_year, 12, 31)
            total_proceeds = g.realized_pl_eur  # fallback
            total_qty = Decimal("1")

        cost_basis = total_proceeds - g.realized_pl_eur
        country = country_from_isin(g.isin)

        # Create synthetic buy transaction
        buy_tx = Transaction(
            account_id=account_id,
            import_id=import_id,
            type=TransactionType.BUY.value,
            trade_date=date(fiscal_year, 1, 1),
            isin=g.isin,
            name=g.name,
            country=country,
            quantity=total_qty,
            price=cost_basis / total_qty if total_qty else Decimal("0"),
            currency="EUR",
            gross_amount=cost_basis,
            fees=g.commission_eur,
            net_amount_eur=cost_basis,
        )
        db.add(buy_tx)
        db.flush()

        # Create synthetic sell transaction
        sell_tx = Transaction(
            account_id=account_id,
            import_id=import_id,
            type=TransactionType.SELL.value,
            trade_date=sell_date,
            isin=g.isin,
            name=g.name,
            country=country,
            quantity=total_qty,
            price=total_proceeds / total_qty if total_qty else Decimal("0"),
            currency="EUR",
            gross_amount=total_proceeds,
            fees=Decimal("0"),
            net_amount_eur=total_proceeds,
        )
        db.add(sell_tx)
        db.flush()

        lot = TaxLot(
            buy_tx_id=buy_tx.id,
            sell_tx_id=sell_tx.id,
            isin=g.isin,
            quantity_bought=total_qty,
            quantity_remaining=Decimal("0"),
            cost_basis_eur=cost_basis,
            quantity_sold=total_qty,
            proceeds_eur=total_proceeds,
            realized_pl_eur=g.realized_pl_eur,
            close_date=sell_date,
        )
        db.add(lot)
        lots.append(lot)

    return lots


def _compute_broker_casillas(
    db: Session, broker: Broker, fiscal_year: int, account_id: int, user_id: int | None = None
) -> list[TaxResult]:
    """Compute Modelo 100 casilla values from Transaction/TaxLot data.

    Used for brokers that don't provide pre-calculated casillas (e.g. DEGIRO).
    """
    from sqlalchemy import func

    year_value = str(fiscal_year)

    # Casilla 29 — Dividendos brutos
    div_gross = (
        db.query(func.coalesce(func.sum(Transaction.gross_amount), 0))
        .filter(
            Transaction.account_id == account_id,
            Transaction.type == TransactionType.DIVIDEND.value,
            year_str(Transaction.trade_date) == year_value,
        )
        .scalar()
    ) or Decimal("0")

    # Casilla 332/337 — Ganancias/Pérdidas patrimoniales (from TaxLot via buy_tx)
    gains = (
        db.query(func.coalesce(func.sum(TaxLot.realized_pl_eur), 0))
        .join(Transaction, TaxLot.buy_tx_id == Transaction.id)
        .filter(
            Transaction.account_id == account_id,
            TaxLot.realized_pl_eur > 0,
            year_str(TaxLot.close_date) == year_value,
        )
        .scalar()
    ) or Decimal("0")

    losses = (
        db.query(func.coalesce(func.sum(TaxLot.realized_pl_eur), 0))
        .join(Transaction, TaxLot.buy_tx_id == Transaction.id)
        .filter(
            Transaction.account_id == account_id,
            TaxLot.realized_pl_eur < 0,
            year_str(TaxLot.close_date) == year_value,
        )
        .scalar()
    ) or Decimal("0")

    casilla_data = []
    if div_gross:
        casilla_data.append((100, 29, "Dividendos y demás rendimientos", div_gross))
    if gains:
        casilla_data.append((100, 332, "Ganancias patrimoniales", gains))
    if losses:
        casilla_data.append((100, 337, "Pérdidas patrimoniales", losses))

    results = []
    for modelo, casilla, desc, amount in casilla_data:
        tr = TaxResult(
            fiscal_year=fiscal_year,
            broker=broker.value,
            modelo=modelo,
            casilla=casilla,
            description=desc,
            amount_eur=amount,
            user_id=user_id or 1,
        )
        db.add(tr)
        results.append(tr)
    return results


def import_dg_report(db: Session, report: DGAnnualReport, file_hash: str, filename: str, user_id: int | None = None) -> dict:
    """Import a parsed DEGIRO Annual Report into the database."""
    existing = _check_duplicate(db, file_hash, Broker.DEGIRO)
    if existing:
        return {
            "status": "duplicate",
            "message": f"Este archivo ya fue importado el {existing.imported_at.isoformat()}",
            "import_id": existing.id,
        }

    # Check if same broker+year already imported → auto-replace
    replaced_id = None
    year_dup = _check_year_duplicate(db, Broker.DEGIRO, report.fiscal_year)
    if year_dup:
        replaced_id = year_dup.id
        _delete_import_data(db, year_dup.id)

    account = _get_or_create_account(db, Broker.DEGIRO, "DEGIRO", user_id)

    import_rec = ImportRecord(
        account_id=account.id,
        filename=filename,
        file_hash=file_hash,
        broker=Broker.DEGIRO.value,
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

    # Store all transactions
    tx_count = 0
    for tx in report.transactions:
        _store_transaction(db, tx, account.id, import_rec.id)
        tx_count += 1

    # Create TaxLots from gains summary
    lots = _create_dg_tax_lots(
        db, report.gains_summary, report.transactions,
        account.id, import_rec.id, report.fiscal_year,
    )

    # Compute and store casillas from transaction/lot data
    casillas = _compute_broker_casillas(db, Broker.DEGIRO, report.fiscal_year, account.id, user_id=user_id)

    # Recalculate cross-broker FIFO
    fifo_result = recalculate_cross_broker_fifo(db, report.fiscal_year, user_id=user_id)

    # Run data supervisor checks
    issues = _run_supervisor(db, import_rec.id)

    db.commit()

    return {
        "status": "replaced" if replaced_id else "success",
        "message": f"Reemplazó importación anterior (ID {replaced_id})" if replaced_id else None,
        "import_id": import_rec.id,
        "fiscal_year": report.fiscal_year,
        "counts": {
            "dividends": div_count,
            "transactions": tx_count,
            "capital_gains": len(lots),
            "casillas": len(casillas),
            "holdings": len(report.holdings),
            "gains_summary": len(report.gains_summary),
            "fifo_cross_broker": fifo_result["lots_created"],
        },
        "issues": issues,
    }


def import_ing_report(db: Session, report: INGAnnualReport, file_hash: str, filename: str, user_id: int | None = None) -> dict:
    """Import a parsed ING Información Fiscal PDF into the database."""
    existing = _check_duplicate(db, file_hash, Broker.ING)
    if existing:
        return {
            "status": "duplicate",
            "message": f"Este archivo ya fue importado el {existing.imported_at.isoformat()}",
            "import_id": existing.id,
        }

    replaced_id = None
    year_dup = _check_year_duplicate(db, Broker.ING, report.fiscal_year)
    if year_dup:
        replaced_id = year_dup.id
        _delete_import_data(db, year_dup.id)

    account = _get_or_create_account(db, Broker.ING, "ING", user_id)

    record_count = len(report.interest) + len(report.dividends) + len(report.transactions)
    import_rec = ImportRecord(
        account_id=account.id,
        filename=filename,
        file_hash=file_hash,
        broker=Broker.ING.value,
        fiscal_year=report.fiscal_year,
        record_count=record_count,
    )
    db.add(import_rec)
    db.flush()

    # Store interest
    int_count = 0
    for tx in report.interest:
        _store_transaction(db, tx, account.id, import_rec.id)
        int_count += 1

    # Store dividends
    div_count = 0
    for div in report.dividends:
        _store_transaction(db, div, account.id, import_rec.id)
        div_count += 1

    # Store buy/sell transactions
    tx_count = 0
    for tx in report.transactions:
        _store_transaction(db, tx, account.id, import_rec.id)
        tx_count += 1

    # Store year-end holdings
    hold_count = 0
    for h in report.holdings:
        db.add(PortfolioHolding(
            import_id=import_rec.id,
            account_id=account.id,
            fiscal_year=report.fiscal_year,
            broker=Broker.ING.value,
            isin=h.isin,
            name=h.name,
            country=h.country,
            currency=h.currency,
            quantity=h.quantity,
            price=h.price,
            value_eur=h.value_dec31_eur,
        ))
        hold_count += 1

    # Compute casillas from stored transactions
    casillas = _compute_broker_casillas(db, Broker.ING, report.fiscal_year, account.id, user_id=user_id)

    # Recalculate cross-broker FIFO
    fifo_result = recalculate_cross_broker_fifo(db, report.fiscal_year, user_id=user_id)

    # Run data supervisor checks
    issues = _run_supervisor(db, import_rec.id)

    db.commit()

    return {
        "status": "replaced" if replaced_id else "success",
        "message": f"Reemplazó importación anterior (ID {replaced_id})" if replaced_id else None,
        "import_id": import_rec.id,
        "fiscal_year": report.fiscal_year,
        "counts": {
            "interest": int_count,
            "dividends": div_count,
            "transactions": tx_count,
            "casillas": len(casillas),
            "holdings": hold_count,
            "fifo_cross_broker": fifo_result["lots_created"],
        },
        "issues": issues,
    }


def import_bbva_report(db: Session, report: BBVAAnnualReport, file_hash: str, filename: str, user_id: int | None = None) -> dict:
    """Import a parsed BBVA annual report (from 1-3 PDFs) into the database."""
    existing = _check_duplicate(db, file_hash, Broker.BBVA)
    if existing:
        return {
            "status": "duplicate",
            "message": f"Estos archivos ya fueron importados el {existing.imported_at.isoformat()}",
            "import_id": existing.id,
        }

    replaced_id = None
    year_dup = _check_year_duplicate(db, Broker.BBVA, report.fiscal_year)
    if year_dup:
        replaced_id = year_dup.id
        _delete_import_data(db, year_dup.id)

    account = _get_or_create_account(db, Broker.BBVA, "BBVA", user_id)

    record_count = len(report.dividends) + len(report.transactions)
    import_rec = ImportRecord(
        account_id=account.id,
        filename=filename,
        file_hash=file_hash,
        broker=Broker.BBVA.value,
        fiscal_year=report.fiscal_year,
        record_count=record_count,
    )
    db.add(import_rec)
    db.flush()

    # Store dividends
    div_count = 0
    for div in report.dividends:
        _store_transaction(db, div, account.id, import_rec.id)
        div_count += 1

    # Store buy/sell transactions
    tx_count = 0
    for tx in report.transactions:
        _store_transaction(db, tx, account.id, import_rec.id)
        tx_count += 1

    # Store custody fee as a FEE transaction if > 0
    fee_count = 0
    if report.custody_fee > 0:
        fee_tx = ParsedTransaction(
            tx_type=TxType.FEE,
            trade_date=date(report.fiscal_year, 12, 31),
            isin="",
            name="Gastos custodia BBVA",
            country="España",
            quantity=Decimal("0"),
            price=Decimal("0"),
            currency="EUR",
            gross_amount=report.custody_fee,
            fees=report.custody_fee,
            net_amount_eur=-report.custody_fee,
        )
        _store_transaction(db, fee_tx, account.id, import_rec.id)
        fee_count = 1

    # Store year-end holdings
    hold_count = 0
    for h in report.holdings:
        db.add(PortfolioHolding(
            import_id=import_rec.id,
            account_id=account.id,
            fiscal_year=report.fiscal_year,
            broker=Broker.BBVA.value,
            isin=h.isin,
            name=h.name,
            country=h.country,
            currency=h.currency,
            quantity=h.quantity,
            price=h.price,
            value_eur=h.value_dec31_eur,
        ))
        hold_count += 1

    # Compute casillas from stored transactions
    casillas = _compute_broker_casillas(db, Broker.BBVA, report.fiscal_year, account.id, user_id=user_id)

    # Recalculate cross-broker FIFO
    fifo_result = recalculate_cross_broker_fifo(db, report.fiscal_year, user_id=user_id)

    # Run data supervisor checks
    issues = _run_supervisor(db, import_rec.id)

    db.commit()

    return {
        "status": "replaced" if replaced_id else "success",
        "message": f"Reemplazó importación anterior (ID {replaced_id})" if replaced_id else None,
        "import_id": import_rec.id,
        "fiscal_year": report.fiscal_year,
        "counts": {
            "dividends": div_count,
            "transactions": tx_count,
            "fees": fee_count,
            "casillas": len(casillas),
            "holdings": hold_count,
            "fifo_cross_broker": fifo_result["lots_created"],
        },
        "issues": issues,
    }


def import_etoro_report(db: Session, report: EToroAnnualReport, file_hash: str, filename: str, user_id: int | None = None) -> dict:
    """Import a parsed eToro annual account statement into the database."""
    existing = _check_duplicate(db, file_hash, Broker.ETORO)
    if existing:
        return {
            "status": "duplicate",
            "message": f"Este archivo ya fue importado el {existing.imported_at.isoformat()}",
            "import_id": existing.id,
        }

    replaced_id = None
    year_dup = _check_year_duplicate(db, Broker.ETORO, report.fiscal_year)
    if year_dup:
        replaced_id = year_dup.id
        _delete_import_data(db, year_dup.id)

    account = _get_or_create_account(db, Broker.ETORO, "ETORO", user_id)

    record_count = (
        len(report.dividends) + len(report.transactions) + len(report.closed_positions) * 2
    )
    import_rec = ImportRecord(
        account_id=account.id,
        filename=filename,
        file_hash=file_hash,
        broker=Broker.ETORO.value,
        fiscal_year=report.fiscal_year,
        record_count=record_count,
    )
    db.add(import_rec)
    db.flush()

    # Dividends
    div_count = 0
    for div in report.dividends:
        _store_transaction(db, div, account.id, import_rec.id)
        div_count += 1

    # Open positions (buys still held)
    tx_count = 0
    for tx in report.transactions:
        _store_transaction(db, tx, account.id, import_rec.id)
        tx_count += 1

    # Closed positions → BUY+SELL pairs + TaxLots with realized P&L
    lots = _store_capital_gains_as_lots(
        db, report.closed_positions, account.id, import_rec.id
    )
    tx_count += len(lots) * 2

    casillas = _compute_broker_casillas(db, Broker.ETORO, report.fiscal_year, account.id, user_id=user_id)

    # Recalculate cross-broker FIFO
    fifo_result = recalculate_cross_broker_fifo(db, report.fiscal_year, user_id=user_id)

    # Run data supervisor checks
    issues = _run_supervisor(db, import_rec.id)

    db.commit()

    return {
        "status": "replaced" if replaced_id else "success",
        "message": f"Reemplazó importación anterior (ID {replaced_id})" if replaced_id else None,
        "import_id": import_rec.id,
        "fiscal_year": report.fiscal_year,
        "counts": {
            "dividends": div_count,
            "transactions": tx_count,
            "casillas": len(casillas),
            "fifo_cross_broker": fifo_result["lots_created"],
        },
        "issues": issues,
    }


def _create_ibkr_tax_lots(
    db: Session,
    realized_gains: list[ParsedGainLoss],
    account_id: int,
    import_id: int,
    fiscal_year: int,
) -> list[TaxLot]:
    """Create TaxLot entries from IBKR realized performance summary.

    The realized P/L values are already in EUR (base currency) and come
    directly from IBKR — they are the source of truth.
    """
    lots = []
    for g in realized_gains:
        country = country_from_isin(g.isin)
        # Realized P/L is the net result; derive synthetic cost/proceeds
        if g.realized_pl_eur >= 0:
            cost = Decimal("0")
            proceeds = g.realized_pl_eur
        else:
            cost = abs(g.realized_pl_eur)
            proceeds = Decimal("0")

        buy_tx = Transaction(
            account_id=account_id,
            import_id=import_id,
            type=TransactionType.BUY.value,
            trade_date=date(fiscal_year, 1, 1),
            isin=g.isin,
            name=g.name,
            country=country,
            quantity=Decimal("1"),
            price=cost,
            currency="EUR",
            gross_amount=cost,
            fees=Decimal("0"),
            net_amount_eur=cost,
        )
        db.add(buy_tx)
        db.flush()

        sell_tx = Transaction(
            account_id=account_id,
            import_id=import_id,
            type=TransactionType.SELL.value,
            trade_date=date(fiscal_year, 12, 31),
            isin=g.isin,
            name=g.name,
            country=country,
            quantity=Decimal("1"),
            price=proceeds,
            currency="EUR",
            gross_amount=proceeds,
            fees=Decimal("0"),
            net_amount_eur=proceeds,
        )
        db.add(sell_tx)
        db.flush()

        lot = TaxLot(
            buy_tx_id=buy_tx.id,
            sell_tx_id=sell_tx.id,
            isin=g.isin,
            quantity_bought=Decimal("1"),
            quantity_remaining=Decimal("0"),
            cost_basis_eur=cost,
            quantity_sold=Decimal("1"),
            proceeds_eur=proceeds,
            realized_pl_eur=g.realized_pl_eur,
            close_date=date(fiscal_year, 12, 31),
            holding_period="<1y",
        )
        db.add(lot)
        lots.append(lot)

    return lots


def import_ibkr_report(
    db: Session, report: IBKRAnnualReport, file_hash: str, filename: str, user_id: int | None = None
) -> dict:
    """Import a parsed IBKR Activity Statement into the database."""
    existing = _check_duplicate(db, file_hash, Broker.IBKR)
    if existing:
        return {
            "status": "duplicate",
            "message": f"Este archivo ya fue importado el {existing.imported_at.isoformat()}",
            "import_id": existing.id,
        }

    # Check if same broker+year already imported → auto-replace
    replaced_id = None
    year_dup = _check_year_duplicate(db, Broker.IBKR, report.fiscal_year)
    if year_dup:
        replaced_id = year_dup.id
        _delete_import_data(db, year_dup.id)

    account = _get_or_create_account(db, Broker.IBKR, report.account_id, user_id)

    import_rec = ImportRecord(
        account_id=account.id,
        filename=filename,
        file_hash=file_hash,
        broker=Broker.IBKR.value,
        fiscal_year=report.fiscal_year,
        record_count=(
            len(report.trades) + len(report.dividends) + len(report.interest)
        ),
    )
    db.add(import_rec)
    db.flush()

    # Store dividends
    div_count = 0
    for div in report.dividends:
        _store_transaction(db, div, account.id, import_rec.id)
        div_count += 1

    # Store interest
    int_count = 0
    for intr in report.interest:
        _store_transaction(db, intr, account.id, import_rec.id)
        int_count += 1

    # Store individual trades (informational)
    tx_count = 0
    for tx in report.trades:
        _store_transaction(db, tx, account.id, import_rec.id)
        tx_count += 1

    # Create TaxLots from IBKR's realized P/L (source of truth)
    lots = _create_ibkr_tax_lots(
        db, report.realized_gains, account.id, import_rec.id, report.fiscal_year
    )

    # Store detected option assignments (informational for IRPF audit)
    for a in report.assignments:
        db.add(OptionAssignmentRecord(
            import_id=import_rec.id,
            fiscal_year=report.fiscal_year,
            assignment_date=a.assignment_date,
            underlying=a.underlying,
            option_symbol=a.option_symbol,
            option_type="PUT" if a.option_type == "P" else "CALL",
            strike=a.strike,
            stock_quantity=a.stock_quantity,
            stock_isin=a.stock_isin,
            premium_eur=a.premium_eur,
        ))

    # Compute casillas from the stored data
    casillas = _compute_broker_casillas(
        db, Broker.IBKR, report.fiscal_year, account.id, user_id=user_id
    )

    # Recalculate cross-broker FIFO
    fifo_result = recalculate_cross_broker_fifo(db, report.fiscal_year, user_id=user_id)

    # Run data supervisor checks
    issues = _run_supervisor(db, import_rec.id)

    db.commit()

    return {
        "status": "replaced" if replaced_id else "success",
        "message": f"Reemplazó importación anterior (ID {replaced_id})" if replaced_id else None,
        "import_id": import_rec.id,
        "fiscal_year": report.fiscal_year,
        "counts": {
            "dividends": div_count,
            "interest": int_count,
            "transactions": tx_count,
            "capital_gains": len(lots),
            "casillas": len(casillas),
            "holdings": len(report.holdings),
            "fifo_cross_broker": fifo_result["lots_created"],
            "option_assignments": len(report.assignments),
        },
        "issues": issues,
        "assignments": [
            {
                "date": a.assignment_date.isoformat(),
                "underlying": a.underlying,
                "option": a.option_symbol,
                "type": "PUT" if a.option_type == "P" else "CALL",
                "strike": str(a.strike),
                "shares": str(a.stock_quantity),
                "premium_eur": str(a.premium_eur),
            }
            for a in report.assignments
        ],
    }
