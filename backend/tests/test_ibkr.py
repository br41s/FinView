"""Tests for the IBKR Activity Statement CSV parser."""

from decimal import Decimal
from pathlib import Path

import pytest

from backend.importers.ibkr import parse_ibkr_activity_statement

CSV_PATH = Path(__file__).parent.parent.parent / "files" / "IBKR-U11040354_2024_2024.csv"


@pytest.fixture
def report():
    assert CSV_PATH.exists(), f"Test CSV not found: {CSV_PATH}"
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

    def test_no_forex_trades(self, report):
        fx = [t for t in report.trades if "EUR.USD" in t.name or "EUR.GBP" in t.name]
        assert len(fx) == 0


class TestDividends:
    def test_dividend_count(self, report):
        assert len(report.dividends) == 3

    def test_t_dividend(self, report):
        t_divs = [d for d in report.dividends if "T(" in d.name or d.isin == "US00206R1023"]
        assert len(t_divs) == 1
        assert t_divs[0].gross_amount == Decimal("13.88")
        assert t_divs[0].withholding_tax == Decimal("2.08")
        assert t_divs[0].currency == "USD"

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
