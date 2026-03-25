"""Chart and analytics API endpoints."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import TaxLot, Transaction, TransactionType

router = APIRouter(prefix="/charts", tags=["charts"])


@router.get("/dividends-by-country")
def dividends_by_country(
    fiscal_year: int | None = None,
    db: Session = Depends(get_db),
):
    """Dividends aggregated by country for donut chart."""
    q = db.query(
        func.coalesce(Transaction.country, "Desconocido").label("country"),
        func.sum(Transaction.gross_amount).label("gross"),
        func.sum(Transaction.withholding_tax).label("withholding"),
        func.sum(Transaction.net_amount_eur).label("net"),
        func.count().label("count"),
    ).filter(Transaction.type == TransactionType.DIVIDEND.value)

    if fiscal_year:
        q = q.filter(func.strftime("%Y", Transaction.trade_date) == str(fiscal_year))

    rows = q.group_by("country").order_by(func.sum(Transaction.gross_amount).desc()).all()

    return [
        {
            "country": r.country,
            "gross": str(r.gross or 0),
            "withholding": str(r.withholding or 0),
            "net": str(r.net or 0),
            "count": r.count,
        }
        for r in rows
    ]


@router.get("/dividends-monthly")
def dividends_monthly(
    fiscal_year: int | None = None,
    db: Session = Depends(get_db),
):
    """Monthly dividend income for bar chart."""
    q = db.query(
        func.strftime("%Y-%m", Transaction.trade_date).label("month"),
        func.sum(Transaction.gross_amount).label("gross"),
        func.sum(Transaction.withholding_tax).label("withholding"),
        func.sum(Transaction.net_amount_eur).label("net"),
        func.count().label("count"),
    ).filter(Transaction.type == TransactionType.DIVIDEND.value)

    if fiscal_year:
        q = q.filter(func.strftime("%Y", Transaction.trade_date) == str(fiscal_year))

    rows = q.group_by("month").order_by("month").all()

    return [
        {
            "month": r.month,
            "gross": str(r.gross or 0),
            "withholding": str(r.withholding or 0),
            "net": str(r.net or 0),
            "count": r.count,
        }
        for r in rows
    ]


@router.get("/top-dividend-payers")
def top_dividend_payers(
    fiscal_year: int | None = None,
    limit: int = Query(default=10, le=50),
    db: Session = Depends(get_db),
):
    """Top N dividend-paying companies."""
    q = db.query(
        Transaction.isin,
        Transaction.name,
        Transaction.country,
        func.sum(Transaction.gross_amount).label("gross"),
        func.sum(Transaction.withholding_tax).label("withholding"),
        func.sum(Transaction.net_amount_eur).label("net"),
        func.count().label("count"),
    ).filter(Transaction.type == TransactionType.DIVIDEND.value)

    if fiscal_year:
        q = q.filter(func.strftime("%Y", Transaction.trade_date) == str(fiscal_year))

    rows = (
        q.group_by(Transaction.isin, Transaction.name, Transaction.country)
        .order_by(func.sum(Transaction.gross_amount).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "isin": r.isin,
            "name": r.name,
            "country": r.country,
            "gross": str(r.gross or 0),
            "withholding": str(r.withholding or 0),
            "net": str(r.net or 0),
            "count": r.count,
        }
        for r in rows
    ]


@router.get("/capital-gains-breakdown")
def capital_gains_breakdown(
    fiscal_year: int | None = None,
    db: Session = Depends(get_db),
):
    """Capital gains/losses per ISIN for bar chart."""
    q = db.query(
        TaxLot.isin,
        func.sum(
            case((TaxLot.realized_pl_eur > 0, TaxLot.realized_pl_eur), else_=Decimal("0"))
        ).label("gains"),
        func.sum(
            case((TaxLot.realized_pl_eur < 0, TaxLot.realized_pl_eur), else_=Decimal("0"))
        ).label("losses"),
        func.sum(TaxLot.realized_pl_eur).label("net"),
        func.count().label("trades"),
    ).filter(TaxLot.sell_tx_id.isnot(None))

    if fiscal_year:
        q = q.filter(func.strftime("%Y", TaxLot.close_date) == str(fiscal_year))

    rows = q.group_by(TaxLot.isin).order_by(func.sum(TaxLot.realized_pl_eur)).all()

    # Build ISIN → name map from transactions
    isins = [r.isin for r in rows]
    name_rows = (
        db.query(Transaction.isin, Transaction.name)
        .filter(Transaction.isin.in_(isins))
        .distinct()
        .all()
    )
    name_map = {r.isin: r.name for r in name_rows}

    return [
        {
            "isin": r.isin,
            "name": name_map.get(r.isin, r.isin),
            "gains": str(r.gains or 0),
            "losses": str(r.losses or 0),
            "net": str(r.net or 0),
            "trades": r.trades,
        }
        for r in rows
    ]


@router.get("/patrimonio-composition")
def patrimonio_composition(db: Session = Depends(get_db)):
    """Portfolio composition from Modelo 714 casillas."""
    from backend.models import TaxResult

    rows = (
        db.query(TaxResult)
        .filter(TaxResult.modelo == 714)
        .order_by(TaxResult.fiscal_year.desc(), TaxResult.casilla)
        .all()
    )

    return [
        {
            "casilla": r.casilla,
            "description": r.description,
            "amount": str(r.amount_eur),
            "fiscal_year": r.fiscal_year,
        }
        for r in rows
    ]


@router.get("/dividend-yield")
def dividend_yield(
    fiscal_year: int | None = None,
    db: Session = Depends(get_db),
):
    """Dividend yield per ISIN: dividends vs cost basis invested.

    For each ISIN that paid dividends:
    - total_dividends: sum of gross dividend payments
    - total_invested: sum of cost_basis_eur from all buy lots (closed + open)
    - current_value: quantity_remaining * latest buy price (approximation from TR data)
    - yield_on_cost: dividends / invested * 100
    - yield_on_value: dividends / current_holding_value * 100
    """
    # Get dividend totals by ISIN
    div_q = db.query(
        Transaction.isin,
        Transaction.name,
        Transaction.country,
        func.sum(Transaction.gross_amount).label("total_dividends"),
        func.count().label("payment_count"),
    ).filter(Transaction.type == TransactionType.DIVIDEND.value)

    if fiscal_year:
        div_q = div_q.filter(func.strftime("%Y", Transaction.trade_date) == str(fiscal_year))

    div_rows = div_q.group_by(Transaction.isin, Transaction.name, Transaction.country).all()

    # Get cost basis and current holdings per ISIN from TaxLots
    lot_data = (
        db.query(
            TaxLot.isin,
            func.sum(TaxLot.cost_basis_eur).label("total_invested"),
            func.sum(TaxLot.quantity_remaining).label("qty_remaining"),
        )
        .group_by(TaxLot.isin)
        .all()
    )
    lot_map = {r.isin: r for r in lot_data}

    # Get latest price per ISIN from BUY/SELL transactions
    # Use subquery to get latest trade_date per ISIN
    latest_prices_q = (
        db.query(Transaction.isin, Transaction.price)
        .filter(Transaction.type.in_([TransactionType.BUY.value, TransactionType.SELL.value]))
        .filter(Transaction.isin.isnot(None))
        .order_by(Transaction.isin, Transaction.trade_date.desc())
        .all()
    )
    # Take the first (most recent) price per ISIN
    price_map: dict[str, Decimal] = {}
    for r in latest_prices_q:
        if r.isin not in price_map:
            price_map[r.isin] = r.price

    results = []
    for d in div_rows:
        isin = d.isin or ""
        total_div = d.total_dividends or Decimal("0")
        lot = lot_map.get(isin)

        total_invested = abs(lot.total_invested) if lot else Decimal("0")
        qty_remaining = lot.qty_remaining if lot else Decimal("0")
        latest_price = price_map.get(isin, Decimal("0"))
        current_value = abs(qty_remaining * latest_price) if qty_remaining else Decimal("0")

        yield_on_cost = (
            (total_div / total_invested * 100) if total_invested > 0 else Decimal("0")
        )
        yield_on_value = (
            (total_div / current_value * 100) if current_value > 0 else Decimal("0")
        )

        results.append(
            {
                "isin": isin,
                "name": d.name,
                "country": d.country,
                "total_dividends": str(total_div),
                "total_invested": str(total_invested),
                "qty_remaining": str(qty_remaining),
                "latest_price": str(latest_price),
                "current_value": str(current_value),
                "yield_on_cost": str(round(yield_on_cost, 2)),
                "yield_on_value": str(round(yield_on_value, 2)),
                "payment_count": d.payment_count,
            }
        )

    results.sort(key=lambda x: float(x["yield_on_cost"]), reverse=True)
    return results


@router.get("/withholdings-by-country")
def withholdings_by_country(
    fiscal_year: int | None = None,
    db: Session = Depends(get_db),
):
    """Withholding tax breakdown by country for double taxation analysis."""
    q = db.query(
        func.coalesce(Transaction.country, "Desconocido").label("country"),
        func.sum(Transaction.gross_amount).label("gross"),
        func.sum(Transaction.withholding_tax).label("withholding"),
        func.sum(Transaction.net_amount_eur).label("net"),
    ).filter(
        Transaction.type == TransactionType.DIVIDEND.value,
        Transaction.withholding_tax > 0,
    )

    if fiscal_year:
        q = q.filter(func.strftime("%Y", Transaction.trade_date) == str(fiscal_year))

    rows = q.group_by("country").order_by(func.sum(Transaction.withholding_tax).desc()).all()

    return [
        {
            "country": r.country,
            "gross": str(r.gross or 0),
            "withholding": str(r.withholding or 0),
            "net": str(r.net or 0),
            "effective_rate": str(
                round(
                    (r.withholding / r.gross * 100) if r.gross and r.gross > 0 else 0,
                    2,
                )
            ),
        }
        for r in rows
    ]
