"""Tests for the DEGIRO Annual Report parser."""

from decimal import Decimal
from pathlib import Path

import pytest

from backend.importers.base import TxType
from backend.importers.dg import parse_dg_annual_report

PDF_PATH = Path("files/DG-Informe Anual 2024.pdf")
pytestmark = pytest.mark.skipif(not PDF_PATH.exists(), reason="DEGIRO 2024 PDF not available")


@pytest.fixture(scope="module")
def report():
    return parse_dg_annual_report(PDF_PATH)


# ── Fiscal year ────────────────────────────────────────────────────────


def test_fiscal_year(report):
    assert report.fiscal_year == 2024


# ── Dividends ──────────────────────────────────────────────────────────


def test_dividends_count(report):
    assert len(report.dividends) == 1


def test_enagas_dividend(report):
    d = report.dividends[0]
    assert d.name == "Enagas SA"
    assert d.isin == "ES0130960018"  # enriched from holdings
    assert d.country == "España"
    assert d.gross_amount == Decimal("40.00")
    assert d.withholding_tax == Decimal("7.60")
    assert d.foreign_withholding_tax == Decimal("7.60")
    assert d.net_amount_eur == Decimal("32.40")
    assert d.tx_type == TxType.DIVIDEND


# ── Gains summary ─────────────────────────────────────────────────────


def test_gains_summary_count(report):
    assert len(report.gains_summary) == 29


def test_gains_total_pl(report):
    total = sum(g.realized_pl_eur for g in report.gains_summary)
    assert total == Decimal("576.46")


def test_gains_total_commission(report):
    total = sum(g.commission_eur for g in report.gains_summary)
    assert total == Decimal("38.63")


def test_bayer_gain(report):
    bayer = [g for g in report.gains_summary if g.isin == "DE000BAY0017"]
    assert len(bayer) == 1
    assert bayer[0].realized_pl_eur == Decimal("96.00")


def test_coinbase_loss(report):
    coin = [g for g in report.gains_summary if g.isin == "US19260Q1076"]
    assert len(coin) == 1
    assert coin[0].realized_pl_eur == Decimal("-210.27")


# ── Holdings ───────────────────────────────────────────────────────────


def test_holdings_count(report):
    assert len(report.holdings) == 8  # 6 stocks + 2 options


def test_holdings_stocks(report):
    stocks = [h for h in report.holdings if h.asset_type == "Stock"]
    assert len(stocks) == 6
    names = {h.name for h in stocks}
    assert names == {"BANKINTER", "BASF SE", "Bayer AG", "Enagas SA", "ORANGE", "Telefonica SA"}


def test_holdings_options(report):
    opts = [h for h in report.holdings if h.asset_type == "Option"]
    assert len(opts) == 2


def test_enagas_holding(report):
    h = [h for h in report.holdings if h.isin == "ES0130960018"][0]
    assert h.quantity == Decimal("200")
    assert h.price == Decimal("11.7800")
    assert h.value_dec31_eur == Decimal("2356.00")


# ── Transactions ───────────────────────────────────────────────────────


def test_transactions_count(report):
    assert len(report.transactions) == 64


def test_transaction_types(report):
    buys = [t for t in report.transactions if t.tx_type == TxType.BUY]
    sells = [t for t in report.transactions if t.tx_type == TxType.SELL]
    assert len(buys) > 0
    assert len(sells) > 0
    assert len(buys) + len(sells) == 64


def test_bayer_buy(report):
    bayer_buys = [
        t for t in report.transactions
        if t.isin == "DE000BAY0017" and t.tx_type == TxType.BUY
    ]
    # 25/06 buy (round-trip) + 20/12 buy (open at year-end)
    assert len(bayer_buys) == 2


def test_bayer_sell_pl(report):
    bayer_sell = [
        t for t in report.transactions
        if t.isin == "DE000BAY0017" and t.tx_type == TxType.SELL
    ][0]
    assert bayer_sell.net_amount_eur == Decimal("2750.00")
    assert bayer_sell.realized_pl_eur == Decimal("96.0000")


def test_cross_year_sell(report):
    """Coinbase and CRONOS were bought in previous years — only sell in 2024."""
    coin = [t for t in report.transactions if t.isin == "US19260Q1076"]
    assert len(coin) == 1
    assert coin[0].tx_type == TxType.SELL
    assert coin[0].realized_pl_eur == Decimal("-210.2704")
