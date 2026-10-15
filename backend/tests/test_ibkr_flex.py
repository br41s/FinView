"""IBKR Flex Web Service: the XML parser and the HTTP client.

The parser is checked against a hand-built statement that uses Flex's attribute
names. It is not a real IBKR file: parity with an uploaded Activity Statement
for the same year is the open check listed in tasks/todo.md.

The client talks to IBKR with the token in the query string (IBKR's design), so
the ugly paths below also pin that the token never reaches an error message or
a log line.
"""

import logging
from datetime import date
from decimal import Decimal

import httpx
import pytest

from backend.importers.base import TxType
from backend.importers.ibkr_flex import FlexQueryError, parse_ibkr_flex
from backend.services import ibkr_flex
from backend.services.ibkr_flex import FlexError

TOKEN = "123456789012345678901234"


def flex_xml(
    *,
    base="EUR",
    from_date="20250101",
    to_date="20251231",
    date_opened='dateOpened="20190312"',
    sections: dict[str, str] | None = None,
    statements: int = 1,
) -> str:
    body = {
        "AccountInformation": (
            f'<AccountInformation accountId="U1234567" name="Test User" currency="{base}" '
            f"{date_opened} />"
        ),
        "Trades": """<Trades>
  <Trade levelOfDetail="EXECUTION" assetCategory="STK" symbol="AAPL" isin="US0378331005"
    currency="USD" fxRateToBase="0.9" tradeDate="20250115" quantity="10" tradePrice="150"
    proceeds="-1500" ibCommission="-1" fifoPnlRealized="0" notes="" openCloseIndicator="O" />
  <Order levelOfDetail="ORDER" assetCategory="STK" symbol="AAPL" isin="US0378331005"
    currency="USD" fxRateToBase="0.9" tradeDate="20250115" quantity="10" tradePrice="150"
    proceeds="-1500" ibCommission="-1" />
  <Trade levelOfDetail="EXECUTION" assetCategory="STK" symbol="AAPL" isin="US0378331005"
    currency="USD" fxRateToBase="0.95" tradeDate="20250601" quantity="-4" tradePrice="200"
    proceeds="800" ibCommission="-1" fifoPnlRealized="199" notes="" openCloseIndicator="C" />
  <Trade levelOfDetail="EXECUTION" assetCategory="CASH" symbol="EUR.USD" currency="USD"
    fxRateToBase="0.9" tradeDate="20250114" quantity="1000" tradePrice="1.1" proceeds="-1100"
    ibCommission="-2" />
  <Trade levelOfDetail="EXECUTION" assetCategory="OPT" symbol="ADM   250321P00050000"
    description="ADM 21MAR25 50 P" underlyingSymbol="ADM" putCall="P" strike="50"
    multiplier="100" currency="USD" fxRateToBase="0.9" tradeDate="20250321" quantity="1"
    tradePrice="0" proceeds="0" ibCommission="0" cost="-120" notes="A"
    openCloseIndicator="C" />
  <Trade levelOfDetail="EXECUTION" assetCategory="STK" symbol="ADM" isin="US0394831020"
    currency="USD" fxRateToBase="0.9" tradeDate="20250321" quantity="100" tradePrice="50"
    proceeds="-5000" ibCommission="0" notes="A" openCloseIndicator="O" />
  <Lot levelOfDetail="CLOSED_LOT" assetCategory="STK" symbol="AAPL" isin="US0378331005"
    currency="USD" tradeDate="20250115" quantity="4" />
</Trades>""",
        "OpenPositions": """<OpenPositions>
  <OpenPosition levelOfDetail="SUMMARY" assetCategory="STK" symbol="AAPL" isin="US0378331005"
    currency="USD" fxRateToBase="0.92" position="6" markPrice="210" positionValue="1260" />
  <OpenPosition levelOfDetail="LOT" assetCategory="STK" symbol="AAPL" isin="US0378331005"
    currency="USD" fxRateToBase="0.92" position="6" markPrice="210" positionValue="1260" />
  <OpenPosition levelOfDetail="SUMMARY" assetCategory="OPT" symbol="X" currency="USD"
    fxRateToBase="0.92" position="1" markPrice="0.1" positionValue="10" />
</OpenPositions>""",
        "CashTransactions": """<CashTransactions>
  <CashTransaction levelOfDetail="DETAIL" type="Dividends" symbol="AAPL" isin="US0378331005"
    currency="USD" fxRateToBase="0.9" dateTime="20250215;202000" amount="10"
    description="AAPL(US0378331005) Cash Dividend USD 0.25 per Share (Ordinary Dividend)" />
  <CashTransaction levelOfDetail="DETAIL" type="Withholding Tax" symbol="AAPL"
    isin="US0378331005" currency="USD" fxRateToBase="0.9" dateTime="20250215;202000"
    amount="-1.5" description="AAPL US TAX" />
  <CashTransaction levelOfDetail="DETAIL" type="Withholding Tax" symbol="AAPL"
    isin="US0378331005" currency="USD" fxRateToBase="0.9" dateTime="20250215;202000"
    amount="0.5" description="AAPL US TAX correction" />
  <CashTransaction levelOfDetail="SUMMARY" type="Dividends" currency="USD" fxRateToBase="0.9"
    amount="10" />
  <CashTransaction levelOfDetail="DETAIL" type="Broker Interest Received" currency="EUR"
    fxRateToBase="1" dateTime="20250304" amount="3.21"
    description="EUR CREDIT INT FOR FEB-2025" />
  <CashTransaction levelOfDetail="DETAIL" type="Deposits/Withdrawals" currency="EUR"
    fxRateToBase="1" dateTime="20250101" amount="5000" />
</CashTransactions>""",
        "FIFOPerformanceSummaryInBase": """<FIFOPerformanceSummaryInBase>
  <FIFOPerformanceSummaryUnderlying assetCategory="STK" symbol="AAPL" isin="US0378331005"
    totalRealizedPnl="189.05" />
  <FIFOPerformanceSummaryUnderlying assetCategory="OPT" symbol="ADM   250321P00050000"
    description="ADM 21MAR25 50 P" totalRealizedPnl="0" />
  <FIFOPerformanceSummaryUnderlying assetCategory="CASH" symbol="USD"
    totalRealizedPnl="-3.2" />
  <FIFOPerformanceSummaryUnderlying assetCategory="" symbol="" description="Total"
    totalRealizedPnl="185.85" />
</FIFOPerformanceSummaryInBase>""",
    }
    for tag, xml in (sections or {}).items():
        if xml is None:
            body.pop(tag)
        else:
            body[tag] = xml
    inner = "\n".join(body.values())
    statement = (
        f'<FlexStatement accountId="U1234567" fromDate="{from_date}" toDate="{to_date}" '
        f'period="Custom">\n{inner}\n</FlexStatement>'
    )
    return (
        f'<FlexQueryResponse queryName="finview" type="AF">'
        f'<FlexStatements count="{statements}">'
        + statement * statements
        + "</FlexStatements></FlexQueryResponse>"
    )


# ── parser ───────────────────────────────────────────────────────────


@pytest.fixture
def parsed():
    return parse_ibkr_flex(flex_xml())


def test_statement_identity(parsed):
    report = parsed.report
    assert report.account_id == "U1234567"
    assert report.base_currency == "EUR"
    assert report.fiscal_year == 2025
    assert parsed.date_opened == date(2019, 3, 12)
    assert (parsed.from_date, parsed.to_date) == (date(2025, 1, 1), date(2025, 12, 31))


def test_one_row_per_execution_no_forex_no_orders_no_lots(parsed):
    # 2 AAPL + 1 OPT + 1 ADM; the ORDER, CLOSED_LOT and CASH rows are not trades.
    assert len(parsed.report.trades) == 4
    assert not any(t.name.startswith("EUR") for t in parsed.report.trades)


def test_orders_are_used_when_the_query_has_no_executions():
    trades = """<Trades>
  <Order levelOfDetail="ORDER" assetCategory="STK" symbol="AAPL" isin="US0378331005"
    currency="EUR" tradeDate="20250115" quantity="2" tradePrice="10" proceeds="-20"
    ibCommission="-1" />
</Trades>"""
    report = parse_ibkr_flex(flex_xml(sections={"Trades": trades})).report
    assert len(report.trades) == 1
    assert report.trades[0].net_amount_eur == Decimal("21")


def test_trades_convert_with_the_rows_own_rate(parsed):
    buy, sell = [t for t in parsed.report.trades if t.name == "AAPL"]
    assert buy.tx_type == TxType.BUY
    assert buy.quantity == Decimal("10")
    assert buy.exchange_rate == Decimal("0.9")
    # BUY = gross + fees, SELL = gross − fees (CLAUDE.md cash semantics)
    assert buy.net_amount_eur == Decimal("1350.9")
    assert sell.tx_type == TxType.SELL
    assert sell.net_amount_eur == Decimal("759.05")
    assert sell.realized_pl_eur == Decimal("189.05")


def test_option_trade_has_no_isin(parsed):
    option = next(t for t in parsed.report.trades if t.name.startswith("[OPT]"))
    assert option.isin == ""
    assert option.name == "[OPT] ADM 21MAR25 50 P"


def test_assigned_put_premium_reduces_the_stock_cost(parsed):
    (assignment,) = parsed.report.assignments
    assert assignment.option_type == "P"
    assert assignment.underlying == "ADM"
    assert assignment.stock_quantity == Decimal("100")
    assert assignment.premium_eur == Decimal("108.0")
    stock = next(t for t in parsed.report.trades if t.name == "ADM")
    assert stock.net_amount_eur == Decimal("4500") - Decimal("108.0")


def test_ambiguous_assignment_fails_instead_of_guessing():
    trades = """<Trades>
  <Trade levelOfDetail="EXECUTION" assetCategory="OPT" symbol="ADM P" underlyingSymbol="ADM"
    putCall="P" strike="50" multiplier="100" currency="USD" fxRateToBase="0.9"
    tradeDate="20250321" quantity="1" tradePrice="0" proceeds="0" ibCommission="0"
    cost="-120" notes="A" openCloseIndicator="C" />
</Trades>"""
    with pytest.raises(ValueError, match="unívoca") as exc:
        parse_ibkr_flex(flex_xml(sections={"Trades": trades}))
    assert not isinstance(exc.value, FlexQueryError)  # one year's problem, not the query's


def test_dividend_with_summed_withholding(parsed):
    (div,) = parsed.report.dividends
    assert div.trade_date == date(2025, 2, 15)
    assert div.isin == "US0378331005"
    assert div.gross_amount == Decimal("9.0")
    # −1.5 withheld, +0.5 corrected the same day → 1.0 USD, 0.9 EUR
    assert div.withholding_tax == Decimal("0.90")
    assert div.foreign_withholding_tax == Decimal("0.90")
    assert div.net_amount_eur == Decimal("8.10")
    assert div.withholding_rate == Decimal("10")


def test_interest_only_interest_rows(parsed):
    (interest,) = parsed.report.interest
    assert interest.gross_amount == Decimal("3.21")
    assert interest.tx_type == TxType.INTEREST


def test_holdings_are_stock_summaries_in_eur(parsed):
    (holding,) = parsed.report.holdings
    assert holding.isin == "US0378331005"
    assert holding.quantity == Decimal("6")
    assert holding.value_dec31_eur == Decimal("1159.20")


def test_realized_gains_skip_totals_and_zeros(parsed):
    gains = {g.name: g.realized_pl_eur for g in parsed.report.realized_gains}
    assert gains == {"AAPL": Decimal("189.05"), "[FX] USD": Decimal("-3.2")}


def test_dashed_dates_are_accepted():
    xml = flex_xml(from_date="2025-01-01", to_date="2025-06-30")
    xml = xml.replace('tradeDate="20250115"', 'tradeDate="2025-01-15"')
    assert parse_ibkr_flex(xml).to_date == date(2025, 6, 30)


def test_ambiguous_date_format_is_a_query_error():
    with pytest.raises(FlexQueryError, match="yyyyMMdd"):
        parse_ibkr_flex(flex_xml(from_date="01/02/2025", to_date="31/12/2025"))


def test_missing_section_is_named():
    with pytest.raises(FlexQueryError, match="Open Positions"):
        parse_ibkr_flex(flex_xml(sections={"OpenPositions": None}))


def test_non_eur_base_is_refused():
    with pytest.raises(FlexQueryError, match="USD"):
        parse_ibkr_flex(flex_xml(base="USD"))


def test_multi_account_query_is_refused():
    with pytest.raises(FlexQueryError, match="2 cuentas"):
        parse_ibkr_flex(flex_xml(statements=2))


def test_period_across_years_is_refused():
    with pytest.raises(FlexQueryError, match="mismo año"):
        parse_ibkr_flex(flex_xml(from_date="20240601", to_date="20250531"))


def test_garbage_is_a_query_error():
    with pytest.raises(FlexQueryError):
        parse_ibkr_flex("<html>Maintenance</html>")


def _without(xml: str, attribute: str) -> str:
    import re
    return re.sub(rf'\s{attribute}="[^"]*"', "", xml)


@pytest.mark.parametrize(
    ("attribute", "section"),
    [("proceeds", "Trades"), ("amount", "Cash Transactions"),
     ("totalRealizedPnl", "Realized and Unrealized"), ("positionValue", "Open Positions")],
)
def test_a_missing_field_is_named_instead_of_read_as_zero(attribute, section):
    with pytest.raises(FlexQueryError, match=attribute) as exc:
        parse_ibkr_flex(_without(flex_xml(), attribute))
    assert section in str(exc.value)


def test_a_foreign_row_without_its_rate_is_not_taken_for_euros():
    with pytest.raises(FlexQueryError, match="fxRateToBase"):
        parse_ibkr_flex(_without(flex_xml(), "fxRateToBase"))


def test_eur_rows_need_no_rate():
    trades = """<Trades>
  <Trade levelOfDetail="EXECUTION" assetCategory="STK" symbol="SAN" isin="ES0113900J37"
    currency="EUR" tradeDate="20250115" quantity="2" tradePrice="10" proceeds="-20"
    ibCommission="-1" />
</Trades>"""
    report = parse_ibkr_flex(flex_xml(sections={"Trades": trades})).report
    assert report.trades[0].net_amount_eur == Decimal("21")


@pytest.mark.parametrize(
    ("tag", "rows", "level"),
    [
        ("Trades", '<Trades><Lot levelOfDetail="CLOSED_LOT" symbol="A" /></Trades>', "Execution"),
        ("CashTransactions",
         '<CashTransactions><CashTransaction levelOfDetail="SUMMARY" type="Dividends" '
         'currency="EUR" amount="1" /></CashTransactions>', "Detail"),
        ("OpenPositions",
         '<OpenPositions><OpenPosition levelOfDetail="LOT" /></OpenPositions>', "Summary"),
    ],
)
def test_a_section_with_rows_but_no_usable_level_is_refused(tag, rows, level):
    with pytest.raises(FlexQueryError, match=level):
        parse_ibkr_flex(flex_xml(sections={tag: rows}))


def test_dividend_isin_comes_from_the_description_like_the_csv():
    cash = """<CashTransactions>
  <CashTransaction levelOfDetail="DETAIL" type="Dividends" symbol="" currency="EUR"
    dateTime="20250215" amount="10" description="MAP(ES0124244E34) Cash Dividend EUR 0.10" />
  <CashTransaction levelOfDetail="DETAIL" type="Withholding Tax" symbol="MAP"
    currency="EUR" dateTime="20250215" amount="-1.9" description="MAP ES TAX" />
</CashTransactions>"""
    (div,) = parse_ibkr_flex(flex_xml(sections={"CashTransactions": cash})).report.dividends
    assert div.isin == "ES0124244E34"
    assert div.country == "España"
    assert div.withholding_tax == Decimal("1.9")


def test_payment_in_lieu_is_a_dividend_like_in_the_csv():
    cash = """<CashTransactions>
  <CashTransaction levelOfDetail="DETAIL" type="Payment In Lieu Of Dividends" symbol="IBKR"
    isin="US45841N1072" currency="USD" fxRateToBase="0.9" dateTime="20250314" amount="0.63"
    description="IBKR(US45841N1072) Payment in Lieu of Dividend (Ordinary Dividend)" />
  <CashTransaction levelOfDetail="DETAIL" type="Withholding Tax" symbol="IBKR"
    isin="US45841N1072" currency="USD" fxRateToBase="0.9" dateTime="20250314" amount="-0.09"
    description="IBKR(US45841N1072) Payment in Lieu of Dividend - US Tax" />
</CashTransactions>"""
    (div,) = parse_ibkr_flex(flex_xml(sections={"CashTransactions": cash})).report.dividends
    assert div.tx_type == TxType.DIVIDEND
    assert div.isin == "US45841N1072"
    assert div.gross_amount == Decimal("0.567")
    assert div.withholding_tax == Decimal("0.081")


def test_same_day_dividend_and_payment_in_lieu_split_the_withholding():
    """One withholding row per key: counted once in total, not once per payout."""
    cash = """<CashTransactions>
  <CashTransaction levelOfDetail="DETAIL" type="Dividends" symbol="IBKR" currency="USD"
    fxRateToBase="1" dateTime="20250314" amount="3" description="IBKR Cash Dividend" />
  <CashTransaction levelOfDetail="DETAIL" type="Payment In Lieu Of Dividends" symbol="IBKR"
    currency="USD" fxRateToBase="1" dateTime="20250314" amount="1"
    description="IBKR Payment in Lieu of Dividend" />
  <CashTransaction levelOfDetail="DETAIL" type="Withholding Tax" symbol="IBKR" currency="USD"
    fxRateToBase="1" dateTime="20250314" amount="-0.6" description="IBKR US Tax" />
</CashTransactions>"""
    divs = parse_ibkr_flex(flex_xml(sections={"CashTransactions": cash})).report.dividends
    assert [d.withholding_tax for d in divs] == [Decimal("0.45"), Decimal("0.15")]
    assert sum(d.withholding_tax for d in divs) == Decimal("0.6")


def test_a_reversed_dividend_keeps_its_withholding_once():
    cash = """<CashTransactions>
  <CashTransaction levelOfDetail="DETAIL" type="Dividends" symbol="X" currency="EUR"
    dateTime="20250314" amount="5" description="X Cash Dividend" />
  <CashTransaction levelOfDetail="DETAIL" type="Dividends" symbol="X" currency="EUR"
    dateTime="20250314" amount="-5" description="X Cash Dividend - Reversal" />
  <CashTransaction levelOfDetail="DETAIL" type="Withholding Tax" symbol="X" currency="EUR"
    dateTime="20250314" amount="-0.5" description="X Tax" />
</CashTransactions>"""
    divs = parse_ibkr_flex(flex_xml(sections={"CashTransactions": cash})).report.dividends
    assert sum(d.withholding_tax for d in divs) == Decimal("0.5")


def test_opening_date_is_readable_from_a_statement_that_fails_to_parse():
    from backend.importers.ibkr_flex import read_date_opened

    broken = flex_xml(sections={"OpenPositions": None})
    assert read_date_opened(broken) == date(2019, 3, 12)
    assert read_date_opened("<<nope") is None


# ── client ───────────────────────────────────────────────────────────


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def envelope(status="Success", code=None, message="", reference=None) -> str:
    parts = [f"<Status>{status}</Status>"]
    if reference:
        parts.append(f"<ReferenceCode>{reference}</ReferenceCode>")
    if code:
        parts.append(f"<ErrorCode>{code}</ErrorCode><ErrorMessage>{message}</ErrorMessage>")
    return f'<FlexStatementResponse timestamp="x">{"".join(parts)}</FlexStatementResponse>'


def test_send_request_returns_the_reference_and_asks_for_the_period():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        assert request.url.path.endswith("/SendRequest")
        return httpx.Response(200, text=envelope(reference="9876543210"))

    reference = ibkr_flex.send_request(
        TOKEN, "123456", date(2024, 1, 1), date(2024, 12, 31), client=_client(handler)
    )
    assert reference == "9876543210"
    assert seen == {"t": TOKEN, "q": "123456", "v": "3", "fd": "20240101", "td": "20241231"}


@pytest.mark.parametrize(
    ("code", "kind"),
    [("1012", "connection"), ("1015", "connection"), ("1019", "transient"),
     ("1018", "transient"), ("1017", "stale_reference"), ("1003", None)],
)
def test_error_codes_are_classified(code, kind, caplog):
    def handler(request):
        return httpx.Response(200, text=envelope("Fail", code, "Some English text"))

    with caplog.at_level(logging.DEBUG), pytest.raises(FlexError) as exc:
        ibkr_flex.send_request(TOKEN, "1", date(2025, 1, 1), date(2025, 1, 2),
                               client=_client(handler))
    assert exc.value.code == code
    for flag in ("connection", "transient", "stale_reference"):
        assert getattr(exc.value, flag) is (flag == kind)
    assert "English" not in str(exc.value)  # the user reads Spanish
    assert TOKEN not in caplog.text


def test_network_failure_does_not_leak_the_token(caplog):
    def handler(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")

    with caplog.at_level(logging.DEBUG), pytest.raises(FlexError) as exc:
        ibkr_flex.get_statement(TOKEN, "42", client=_client(handler))
    assert exc.value.code is None
    assert TOKEN not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__
    assert TOKEN not in caplog.text


def test_http_error_status_is_reported():
    with pytest.raises(FlexError, match="HTTP 503"):
        ibkr_flex.get_statement(TOKEN, "42", client=_client(lambda r: httpx.Response(503)))


def test_non_xml_answer_is_reported():
    with pytest.raises(FlexError, match="no es XML"):
        ibkr_flex.get_statement(
            TOKEN, "42", client=_client(lambda r: httpx.Response(200, text="<<oops"))
        )


def test_success_envelope_instead_of_a_statement_is_not_imported():
    with pytest.raises(FlexError, match="inesperada"):
        ibkr_flex.get_statement(
            TOKEN, "42", client=_client(lambda r: httpx.Response(200, text=envelope()))
        )


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_poll_waits_through_generation_then_returns_the_statement():
    answers = iter([envelope("Warn", "1019"), envelope("Warn", "1019"), flex_xml()])
    clock = FakeClock()
    result = ibkr_flex.poll_statement(
        TOKEN, "42", budget_seconds=20, client=_client(lambda r: httpx.Response(200, text=next(answers))),
        sleep=clock.sleep, clock=clock,
    )
    assert result.xml is not None and "FlexQueryResponse" in result.xml
    assert clock.sleeps == [5.0, 5.0]


def test_poll_gives_up_inside_the_budget_and_keeps_the_reference():
    clock = FakeClock()
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, text=envelope("Warn", "1019"))

    result = ibkr_flex.poll_statement(
        TOKEN, "42", budget_seconds=12, client=_client(handler), sleep=clock.sleep, clock=clock
    )
    assert result.xml is None
    assert clock.now <= 12
    assert len(calls) == 3  # t=0, 5, 10 — never more than IBKR's pacing allows


def test_poll_raises_a_real_failure_at_once():
    clock = FakeClock()
    with pytest.raises(FlexError) as exc:
        ibkr_flex.poll_statement(
            TOKEN, "42", budget_seconds=20,
            client=_client(lambda r: httpx.Response(200, text=envelope("Fail", "1012"))),
            sleep=clock.sleep, clock=clock,
        )
    assert exc.value.connection
    assert clock.sleeps == []
