"""IBKR Activity Flex Query XML parser.

Produces the same `IBKRAnnualReport` as the Activity Statement CSV parser
(ibkr.py), so a synced year goes through `import_ibkr_report` unchanged and is
interchangeable with an uploaded CSV for that year. The principle carries over:
IBKR's realized P/L (FIFO performance summary in base) is the source of truth.

Differences from the CSV, all deliberate:
  - every row carries `fxRateToBase`, so amounts convert with IBKR's own rate
    for that row instead of the nearest forex trade;
  - only EUR-base accounts are accepted. "In Base" figures in another base
    currency would be imported as if they were euros;
  - the query layout is the user's, so required sections are checked up front
    and a missing one is named in the error instead of importing a partial year.

XML comes from IBKR over TLS and is parsed with the stdlib parser: expat ≥ 2.4.1
(bundled with Python 3.12) refuses entity expansion bombs and ElementTree never
fetches external entities.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from backend.importers.base import (
    IBKRAnnualReport,
    OptionAssignment,
    ParsedGainLoss,
    ParsedPortfolioHolding,
    ParsedTransaction,
    TxType,
    country_from_isin,
)
from backend.importers.ibkr import _apply_assignment_premiums

# Flex element → the name the user sees when configuring the query in IBKR.
REQUIRED_SECTIONS: dict[str, str] = {
    "AccountInformation": "Account Information",
    "Trades": "Trades",
    "OpenPositions": "Open Positions",
    "CashTransactions": "Cash Transactions",
    "FIFOPerformanceSummaryInBase": "Realized and Unrealized Performance Summary in Base",
}

_DATE_FORMATS = ("%Y%m%d", "%Y-%m-%d")

# Attributes every usable row of a section must carry. Flex lets the user pick
# fields one by one, and a field left out reads as 0 — a year imported with no
# proceeds or no realized P/L would replace a correct one without a word.
_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "Trades": ("assetCategory", "symbol", "currency", "quantity", "tradePrice", "proceeds",
               "ibCommission"),
    "OpenPositions": ("assetCategory", "symbol", "currency", "position", "positionValue"),
    "CashTransactions": ("type", "currency", "amount"),
    "FIFOPerformanceSummaryInBase": ("totalRealizedPnl",),
}
# Rows in another currency are converted with their own rate; without it they
# would be taken for euros.
_FX_SECTIONS = ("Trades", "OpenPositions", "CashTransactions")
# Cash types imported as dividends. A payment in lieu (paid by the borrower
# while the shares are lent out) sits in the CSV's Dividends section and is
# imported as a dividend there; Flex gives it a type of its own.
_DIVIDEND_TYPES = frozenset({"dividends", "payment in lieu of dividends"})
_DIV_DESC = re.compile(r"(\w+)\(([A-Z0-9]{12})\)")


class FlexQueryError(ValueError):
    """The query is set up in a way no year can be imported from (layout, base
    currency, date format). Retrying another year will not help; the user has
    to change the query in IBKR."""


@dataclass
class FlexStatement:
    report: IBKRAnnualReport
    date_opened: date | None
    from_date: date
    to_date: date


def _dec(value: str | None) -> Decimal:
    value = (value or "").strip().replace(",", "")
    if not value or value == "--":
        return Decimal("0")
    try:
        return Decimal(value)
    except InvalidOperation:
        return Decimal("0")


def _date(value: str | None) -> date | None:
    """Parse a Flex date or dateTime; None when empty.

    The date format is a setting of the user's query. yyyyMMdd (the default)
    and yyyy-MM-dd are accepted; anything else is ambiguous (dd/MM vs MM/dd).
    """
    raw = (value or "").strip()
    if not raw:
        return None
    for sep in (";", ",", " ", "T"):
        raw = raw.split(sep)[0]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise FlexQueryError(
        f"Formato de fecha no admitido en la Flex Query ({value!r}). "
        "Configura la fecha como yyyyMMdd en la entrega de la consulta."
    )


def _rows(section: ET.Element | None) -> list[ET.Element]:
    return list(section) if section is not None else []


def _fx(el: ET.Element) -> Decimal:
    """EUR per unit of the row's currency. Only EUR rows may lack it (`_check_fields`)."""
    rate = _dec(el.get("fxRateToBase"))
    return rate if rate > 0 else Decimal("1")


def _statement_element(xml_text: str) -> ET.Element:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        raise FlexQueryError("El informe de IBKR no es un XML válido.") from None
    if root.tag != "FlexQueryResponse":
        raise FlexQueryError("El informe de IBKR no es una respuesta de Flex Query.")
    statements = root.findall("./FlexStatements/FlexStatement")
    if len(statements) != 1:
        raise FlexQueryError(
            f"La Flex Query devuelve {len(statements)} cuentas; "
            "configúrala para una sola cuenta."
        )
    return statements[0]


def _check_sections(stmt: ET.Element) -> None:
    missing = [label for tag, label in REQUIRED_SECTIONS.items() if stmt.find(tag) is None]
    if missing:
        raise FlexQueryError(
            "A la Flex Query le faltan secciones: " + ", ".join(missing)
            + ". Añádelas en el Portal de Clientes de IBKR."
        )


def _check_fields(stmt: ET.Element) -> None:
    """Every section must carry the levels and fields its numbers come from."""
    usable = {
        "Trades": _trade_rows(stmt),
        "OpenPositions": _position_rows(stmt),
        "CashTransactions": _cash_rows(stmt),
        "FIFOPerformanceSummaryInBase": _rows(stmt.find("FIFOPerformanceSummaryInBase")),
    }
    levels = {
        "Trades": "Execution",
        "OpenPositions": "Summary",
        "CashTransactions": "Detail",
    }
    for tag, level in levels.items():
        if _rows(stmt.find(tag)) and not usable[tag]:
            raise FlexQueryError(
                f"La sección {REQUIRED_SECTIONS[tag]} de la Flex Query no incluye el nivel "
                f"{level}. Márcalo en la configuración de la consulta en IBKR."
            )
    for tag, fields in _REQUIRED_FIELDS.items():
        missing = {f for el in usable[tag] for f in fields if el.get(f) is None}
        if tag in _FX_SECTIONS:
            missing |= {
                "fxRateToBase"
                for el in usable[tag]
                if el.get("currency", "EUR") != "EUR" and not el.get("fxRateToBase")
            }
        if missing:
            raise FlexQueryError(
                f"A la sección {REQUIRED_SECTIONS[tag]} de la Flex Query le faltan campos: "
                + ", ".join(sorted(missing))
                + ". Selecciona todos los campos de la sección en IBKR."
            )


def read_date_opened(xml_text: str) -> date | None:
    """The account's opening date, or None. Never raises: it is read even from a
    statement that failed to parse, so a bad year cannot hide where history starts."""
    try:
        info = ET.fromstring(xml_text).find("./FlexStatements/FlexStatement/AccountInformation")
        return _date(info.get("dateOpened")) if info is not None else None
    except (ET.ParseError, ValueError):
        return None


def _symbol_isin_map(stmt: ET.Element) -> dict[str, str]:
    mapping: dict[str, str] = {}
    sources = (
        _rows(stmt.find("SecuritiesInfo"))
        + _rows(stmt.find("OpenPositions"))
        + _rows(stmt.find("Trades"))
    )
    for el in sources:
        if el.get("assetCategory") != "STK":
            continue
        isin = (el.get("isin") or "").strip()
        symbol = (el.get("symbol") or "").strip()
        if symbol and len(isin) == 12:
            mapping.setdefault(symbol, isin)
    return mapping


def _trade_rows(stmt: ET.Element) -> list[ET.Element]:
    """One row per execution, or per order when the query has no executions.

    A query may include executions, orders and closed lots at once; taking more
    than one level would count the same trade twice.
    """
    rows = _rows(stmt.find("Trades"))
    executions = [r for r in rows if (r.get("levelOfDetail") or "").upper() == "EXECUTION"]
    if executions:
        return executions
    return [r for r in rows if (r.get("levelOfDetail") or "").upper() == "ORDER"]


def _position_rows(stmt: ET.Element) -> list[ET.Element]:
    return [
        r for r in _rows(stmt.find("OpenPositions"))
        if (r.get("levelOfDetail") or "").upper() != "LOT"
    ]


def _option_name(el: ET.Element) -> str:
    return f"[OPT] {(el.get('description') or el.get('symbol') or '').strip()}"


def _parse_trade(el: ET.Element, symbol_isin: dict[str, str]) -> ParsedTransaction | None:
    category = el.get("assetCategory") or ""
    if category == "CASH":
        return None  # forex conversions are not securities trades
    trade_dt = _date(el.get("tradeDate") or el.get("dateTime"))
    symbol = (el.get("symbol") or "").strip()
    if trade_dt is None or not symbol:
        return None

    quantity = _dec(el.get("quantity"))
    tx_type = TxType.BUY if quantity > 0 else TxType.SELL
    fx = _fx(el)
    proceeds_eur = abs(_dec(el.get("proceeds"))) * fx
    commission_eur = abs(_dec(el.get("ibCommission"))) * fx
    net_amount_eur = (
        proceeds_eur + commission_eur if tx_type == TxType.BUY else proceeds_eur - commission_eur
    )

    if category == "OPT":
        isin, name = "", _option_name(el)
    else:
        isin = (el.get("isin") or "").strip() or symbol_isin.get(symbol, "")
        name = symbol

    return ParsedTransaction(
        tx_type=tx_type,
        trade_date=trade_dt,
        isin=isin,
        name=name,
        country=country_from_isin(isin),
        quantity=abs(quantity),
        price=abs(_dec(el.get("tradePrice"))),
        currency=el.get("currency") or "EUR",
        exchange_rate=fx,
        gross_amount=proceeds_eur,
        fees=commission_eur,
        net_amount_eur=net_amount_eur,
        realized_pl_eur=_dec(el.get("fifoPnlRealized")) * fx,
    )


def _codes(el: ET.Element) -> set[str]:
    codes = {c.strip() for c in (el.get("notes") or "").split(";") if c.strip()}
    if el.get("openCloseIndicator"):
        codes.add(el.get("openCloseIndicator", "").strip())
    return codes


def _detect_assignments(
    rows: list[ET.Element], symbol_isin: dict[str, str]
) -> list[OptionAssignment]:
    """Assigned options and the stock leg each one produced (mirrors ibkr.py).

    The option close carries codes A and C; its `cost` is the premium IBKR
    embeds in the stock's basis. The stock leg must be the unique trade with
    code A on the same day, symbol, direction, quantity and price.
    """
    option_closes = []
    stock_legs = []
    for el in rows:
        codes = _codes(el)
        if "A" not in codes:
            continue
        trade_dt = _date(el.get("tradeDate") or el.get("dateTime"))
        if trade_dt is None:
            continue
        category = el.get("assetCategory")
        if category == "OPT" and "C" in codes:
            opt_type = (el.get("putCall") or "").upper()
            if opt_type not in {"P", "C"}:
                raise ValueError(f"Tipo de opción no válido en asignación: {el.get('symbol')}")
            multiplier = _dec(el.get("multiplier")) or Decimal("100")
            underlying = (
                el.get("underlyingSymbol") or (el.get("symbol") or "").split()[0]
            ).strip()
            option_closes.append({
                "underlying": underlying,
                "trade_date": trade_dt,
                "option_symbol": (el.get("description") or el.get("symbol") or "").strip(),
                "option_type": opt_type,
                "strike": _dec(el.get("strike")),
                "stock_quantity": abs(_dec(el.get("quantity"))) * multiplier,
                "premium_eur": abs(_dec(el.get("cost"))) * _fx(el),
            })
        elif category == "STK":
            stock_legs.append({
                "symbol": (el.get("symbol") or "").strip(),
                "trade_date": trade_dt,
                "quantity": _dec(el.get("quantity")),
                "price": abs(_dec(el.get("tradePrice"))),
            })

    assignments: list[OptionAssignment] = []
    used: set[int] = set()
    for option in option_closes:
        expected_sign = 1 if option["option_type"] == "P" else -1
        candidates = [
            i
            for i, stock in enumerate(stock_legs)
            if i not in used
            and stock["symbol"] == option["underlying"]
            and stock["trade_date"] == option["trade_date"]
            and (1 if stock["quantity"] > 0 else -1) == expected_sign
            and abs(stock["quantity"]) == option["stock_quantity"]
            and stock["price"] == option["strike"]
        ]
        if len(candidates) != 1:
            raise ValueError(
                "No se pudo identificar de forma unívoca la pata de acciones "
                f"para la asignación {option['option_symbol']} "
                f"del {option['trade_date']}: {len(candidates)} coincidencias"
            )
        used.add(candidates[0])
        assignments.append(OptionAssignment(
            assignment_date=option["trade_date"],
            underlying=option["underlying"],
            option_symbol=option["option_symbol"],
            option_type=option["option_type"],
            strike=option["strike"],
            stock_quantity=option["stock_quantity"],
            stock_isin=symbol_isin.get(option["underlying"], ""),
            premium_eur=option["premium_eur"],
        ))
    return assignments


def _cash_rows(stmt: ET.Element) -> list[ET.Element]:
    return [
        r for r in _rows(stmt.find("CashTransactions"))
        if (r.get("levelOfDetail") or "").upper() != "SUMMARY"
    ]


def _cash_date(el: ET.Element) -> date | None:
    return _date(el.get("dateTime") or el.get("settleDate") or el.get("reportDate"))


def _cash_symbol_isin(el: ET.Element, symbol_isin: dict[str, str]) -> tuple[str, str]:
    """(symbol, ISIN) of a cash row; the description carries "SYM(ISIN) ..." as in the CSV."""
    symbol = (el.get("symbol") or "").strip()
    isin = (el.get("isin") or "").strip()
    m = _DIV_DESC.match((el.get("description") or "").strip())
    if m:
        symbol = symbol or m.group(1)
        isin = isin or m.group(2)
    return symbol, isin or symbol_isin.get(symbol, "")


def _withholding_key(
    el: ET.Element, day: date, symbol_isin: dict[str, str]
) -> tuple[str, date, str]:
    """Keyed by symbol like the CSV parser, so a row with an ISIN still meets one without."""
    symbol, isin = _cash_symbol_isin(el, symbol_isin)
    return (el.get("currency") or "", day, symbol or isin)


def _extract_dividends(stmt: ET.Element, symbol_isin: dict[str, str]) -> list[ParsedTransaction]:
    rows = _cash_rows(stmt)
    withheld: dict[tuple[str, date, str], Decimal] = {}
    for el in rows:
        if el.get("type") != "Withholding Tax":
            continue
        day = _cash_date(el)
        if day is None:
            continue
        key = _withholding_key(el, day, symbol_isin)
        # Summed, not overwritten: IBKR posts corrections as extra rows on the same day.
        withheld[key] = withheld.get(key, Decimal("0")) + _dec(el.get("amount"))

    payouts = [
        (el, day)
        for el in rows
        if (el.get("type") or "").strip().lower() in _DIVIDEND_TYPES
        and (day := _cash_date(el)) is not None
    ]
    # An ordinary dividend and a payment in lieu can share a day and a symbol,
    # and IBKR's withholding rows cannot be told apart by key: split the
    # withholding by amount so it is counted once, not once per payout.
    paid: dict[tuple[str, date, str], Decimal] = {}
    first_of_key: dict[tuple[str, date, str], int] = {}
    for i, (el, day) in enumerate(payouts):
        key = _withholding_key(el, day, symbol_isin)
        paid[key] = paid.get(key, Decimal("0")) + _dec(el.get("amount"))
        first_of_key.setdefault(key, i)

    dividends: list[ParsedTransaction] = []
    for i, (el, day) in enumerate(payouts):
        symbol, isin = _cash_symbol_isin(el, symbol_isin)
        amount = _dec(el.get("amount"))
        key = _withholding_key(el, day, symbol_isin)
        total_wht = abs(withheld.get(key, Decimal("0")))
        if paid[key]:
            wht = total_wht * amount / paid[key]
        else:
            # Payouts that net to zero (a reversal): keep the withholding on one row.
            wht = total_wht if i == first_of_key[key] else Decimal("0")
        fx = _fx(el)
        amount_eur = amount * fx
        wht_eur = wht * fx
        desc = (el.get("description") or "").strip()
        dividends.append(ParsedTransaction(
            tx_type=TxType.DIVIDEND,
            trade_date=day,
            isin=isin,
            name=f"{symbol} - {desc}" if symbol else desc,
            country=country_from_isin(isin),
            quantity=Decimal("1"),
            price=amount,
            currency=el.get("currency") or "EUR",
            exchange_rate=fx,
            gross_amount=amount_eur,
            fees=Decimal("0"),
            net_amount_eur=amount_eur - wht_eur,
            withholding_tax=wht_eur,
            domestic_withholding_tax=Decimal("0"),
            foreign_withholding_tax=wht_eur,
            withholding_rate=(wht / amount * 100) if amount else None,
        ))
    return dividends


def _extract_interest(stmt: ET.Element) -> list[ParsedTransaction]:
    interest: list[ParsedTransaction] = []
    for el in _cash_rows(stmt):
        kind = el.get("type") or ""
        if "Interest" not in kind:
            continue
        day = _cash_date(el)
        if day is None:
            continue
        amount_eur = _dec(el.get("amount")) * _fx(el)
        interest.append(ParsedTransaction(
            tx_type=TxType.INTEREST,
            trade_date=day,
            isin="",
            name=(el.get("description") or kind).strip(),
            country="",
            quantity=Decimal("1"),
            price=_dec(el.get("amount")),
            currency=el.get("currency") or "EUR",
            exchange_rate=_fx(el),
            gross_amount=amount_eur,
            fees=Decimal("0"),
            net_amount_eur=amount_eur,
        ))
    return interest


def _extract_holdings(
    stmt: ET.Element, symbol_isin: dict[str, str]
) -> list[ParsedPortfolioHolding]:
    holdings: list[ParsedPortfolioHolding] = []
    for el in _position_rows(stmt):
        if el.get("assetCategory") != "STK":
            continue  # only stocks for Modelo 714, as in the CSV parser
        symbol = (el.get("symbol") or "").strip()
        isin = (el.get("isin") or "").strip() or symbol_isin.get(symbol, "")
        value_eur = _dec(el.get("positionValue")) * _fx(el)
        quantity = _dec(el.get("position"))
        holdings.append(ParsedPortfolioHolding(
            isin=isin,
            name=symbol,
            currency=el.get("currency") or "EUR",
            asset_type="Acciones",
            country=country_from_isin(isin),
            casilla_714=0,
            quantity=quantity,
            avg_q4_balance=quantity,
            value_dec31_eur=value_eur,
            fiscal_valuation=value_eur,
            price=_dec(el.get("markPrice")),
            exchange="IBKR",
        ))
    return holdings


def _extract_realized(stmt: ET.Element, symbol_isin: dict[str, str]) -> list[ParsedGainLoss]:
    """Realized P/L per instrument, already in base (EUR). Source of truth for gains."""
    gains: list[ParsedGainLoss] = []
    for el in _rows(stmt.find("FIFOPerformanceSummaryInBase")):
        category = el.get("assetCategory") or ""
        symbol = (el.get("symbol") or "").strip()
        if not category or not symbol:
            continue  # total rows
        realized = _dec(el.get("totalRealizedPnl"))
        if realized == 0:
            continue
        if category == "OPT":
            isin, name = "", _option_name(el)
        elif category == "CASH":
            isin, name = "", f"[FX] {symbol}"
        else:
            isin = (el.get("isin") or "").strip() or symbol_isin.get(symbol, "")
            name = symbol
        gains.append(ParsedGainLoss(
            isin=isin,
            name=name,
            realized_pl_eur=realized,
            commission_eur=Decimal("0"),
            transaction_tax_eur=Decimal("0"),
        ))
    return gains


def parse_ibkr_flex(xml_text: str) -> FlexStatement:
    """Parse one Activity Flex Query statement (one account, one calendar year)."""
    stmt = _statement_element(xml_text)
    _check_sections(stmt)
    _check_fields(stmt)

    info = stmt.find("AccountInformation")
    assert info is not None  # checked above
    base_currency = (info.get("currency") or "").strip()
    if base_currency != "EUR":
        raise FlexQueryError(
            f"La cuenta de IBKR tiene divisa base {base_currency or 'desconocida'}; "
            "por ahora solo se admiten cuentas en EUR."
        )

    from_date = _date(stmt.get("fromDate"))
    to_date = _date(stmt.get("toDate"))
    if from_date is None or to_date is None or from_date.year != to_date.year:
        raise FlexQueryError("El periodo del informe de IBKR debe estar dentro de un mismo año.")

    symbol_isin = _symbol_isin_map(stmt)
    trade_rows = _trade_rows(stmt)
    trades = [t for t in (_parse_trade(r, symbol_isin) for r in trade_rows) if t]
    assignments = _detect_assignments(trade_rows, symbol_isin)
    _apply_assignment_premiums(trades, assignments)

    report = IBKRAnnualReport(
        account_id=(info.get("accountId") or stmt.get("accountId") or "").strip(),
        account_name=(info.get("name") or "").strip(),
        fiscal_year=to_date.year,
        base_currency=base_currency,
        trades=trades,
        dividends=_extract_dividends(stmt, symbol_isin),
        interest=_extract_interest(stmt),
        holdings=_extract_holdings(stmt, symbol_isin),
        realized_gains=_extract_realized(stmt, symbol_isin),
        assignments=assignments,
        symbol_isin_map=symbol_isin,
    )
    if not report.account_id:
        raise FlexQueryError("El informe de IBKR no incluye el número de cuenta.")
    return FlexStatement(
        report=report,
        date_opened=_date(info.get("dateOpened")),
        from_date=from_date,
        to_date=to_date,
    )
