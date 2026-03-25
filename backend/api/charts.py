"""Chart and analytics API endpoints."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import case, func

from backend.database import DbSession
from backend.models import TaxLot, Transaction, TransactionType

router = APIRouter(prefix="/charts", tags=["charts"])


@router.get("/dividends-by-country")
def dividends_by_country(
    db: DbSession,
    fiscal_year: int | None = None,
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
    db: DbSession,
    fiscal_year: int | None = None,
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
    db: DbSession,
    fiscal_year: int | None = None,
    limit: Annotated[int, Query(le=50)] = 10,
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
    db: DbSession,
    fiscal_year: int | None = None,
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
def patrimonio_composition(db: DbSession):
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


def _fifo_cost_basis(
    buys: list[tuple[Decimal, Decimal]], total_sold: Decimal,
) -> tuple[Decimal, Decimal]:
    """Compute FIFO cost basis and remaining qty after sells consume oldest buys.

    Args:
        buys: list of (quantity, cost) tuples ordered by date
        total_sold: total quantity sold to consume

    Returns:
        (cost_basis, qty_remaining) of unsold shares
    """
    cost_basis = Decimal("0")
    qty_remaining = Decimal("0")
    remaining = total_sold
    for buy_qty, buy_cost in buys:
        if remaining >= buy_qty:
            remaining -= buy_qty
        elif remaining > 0:
            kept = buy_qty - remaining
            cost_per_share = buy_cost / buy_qty if buy_qty else Decimal("0")
            cost_basis += kept * cost_per_share
            qty_remaining += kept
            remaining = Decimal("0")
        else:
            cost_basis += buy_cost
            qty_remaining += buy_qty
    return cost_basis, qty_remaining


def _avg_invested_at_dates(buys: list, sells: list, div_dates: list) -> Decimal:
    """Compute average FIFO cost basis at each dividend payment date."""
    invested_at_dates = []
    for ddate in div_dates:
        buys_up_to = [
            (abs(tx.quantity), abs(tx.net_amount_eur))
            for tx in buys if tx.trade_date <= ddate
        ]
        sold_up_to = sum(
            (abs(tx.quantity) for tx in sells if tx.trade_date <= ddate),
            Decimal("0"),
        )
        cost, _ = _fifo_cost_basis(buys_up_to, sold_up_to)
        invested_at_dates.append(cost)
    if not invested_at_dates:
        return Decimal("0")
    return sum(invested_at_dates, Decimal("0")) / len(invested_at_dates)


def _compute_isin_yield(
    d, buys_by_isin: dict, sells_by_isin: dict,
    div_dates_by_isin: dict, price_map: dict,
) -> dict:
    """Compute yield metrics for a single ISIN."""
    isin = d.isin or ""
    total_div = Decimal(str(d.total_dividends or 0))

    buys = buys_by_isin.get(isin, [])
    sells = sells_by_isin.get(isin, [])
    div_dates = div_dates_by_isin.get(isin, [])

    avg_invested = _avg_invested_at_dates(buys, sells, div_dates)

    total_sold = sum((abs(tx.quantity) for tx in sells), Decimal("0"))
    buy_pairs = [(abs(tx.quantity), abs(tx.net_amount_eur)) for tx in buys]
    _, qty_remaining = _fifo_cost_basis(buy_pairs, total_sold)

    latest_price = price_map.get(isin, Decimal("0"))
    current_value = abs(qty_remaining * latest_price) if qty_remaining else Decimal("0")

    yield_on_cost = (total_div / avg_invested * 100) if avg_invested > 0 else Decimal("0")
    yield_on_value = (total_div / current_value * 100) if current_value > 0 else Decimal("0")

    return {
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


def _group_transactions(txs: list) -> dict[str, list]:
    """Group a list of transactions by ISIN."""
    by_isin: dict[str, list] = {}
    for tx in txs:
        by_isin.setdefault(tx.isin, []).append(tx)
    return by_isin


def _first_per_key(rows, key_attr: str, val_attr: str) -> dict:
    """Build a dict mapping key → value, keeping only the first occurrence."""
    result: dict = {}
    for r in rows:
        k = getattr(r, key_attr)
        if k not in result:
            result[k] = Decimal(str(getattr(r, val_attr)))
    return result


@router.get("/dividend-yield")
def dividend_yield(
    db: DbSession,
    fiscal_year: int | None = None,
):
    """Dividend yield per ISIN: dividends vs avg invested at dividend dates.

    For each ISIN that paid dividends:
    - total_invested: average FIFO cost basis at each dividend payment date
    - qty_remaining: total bought - total sold (current position)
    - current_value: qty_remaining * latest price
    - yield_on_cost: dividends / avg_invested * 100
    - yield_on_value: dividends / current_holding_value * 100
    """
    # Get dividend totals by ISIN (group only by ISIN to merge broker name variants)
    div_q = db.query(
        Transaction.isin,
        func.max(Transaction.name).label("name"),
        func.max(Transaction.country).label("country"),
        func.sum(Transaction.gross_amount).label("total_dividends"),
        func.count().label("payment_count"),
    ).filter(Transaction.type == TransactionType.DIVIDEND.value)

    if fiscal_year:
        div_q = div_q.filter(func.strftime("%Y", Transaction.trade_date) == str(fiscal_year))

    div_rows = div_q.group_by(Transaction.isin).all()

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

    # Exclude synthetic transactions created by DEGIRO tax-lot import
    synthetic_buy_ids = db.query(TaxLot.buy_tx_id).subquery()
    synthetic_sell_ids = db.query(TaxLot.sell_tx_id).filter(TaxLot.sell_tx_id.isnot(None)).subquery()

    # Fetch all BUY transactions for these ISINs (ordered by date for FIFO)
    all_buys = (
        db.query(Transaction)
        .filter(
            Transaction.type == TransactionType.BUY.value,
            Transaction.isin.in_(div_isins),
            Transaction.id.notin_(synthetic_buy_ids),
        )
        .order_by(Transaction.isin, Transaction.trade_date, Transaction.id)
        .all()
    )
    buys_by_isin = _group_transactions(all_buys)

    # Fetch all SELL transactions for these ISINs (ordered by date for FIFO)
    all_sells = (
        db.query(Transaction)
        .filter(
            Transaction.type == TransactionType.SELL.value,
            Transaction.isin.in_(div_isins),
            Transaction.id.notin_(synthetic_sell_ids),
        )
        .order_by(Transaction.isin, Transaction.trade_date, Transaction.id)
        .all()
    )
    sells_by_isin = _group_transactions(all_sells)

    # Latest price per ISIN (exclude synthetic transactions)
    all_synthetic_ids = db.query(TaxLot.buy_tx_id).union(
        db.query(TaxLot.sell_tx_id).filter(TaxLot.sell_tx_id.isnot(None))
    ).subquery()
    latest_prices_q = (
        db.query(Transaction.isin, func.abs(Transaction.price).label("price"))
        .filter(Transaction.type.in_([TransactionType.BUY.value, TransactionType.SELL.value]))
        .filter(Transaction.isin.in_(div_isins))
        .filter(Transaction.id.notin_(all_synthetic_ids))
        .order_by(Transaction.isin, Transaction.trade_date.desc())
        .all()
    )
    price_map = _first_per_key(latest_prices_q, "isin", "price")

    results = [
        _compute_isin_yield(d, buys_by_isin, sells_by_isin, div_dates_by_isin, price_map)
        for d in div_rows
    ]
    results.sort(key=lambda x: float(x["yield_on_cost"]), reverse=True)
    return results


@router.get("/withholdings-by-country")
def withholdings_by_country(
    db: DbSession,
    fiscal_year: int | None = None,
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
