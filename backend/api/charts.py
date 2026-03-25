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
    """Dividend yield per ISIN: dividends vs avg invested at dividend dates.

    For each ISIN that paid dividends:
    - total_invested: average FIFO cost basis at each dividend payment date
    - qty_remaining: total bought - total sold (current position)
    - current_value: qty_remaining * latest price
    - yield_on_cost: dividends / avg_invested * 100
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

    # Collect ISINs with dividends
    div_isins = [d.isin for d in div_rows if d.isin]

    if not div_isins:
        return []

    # Fetch individual dividend dates per ISIN
    div_dates_q = db.query(
        Transaction.isin,
        Transaction.trade_date,
    ).filter(
        Transaction.type == TransactionType.DIVIDEND.value,
        Transaction.isin.in_(div_isins),
    )
    if fiscal_year:
        div_dates_q = div_dates_q.filter(
            func.strftime("%Y", Transaction.trade_date) == str(fiscal_year)
        )
    div_dates_rows = div_dates_q.all()

    # Group dividend dates by ISIN
    div_dates_by_isin: dict[str, list] = {}
    for r in div_dates_rows:
        div_dates_by_isin.setdefault(r.isin, []).append(r.trade_date)

    # Fetch all BUY transactions for these ISINs (ordered by date for FIFO)
    all_buys = (
        db.query(Transaction)
        .filter(
            Transaction.type == TransactionType.BUY.value,
            Transaction.isin.in_(div_isins),
        )
        .order_by(Transaction.isin, Transaction.trade_date, Transaction.id)
        .all()
    )
    buys_by_isin: dict[str, list] = {}
    for tx in all_buys:
        buys_by_isin.setdefault(tx.isin, []).append(tx)

    # Fetch all SELL transactions for these ISINs (ordered by date for FIFO)
    all_sells = (
        db.query(Transaction)
        .filter(
            Transaction.type == TransactionType.SELL.value,
            Transaction.isin.in_(div_isins),
        )
        .order_by(Transaction.isin, Transaction.trade_date, Transaction.id)
        .all()
    )
    sells_by_isin: dict[str, list] = {}
    for tx in all_sells:
        sells_by_isin.setdefault(tx.isin, []).append(tx)

    # Latest price per ISIN
    latest_prices_q = (
        db.query(Transaction.isin, func.abs(Transaction.price).label("price"))
        .filter(Transaction.type.in_([TransactionType.BUY.value, TransactionType.SELL.value]))
        .filter(Transaction.isin.in_(div_isins))
        .order_by(Transaction.isin, Transaction.trade_date.desc())
        .all()
    )
    price_map: dict[str, Decimal] = {}
    for r in latest_prices_q:
        if r.isin not in price_map:
            price_map[r.isin] = Decimal(str(r.price))

    results = []
    for d in div_rows:
        isin = d.isin or ""
        total_div = Decimal(str(d.total_dividends or 0))

        buys = buys_by_isin.get(isin, [])
        sells = sells_by_isin.get(isin, [])
        div_dates = div_dates_by_isin.get(isin, [])

        # Calculate FIFO cost basis at each dividend date
        invested_at_dates = []
        for ddate in div_dates:
            # Buys up to this date
            buys_up_to = [
                (abs(tx.quantity), abs(tx.net_amount_eur))
                for tx in buys
                if tx.trade_date <= ddate
            ]
            # Total sold up to this date
            sold_up_to = sum(
                (abs(tx.quantity) for tx in sells if tx.trade_date <= ddate),
                Decimal("0"),
            )
            # FIFO: consume oldest buys with sells, sum remaining cost
            cost_at_date = Decimal("0")
            remaining_to_sell = sold_up_to
            for buy_qty, buy_cost in buys_up_to:
                if remaining_to_sell >= buy_qty:
                    remaining_to_sell -= buy_qty
                elif remaining_to_sell > 0:
                    kept = buy_qty - remaining_to_sell
                    cost_per_share = buy_cost / buy_qty if buy_qty else Decimal("0")
                    cost_at_date += kept * cost_per_share
                    remaining_to_sell = Decimal("0")
                else:
                    cost_at_date += buy_cost
            invested_at_dates.append(cost_at_date)

        # Average invested amount across dividend dates
        avg_invested = (
            sum(invested_at_dates, Decimal("0")) / len(invested_at_dates)
            if invested_at_dates
            else Decimal("0")
        )

        # Current position: total FIFO for qty_remaining and current_value
        total_sold = sum((abs(tx.quantity) for tx in sells), Decimal("0"))
        qty_remaining = Decimal("0")
        remaining_to_sell = total_sold
        for tx in buys:
            buy_qty = abs(tx.quantity)
            if remaining_to_sell >= buy_qty:
                remaining_to_sell -= buy_qty
            elif remaining_to_sell > 0:
                qty_remaining += buy_qty - remaining_to_sell
                remaining_to_sell = Decimal("0")
            else:
                qty_remaining += buy_qty

        latest_price = price_map.get(isin, Decimal("0"))
        current_value = abs(qty_remaining * latest_price) if qty_remaining else Decimal("0")

        yield_on_cost = (
            (total_div / avg_invested * 100) if avg_invested > 0 else Decimal("0")
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
                "total_invested": str(round(avg_invested, 2)),
                "qty_remaining": str(qty_remaining),
                "latest_price": str(latest_price),
                "current_value": str(round(current_value, 2)),
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
