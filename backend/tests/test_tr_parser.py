"""Tests for the Trade Republic PDF parser.

Uses the real Tax Report 2024 PDF as test fixture. All expected values
are taken directly from the PDF content — these are ground truth.
"""

import pytest
from decimal import Decimal
from pathlib import Path

from backend.importers.tr import parse_tr_tax_report, parse_eur_number, parse_date
from backend.importers.base import TxType

# Path to real test data (same convention as test_import_service.py)
TR_PDF_PATH = Path(__file__).resolve().parents[2] / "files" / "TR-Tax Report 2024.pdf"


# -- Unit tests for helpers --


class TestParseEurNumber:
    def test_simple(self):
        assert parse_eur_number("1.234,56") == Decimal("1234.56")

    def test_negative(self):
        assert parse_eur_number("-2.155,109352") == Decimal("-2155.109352")

    def test_no_thousands(self):
        assert parse_eur_number("530,00") == Decimal("530.00")

    def test_large(self):
        assert parse_eur_number("42.577,900000") == Decimal("42577.900000")

    def test_small_decimal(self):
        assert parse_eur_number("0,08612") == Decimal("0.08612")


class TestParseDate:
    def test_basic(self):
        from datetime import date
        assert parse_date("14.05.2024") == date(2024, 5, 14)


# -- Integration tests against real PDF --


@pytest.fixture(scope="module")
def report():
    """Parse the real TR Tax Report once for all tests.

    The PDF is not in the repo (`files/` is gitignored), so the tests that
    need it skip here rather than at module level — the helper unit tests
    above must run everywhere, including CI.
    """
    if not TR_PDF_PATH.exists():
        pytest.skip("Trade Republic Tax Report PDF not available")
    return parse_tr_tax_report(TR_PDF_PATH)


class TestHeader:
    def test_client_id(self, report):
        assert report.client_id == "0329750900"

    def test_period(self, report):
        from datetime import date
        assert report.period_start == date(2024, 1, 8)
        assert report.period_end == date(2024, 12, 31)

    def test_fiscal_year(self, report):
        assert report.fiscal_year == 2024


class TestModelo100:
    """Section VIII: pre-calculated casillas — our ground truth."""

    def test_four_casillas(self, report):
        assert len(report.casillas_modelo_100) == 4

    def test_casilla_27_intereses(self, report):
        c27 = next(c for c in report.casillas_modelo_100 if c.casilla == 27)
        assert c27.amount_eur == Decimal("1529.638875")

    def test_casilla_29_dividendos(self, report):
        c29 = next(c for c in report.casillas_modelo_100 if c.casilla == 29)
        assert c29.amount_eur == Decimal("5301.020528")

    def test_casilla_332_ganancias(self, report):
        c332 = next(c for c in report.casillas_modelo_100 if c.casilla == 332)
        assert c332.amount_eur == Decimal("297.398022")

    def test_casilla_337_perdidas(self, report):
        c337 = next(c for c in report.casillas_modelo_100 if c.casilla == 337)
        assert c337.amount_eur == Decimal("-2155.109352")


class TestModelo714:
    """Section IX: patrimonio casillas."""

    def test_four_casillas(self, report):
        assert len(report.casillas_modelo_714) == 4

    def test_casilla_05_depositos(self, report):
        c05 = next(c for c in report.casillas_modelo_714 if c.casilla == 5)
        assert c05.amount_eur == Decimal("42577.900000")

    def test_casilla_09_acciones(self, report):
        c09 = next(c for c in report.casillas_modelo_714 if c.casilla == 9)
        assert c09.amount_eur == Decimal("96551.790000")


class TestDividends:
    """Section I: dividend extraction."""

    def test_count(self, report):
        assert len(report.dividends) >= 60  # 65 expected

    def test_mercedes_dividend(self, report):
        """Mercedes-Benz Group: 14.05.2024, 530.00 EUR gross, withholding 139.78.

        `gross_amount` is the íntegro that feeds casilla 29; `net_amount_eur`
        is the cash that reached the account, i.e. gross minus withholding.
        Both are asserted so a future flip in either direction fails here.
        """
        from datetime import date
        mbg = [d for d in report.dividends
               if d.isin == "DE0007100000" and d.trade_date == date(2024, 5, 14)]
        assert len(mbg) == 1
        d = mbg[0]
        assert d.gross_amount == Decimal("530.0000")
        assert d.net_amount_eur == Decimal("390.220000")
        assert d.withholding_tax == Decimal("139.780000")
        assert d.domestic_withholding_tax == Decimal("0")
        assert d.foreign_withholding_tax == Decimal("139.780000")
        assert d.casilla == 29

    def test_siemens_dividend(self, report):
        from datetime import date
        sie = [d for d in report.dividends
               if d.isin == "DE0007236101" and d.trade_date == date(2024, 2, 13)]
        assert len(sie) == 1
        assert sie[0].gross_amount == Decimal("577.269985")
        assert sie[0].withholding_tax == Decimal("152.250000")
        assert sie[0].net_amount_eur == Decimal("425.019985")

    def test_country_tracked(self, report):
        de_divs = [d for d in report.dividends if d.country == "Alemania"]
        assert len(de_divs) >= 3  # Mercedes, Siemens, Allianz at least

    def test_all_dividends_have_casilla(self, report):
        for d in report.dividends:
            assert d.casilla in (27, 29), f"Unexpected casilla {d.casilla} for {d.isin}"

    def test_gross_dividends_match_modelo100(self, report):
        """Sum of gross dividends must equal the PDF's own casilla 29.

        Casilla 29 declares the íntegro, not the cash received, so this is the
        guard against `gross_amount` and `net_amount_eur` being swapped — the
        drift that left the two assertions above stale for months.
        """
        gross = sum(d.gross_amount for d in report.dividends if d.casilla == 29)
        c29 = next(c for c in report.casillas_modelo_100 if c.casilla == 29)
        assert abs(gross - c29.amount_eur) < Decimal("0.01")


class TestCapitalGains:
    """Section III: matched buy/sell pairs with P&L."""

    def test_count(self, report):
        assert len(report.capital_gains) == 16

    def test_mercedes_loss(self, report):
        """Mercedes-Benz Group: loss of -996.00 EUR, casilla 337."""
        mbg = [g for g in report.capital_gains if g.isin == "DE0007100000"]
        assert len(mbg) >= 1
        g = mbg[0]
        assert g.realized_pl_eur == Decimal("-996.0000")
        assert g.casilla == 337
        assert g.holding_period == "<1y"

    def test_siemens_gains(self, report):
        """Siemens had multiple sales with gains."""
        sie = [g for g in report.capital_gains if g.isin == "DE0007236101"]
        assert len(sie) >= 2
        assert all(g.casilla == 332 for g in sie)  # All gains

    def test_all_valid_casillas(self, report):
        for g in report.capital_gains:
            assert g.casilla in (332, 337)

    def test_total_gains_match_modelo100(self, report):
        """Sum of gains (casilla 332) should match Modelo 100."""
        gains = sum(g.realized_pl_eur for g in report.capital_gains if g.casilla == 332)
        c332 = next(c for c in report.casillas_modelo_100 if c.casilla == 332)
        assert abs(gains - c332.amount_eur) < Decimal("0.01")

    def test_total_losses_match_modelo100(self, report):
        """Sum of losses (casilla 337) should match Modelo 100."""
        losses = sum(g.realized_pl_eur for g in report.capital_gains if g.casilla == 337)
        c337 = next(c for c in report.casillas_modelo_100 if c.casilla == 337)
        assert abs(losses - c337.amount_eur) < Decimal("0.01")


class TestTransactions:
    """Section VI: all buy/sell transactions."""

    def test_count(self, report):
        assert len(report.transactions) >= 100  # 112 expected

    def test_wienerberger_buy_sell(self, report):
        """AT0000831706 - Wienerberger: buy 10.05.2024, sell 15.05.2024."""
        from datetime import date
        buys = [t for t in report.transactions
                if t.isin == "AT0000831706" and t.tx_type == TxType.BUY]
        sells = [t for t in report.transactions
                 if t.isin == "AT0000831706" and t.tx_type == TxType.SELL]
        assert len(buys) == 1
        assert len(sells) == 1
        assert buys[0].trade_date == date(2024, 5, 10)
        assert buys[0].quantity == Decimal("15.00")
        assert buys[0].gross_amount == Decimal("525.600000")

    def test_has_spinoff(self, report):
        spinoffs = [t for t in report.transactions if t.tx_type == TxType.SPINOFF]
        assert len(spinoffs) >= 1  # Inmocemento spin-off


class TestHoldings:
    """Section VII: portfolio at year-end."""

    def test_count(self, report):
        assert len(report.holdings) >= 40  # 49 expected

    def test_petrobras(self, report):
        pb = [h for h in report.holdings if h.isin == "BRPETRACNOR9"]
        assert len(pb) == 1
        assert pb[0].quantity == Decimal("500.00")
        assert pb[0].value_dec31_eur == Decimal("3336.00")


class TestWithholdings:
    """Section V: withholding tax details."""

    def test_count(self, report):
        assert len(report.withholdings) >= 20  # 23 expected

    def test_mercedes_withholding(self, report):
        from datetime import date
        w = [w for w in report.withholdings
             if w.isin == "DE0007100000" and w.payment_date == date(2024, 5, 14)]
        assert len(w) == 1
        assert w[0].income_eur == Decimal("530.00")
        assert w[0].withholding_eur == Decimal("139.780000")
        assert w[0].withholding_rate == Decimal("15.00")
