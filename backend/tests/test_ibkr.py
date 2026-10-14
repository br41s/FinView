"""Tests for the IBKR Activity Statement CSV parser."""

from decimal import Decimal
from pathlib import Path

import pytest

from backend.importers import ibkr as ibkr_module
from backend.importers.ibkr import (
    _apply_assignment_premiums,
    _detect_assignments,
    _extract_trades,
    _parse_single_trade,
    parse_ibkr_activity_statement,
)

CSV_PATH = Path(__file__).parent.parent.parent / "files" / "IBKR-U11040354_2024_2024.csv"


def _assignment_row(
    category: str,
    symbol: str,
    quantity: str,
    price: str,
    code: str,
    *,
    basis: str = "0",
    proceeds: str = "0",
) -> list[str]:
    row = [""] * 16
    row[1] = "Data"
    row[2] = "Order"
    row[3] = category
    row[4] = "EUR"
    row[5] = symbol
    row[6] = "2024-12-19"
    row[7] = quantity
    row[8] = price
    row[10] = proceeds
    row[12] = basis
    row[15] = code
    return row


@pytest.fixture
def report():
    if not CSV_PATH.exists():
        pytest.skip(f"IBKR 2024 CSV not available: {CSV_PATH}")
    return parse_ibkr_activity_statement(CSV_PATH)


class TestAccountInfo:
    def test_account_id(self, report):
        assert report.account_id == "U11040354"

    def test_account_name(self, report):
        assert report.account_name == "FRANCISCO B NIETO ROMERO"

    def test_base_currency(self, report):
        assert report.base_currency == "EUR"

    def test_fiscal_year(self, report):
        assert report.fiscal_year == 2024


class TestSymbolISINMap:
    def test_has_stocks(self, report):
        assert "ADM" in report.symbol_isin_map
        assert "IBKR" in report.symbol_isin_map
        assert "T" in report.symbol_isin_map
        assert "VZ" in report.symbol_isin_map

    def test_isin_values(self, report):
        assert report.symbol_isin_map["ADM"] == "US0394831020"
        assert report.symbol_isin_map["T"] == "US00206R1023"
        assert report.symbol_isin_map["VZ"] == "US92343V1044"
        assert report.symbol_isin_map["IBKR"] == "US45841N1072"


class TestTrades:
    def test_trade_count(self, report):
        assert len(report.trades) == 24

    def test_stock_buy(self, report):
        adm_buys = [t for t in report.trades if t.name == "ADM" and t.tx_type.value == "BUY"]
        assert len(adm_buys) == 1
        assert adm_buys[0].quantity == Decimal("100")
        assert adm_buys[0].price == Decimal("52.5")
        assert adm_buys[0].currency == "USD"

    def test_option_trades_present(self, report):
        opt_trades = [t for t in report.trades if t.name.startswith("[OPT]")]
        assert len(opt_trades) > 0

    def test_option_trades_have_no_isin(self, report):
        """Options should NOT inherit the underlying stock's ISIN."""
        opt_trades = [t for t in report.trades if t.name.startswith("[OPT]")]
        for t in opt_trades:
            assert t.isin == "", f"Option {t.name} should have empty ISIN, got {t.isin}"

    def test_no_forex_trades(self, report):
        fx = [t for t in report.trades if "EUR.USD" in t.name or "EUR.GBP" in t.name]
        assert len(fx) == 0

    def test_commissions_increase_buy_cost_and_reduce_sell_proceeds(self):
        buy_row = [""] * 14
        buy_row[3:14] = [
            "Stocks", "EUR", "BASF", "2024-01-02", "10", "100", "",
            "-1000", "-10", "", "0",
        ]
        sell_row = [""] * 14
        sell_row[3:14] = [
            "Stocks", "EUR", "BASF", "2024-06-02", "-10", "120", "",
            "1200", "-10", "", "180",
        ]
        symbol_isin = {"BASF": "DE000BASF111"}

        buy = _parse_single_trade(buy_row, symbol_isin, {})
        sell = _parse_single_trade(sell_row, symbol_isin, {})

        assert buy is not None
        assert sell is not None
        assert buy.net_amount_eur == Decimal("1010")
        assert sell.net_amount_eur == Decimal("1190")
        assert sell.net_amount_eur - buy.net_amount_eur == Decimal("180")


class TestDividends:
    def test_dividend_count(self, report):
        assert len(report.dividends) == 3

    def test_t_dividend_is_in_eur(self, report):
        t_divs = [d for d in report.dividends if d.isin == "US00206R1023"]
        assert len(t_divs) == 1
        d = t_divs[0]
        # Original currency retained for reference
        assert d.currency == "USD"
        assert d.price == Decimal("13.88")  # Original USD amount as price
        # gross_amount, withholding, net are now in EUR
        assert d.gross_amount < Decimal("13.88")  # EUR < USD for 2024 rates
        assert d.gross_amount > Decimal("10")  # Sanity check
        assert d.exchange_rate < Decimal("1")  # EUR/USD < 1 in 2024
        # Withholding also in EUR (stored as negative)
        assert d.withholding_tax < Decimal("2.08")
        assert d.withholding_tax > Decimal("1.5")
        # Net = gross + wht (wht is negative)
        assert abs(d.net_amount_eur - (d.gross_amount - d.withholding_tax)) < Decimal("0.01")

    def test_all_dividends_in_eur(self, report):
        """All dividend gross_amounts should be in EUR (less than original USD)."""
        total_eur = sum(d.gross_amount for d in report.dividends)
        # IBKR reports Total in EUR = 13.4925917, our conversion should be close
        assert Decimal("12") < total_eur < Decimal("15")

    def test_ibkr_pil_dividends(self, report):
        ibkr_divs = [d for d in report.dividends if d.isin == "US45841N1072"]
        assert len(ibkr_divs) == 2


class TestInterest:
    def test_interest_count(self, report):
        assert len(report.interest) == 2

    def test_interest_amounts(self, report):
        total = sum(i.gross_amount for i in report.interest)
        assert total == Decimal("26.88")

    def test_interest_currency(self, report):
        for i in report.interest:
            assert i.currency == "EUR"


class TestHoldings:
    def test_holdings_count(self, report):
        assert len(report.holdings) == 4

    def test_adm_holding(self, report):
        adm = [h for h in report.holdings if h.name == "ADM"]
        assert len(adm) == 1
        assert adm[0].quantity == Decimal("100")
        assert adm[0].currency == "USD"
        assert adm[0].isin == "US0394831020"

    def test_holdings_in_eur(self, report):
        """Holdings values should be converted to EUR using year-end rate."""
        adm = next(h for h in report.holdings if h.name == "ADM")
        # ADM: 100 shares at $50.52 = $5052 USD
        # Year-end rate: 1 USD = 0.96586 EUR → ~$5052 * 0.96586 = ~€4879.53
        assert Decimal("4800") < adm.value_dec31_eur < Decimal("5000")
        assert adm.value_dec31_eur < Decimal("5052")  # EUR < USD

    def test_total_holdings_eur(self, report):
        """Total holdings should match IBKR's EUR total (~10286.31 EUR)."""
        total = sum(h.value_dec31_eur for h in report.holdings)
        # IBKR reports: Open Positions Total Stocks EUR = 10286.312414
        assert abs(total - Decimal("10286.312414")) < Decimal("1")

    def test_all_stocks_have_isin(self, report):
        for h in report.holdings:
            assert h.isin, f"Missing ISIN for {h.name}"


class TestRealizedGains:
    def test_gains_count(self, report):
        assert len(report.realized_gains) == 9

    def test_option_gains(self, report):
        opt_gains = [g for g in report.realized_gains if g.name.startswith("[OPT]")]
        assert len(opt_gains) == 7
        total = sum(g.realized_pl_eur for g in opt_gains)
        assert total == Decimal("219.23965433")

    def test_fx_gains(self, report):
        fx_gains = [g for g in report.realized_gains if g.name.startswith("[FX]")]
        assert len(fx_gains) == 2
        usd_fx = [g for g in fx_gains if "USD" in g.name]
        assert usd_fx[0].realized_pl_eur == Decimal("-6.915179")

    def test_all_gains_are_eur(self, report):
        """Values in Realized Performance Summary are in base currency (EUR)."""
        total_options = sum(
            g.realized_pl_eur for g in report.realized_gains
            if g.name.startswith("[OPT]")
        )
        # 219.24 EUR matches the CSV total for options
        assert abs(total_options - Decimal("219.23965433")) < Decimal("0.01")

    def test_option_gains_have_no_isin(self, report):
        """Option realized gains should NOT inherit the underlying's ISIN."""
        opt_gains = [g for g in report.realized_gains if g.name.startswith("[OPT]")]
        for g in opt_gains:
            assert g.isin == "", f"Option gain {g.name} should have empty ISIN, got {g.isin}"


class TestOptionAssignments:
    """Detect option assignments from IBKR trade codes (A;C / A;O)."""

    def test_assignment_count(self, report):
        """2024 CSV has 2 assignments: ADM PUT and VZ PUT."""
        assert len(report.assignments) == 2

    def test_adm_put_assignment(self, report):
        adm = [a for a in report.assignments if a.underlying == "ADM"]
        assert len(adm) == 1
        a = adm[0]
        assert a.option_type == "P"
        assert a.strike == Decimal("52.5")
        assert a.stock_quantity == Decimal("100")
        assert a.stock_isin == "US0394831020"
        assert a.premium_eur > Decimal("0")

    def test_vz_put_assignment(self, report):
        vz = [a for a in report.assignments if a.underlying == "VZ"]
        assert len(vz) == 1
        a = vz[0]
        assert a.option_type == "P"
        assert a.strike == Decimal("40.5")
        assert a.stock_quantity == Decimal("100")
        assert a.stock_isin == "US92343V1044"
        assert a.premium_eur > Decimal("0")

    def test_assigned_options_not_in_realized_gains(self, report):
        """Assigned option P/L should NOT appear in realized gains (IBKR handles correctly)."""
        realized_names = {g.name for g in report.realized_gains}
        for a in report.assignments:
            opt_name = f"[OPT] {a.option_symbol}"
            assert opt_name not in realized_names, (
                f"Assigned option {a.option_symbol} should not be in realized gains"
            )

    def test_multiple_assignments_same_underlying_and_date_are_not_overwritten(self):
        rows = [
            _assignment_row(
                "Equity and Index Options", "ABC 20DEC24 50 P", "1", "0", "A;C",
                basis="100",
            ),
            _assignment_row("Stocks", "ABC", "100", "50", "A;O", proceeds="-5000"),
            _assignment_row(
                "Equity and Index Options", "ABC 20DEC24 55 P", "1", "0", "A;C",
                basis="80",
            ),
            _assignment_row("Stocks", "ABC", "100", "55", "A;O", proceeds="-5500"),
        ]

        assignments = _detect_assignments(rows, {"ABC": "US0000000001"}, {})

        assert [item.strike for item in assignments] == [Decimal("50"), Decimal("55")]
        assert [item.premium_eur for item in assignments] == [
            Decimal("100"),
            Decimal("80"),
        ]

    def test_put_and_call_premiums_adjust_stock_cash_once(self):
        rows = [
            _assignment_row(
                "Equity and Index Options", "ABC 20DEC24 50 P", "1", "0", "A;C",
                basis="100",
            ),
            _assignment_row("Stocks", "ABC", "100", "50", "A;O", proceeds="-5000"),
            _assignment_row(
                "Equity and Index Options", "XYZ 20DEC24 60 C", "-1", "0", "A;C",
                basis="80",
            ),
            _assignment_row("Stocks", "XYZ", "-100", "60", "A;O", proceeds="6000"),
        ]
        symbol_isin = {"ABC": "US0000000001", "XYZ": "US0000000002"}
        assignments = _detect_assignments(rows, symbol_isin, {})
        trades = _extract_trades(rows, symbol_isin, {})

        _apply_assignment_premiums(trades, assignments)

        abc = next(trade for trade in trades if trade.name == "ABC")
        xyz = next(trade for trade in trades if trade.name == "XYZ")
        assert abc.net_amount_eur == Decimal("4900")
        assert xyz.net_amount_eur == Decimal("6080")

    def test_missing_or_ambiguous_stock_leg_is_rejected(self):
        option = _assignment_row(
            "Equity and Index Options", "ABC 20DEC24 50 P", "1", "0", "A;C",
            basis="100",
        )
        with pytest.raises(ValueError, match="0 coincidencias"):
            _detect_assignments([option], {"ABC": "US0000000001"}, {})

        stock = _assignment_row(
            "Stocks", "ABC", "100", "50", "A;O", proceeds="-5000"
        )
        with pytest.raises(ValueError, match="2 coincidencias"):
            _detect_assignments([option, stock, stock.copy()], {"ABC": "US0000000001"}, {})

    def test_invalid_option_type_is_rejected(self):
        malformed = _assignment_row(
            "Equity and Index Options", "ABC 20DEC24 50 X", "1", "0", "A;C",
            basis="100",
        )

        with pytest.raises(ValueError, match="Tipo de opción no válido"):
            _detect_assignments([malformed], {"ABC": "US0000000001"}, {})

    def test_public_parser_applies_assignment_premium(self, tmp_path, monkeypatch):
        rows = [
            _assignment_row(
                "Equity and Index Options", "ABC 20DEC24 50 P", "1", "0", "A;C",
                basis="100",
            ),
            _assignment_row("Stocks", "ABC", "100", "50", "A;O", proceeds="-5000"),
        ]
        monkeypatch.setattr(ibkr_module, "_parse_sections", lambda _text: {"Trades": rows})
        monkeypatch.setattr(
            ibkr_module,
            "_extract_account_info",
            lambda _rows: ("TEST", "Test", "EUR"),
        )
        monkeypatch.setattr(ibkr_module, "_extract_fiscal_year", lambda _rows: 2024)
        monkeypatch.setattr(
            ibkr_module,
            "_extract_instrument_info",
            lambda _rows: {"ABC": "US0000000001"},
        )
        monkeypatch.setattr(ibkr_module, "_extract_forex_rates", lambda _rows: {})
        monkeypatch.setattr(ibkr_module, "_extract_yearend_fx_rates", lambda _rows: {})
        monkeypatch.setattr(ibkr_module, "_extract_dividends", lambda *_args: [])
        monkeypatch.setattr(ibkr_module, "_extract_interest", lambda _rows: [])
        monkeypatch.setattr(ibkr_module, "_extract_open_positions", lambda *_args: [])
        monkeypatch.setattr(ibkr_module, "_extract_realized_performance", lambda *_args: [])
        path = tmp_path / "ibkr.csv"
        path.write_text("fixture", encoding="utf-8")

        parsed = parse_ibkr_activity_statement(path)

        stock = next(trade for trade in parsed.trades if trade.name == "ABC")
        assert stock.gross_amount == Decimal("5000")
        assert stock.net_amount_eur == Decimal("4900")


class TestForexRates:
    """Test Forex rate extraction and EUR conversion."""

    def test_trades_have_exchange_rate(self, report):
        """USD trades with non-zero amounts should have exchange_rate < 1 (EUR per USD)."""
        usd_trades = [t for t in report.trades if t.currency == "USD" and t.gross_amount > 0]
        assert len(usd_trades) > 0
        for t in usd_trades:
            assert t.exchange_rate < Decimal("1"), f"Trade {t.name} EUR/USD rate should be < 1"
            assert t.exchange_rate > Decimal("0.8"), f"Trade {t.name} rate seems too low"

    def test_gbp_trades_have_exchange_rate(self, report):
        """GBP trades with non-zero amounts should have exchange_rate > 1 (EUR per GBP)."""
        gbp_trades = [t for t in report.trades if t.currency == "GBP" and t.gross_amount > 0]
        assert len(gbp_trades) > 0
        for t in gbp_trades:
            assert t.exchange_rate > Decimal("1"), f"Trade {t.name} EUR/GBP rate should be > 1"

    def test_stock_buy_eur_conversion(self, report):
        """ADM stock buy: $5250 should convert to less in EUR."""
        adm_buys = [t for t in report.trades if t.name == "ADM" and t.tx_type.value == "BUY"]
        assert len(adm_buys) == 1
        adm = adm_buys[0]
        assert adm.price == Decimal("52.5")  # Original USD price preserved
        assert adm.gross_amount < Decimal("5250")  # EUR < USD
        assert adm.gross_amount > Decimal("4500")  # Sanity check

    def test_dividends_have_exchange_rate(self, report):
        """USD dividends should have exchange_rate set."""
        for d in report.dividends:
            if d.currency == "USD":
                assert d.exchange_rate < Decimal("1")
                assert d.exchange_rate > Decimal("0.8")


# ── 2025 tests (Spanish-language IBKR CSV) ───────────────────────────

CSV_2025 = Path(__file__).parent.parent.parent / "files" / "IBKR-U11040354_2025_2025.csv"


@pytest.fixture
def report_2025():
    if not CSV_2025.exists():
        pytest.skip(f"IBKR 2025 CSV not available: {CSV_2025}")
    return parse_ibkr_activity_statement(CSV_2025)


class TestAccountInfo2025:
    def test_account_id(self, report_2025):
        assert report_2025.account_id == "U11040354"

    def test_account_name(self, report_2025):
        assert report_2025.account_name == "FRANCISCO B NIETO ROMERO"

    def test_base_currency(self, report_2025):
        assert report_2025.base_currency == "EUR"

    def test_fiscal_year(self, report_2025):
        assert report_2025.fiscal_year == 2025


class TestSymbolISINMap2025:
    def test_has_new_stocks(self, report_2025):
        for sym in ("ADM", "GIS", "HRL", "IBKR", "IFLEX", "KVUE", "T", "U11", "VZ"):
            assert sym in report_2025.symbol_isin_map, f"Missing {sym}"

    def test_isin_values(self, report_2025):
        assert report_2025.symbol_isin_map["KVUE"] == "US49177J1025"
        assert report_2025.symbol_isin_map["HRL"] == "US4404521001"
        assert report_2025.symbol_isin_map["GIS"] == "US3703341046"
        assert report_2025.symbol_isin_map["U11"] == "SG1M31001969"


class TestTrades2025:
    def test_trade_count(self, report_2025):
        assert len(report_2025.trades) == 52

    def test_no_forex_trades(self, report_2025):
        fx = [t for t in report_2025.trades if "EUR." in t.name]
        assert len(fx) == 0

    def test_option_trades_present(self, report_2025):
        opt = [t for t in report_2025.trades if t.name.startswith("[OPT]")]
        assert len(opt) > 0

    def test_sgd_trade_converted(self, report_2025):
        """U11 is traded in SGD — should have EUR conversion."""
        u11 = [t for t in report_2025.trades if t.name == "U11"]
        assert len(u11) >= 1
        assert u11[0].currency == "SGD"
        assert u11[0].gross_amount > 0


class TestDividends2025:
    def test_dividend_count(self, report_2025):
        assert len(report_2025.dividends) == 20

    def test_eur_dividend(self, report_2025):
        """IFLEX pays in EUR — no conversion needed."""
        iflex = [d for d in report_2025.dividends if d.isin == "ES0105684007"]
        assert len(iflex) == 2
        for d in iflex:
            assert d.currency == "EUR"
            assert d.exchange_rate == Decimal("1")

    def test_usd_dividend_converted(self, report_2025):
        """ADM USD dividends should be converted to EUR."""
        adm = [d for d in report_2025.dividends if d.isin == "US0394831020"]
        assert len(adm) == 4
        for d in adm:
            assert d.currency == "USD"
            assert d.exchange_rate < Decimal("1")
            assert d.gross_amount < d.price  # EUR < USD

    def test_withholding_matched(self, report_2025):
        """All dividends should have withholding tax matched."""
        for d in report_2025.dividends:
            assert d.withholding_tax > 0, f"Missing WHT for {d.name} on {d.trade_date}"
            assert d.domestic_withholding_tax == 0
            assert d.foreign_withholding_tax == d.withholding_tax

    def test_new_tickers_hrl_kvue(self, report_2025):
        """HRL and KVUE are new dividend payers in 2025."""
        hrl = [d for d in report_2025.dividends if d.isin == "US4404521001"]
        kvue = [d for d in report_2025.dividends if d.isin == "US49177J1025"]
        assert len(hrl) == 1
        assert len(kvue) == 1


class TestInterest2025:
    def test_interest_count(self, report_2025):
        assert len(report_2025.interest) == 10

    def test_all_eur(self, report_2025):
        for i in report_2025.interest:
            assert i.currency == "EUR"


class TestHoldings2025:
    def test_holdings_count(self, report_2025):
        assert len(report_2025.holdings) == 9

    def test_quantities(self, report_2025):
        """Verify quantities match Open Positions data (no 'Open' column offset bug)."""
        by_name = {h.name: h for h in report_2025.holdings}
        assert by_name["ADM"].quantity == Decimal("102.5199")
        assert by_name["IFLEX"].quantity == Decimal("1300")
        assert by_name["T"].quantity == Decimal("51.8982")
        assert by_name["VZ"].quantity == Decimal("125.1618")
        assert by_name["U11"].quantity == Decimal("100")

    def test_total_eur(self, report_2025):
        """Total must match IBKR NAV stocks: 25855.4251335 EUR."""
        total = sum(h.value_dec31_eur for h in report_2025.holdings)
        assert abs(total - Decimal("25855.4251335")) < Decimal("1")

    def test_multi_currency(self, report_2025):
        """Holdings span EUR, SGD, and USD."""
        currencies = {h.currency for h in report_2025.holdings}
        assert currencies == {"EUR", "SGD", "USD"}


class TestRealizedGains2025:
    def test_option_gains(self, report_2025):
        opt = [g for g in report_2025.realized_gains if g.name.startswith("[OPT]")]
        total = sum(g.realized_pl_eur for g in opt)
        assert abs(total - Decimal("1012.64231245")) < Decimal("0.01")

    def test_fx_gains(self, report_2025):
        fx = [g for g in report_2025.realized_gains if g.name.startswith("[FX]")]
        assert len(fx) == 3  # GBP, SGD, USD
        usd = next(g for g in fx if "USD" in g.name)
        assert usd.realized_pl_eur == Decimal("-52.830669")

    def test_total_realized(self, report_2025):
        total = sum(g.realized_pl_eur for g in report_2025.realized_gains)
        assert abs(total - Decimal("951.01888545")) < Decimal("0.01")
