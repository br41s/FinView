"""Tests for the ING Información Fiscal PDF parser.

Uses the real ING Fiscal 2024 PDF as test fixture. All expected values
are taken directly from the PDF content — these are ground truth.
"""

import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path

from backend.importers.ing import parse_ing_report
from backend.importers.base import (
    TxType,
    country_from_isin,
    file_sha256 as compute_file_hash,
    parse_dmy as _parse_date,
    parse_eur_decimal as _parse_decimal,
)

_D = Decimal

# Path to real test data (same convention as test_import_service.py)
ING_PDF_PATH = Path(__file__).resolve().parents[2] / "files" / "ING-Fiscal-2024.pdf"


# -- Unit tests for helpers --


class TestParseDecimal:
    def test_simple(self):
        assert _parse_decimal("480,90€") == _D("480.90")

    def test_thousands(self):
        assert _parse_decimal("1.384,27€") == _D("1384.27")

    def test_with_space(self):
        assert _parse_decimal("117,95 €") == _D("117.95")

    def test_plain(self):
        assert _parse_decimal("200,00") == _D("200.00")

    def test_large_value(self):
        assert _parse_decimal("21.688,59€") == _D("21688.59")


class TestParseDate:
    def test_basic(self):
        assert _parse_date("20/06/2024") == date(2024, 6, 20)

    def test_january(self):
        assert _parse_date("31/01/2024") == date(2024, 1, 31)


class TestCountryFromIsin:
    def test_spain(self):
        assert country_from_isin("ES0113900J37") == "España"

    def test_germany(self):
        assert country_from_isin("DE0007100000") == "Alemania"

    def test_unknown(self):
        assert country_from_isin("XX1234567890") == "XX"

    def test_empty(self):
        assert country_from_isin("") == ""


# -- Integration tests against real PDF --


@pytest.fixture(scope="module")
def ing_pdf() -> Path:
    """The real ING Información Fiscal 2024.

    The PDF is not in the repo (`files/` is gitignored), so the tests that
    need it skip here rather than at module level — the helper unit tests
    above must run everywhere, including CI.
    """
    if not ING_PDF_PATH.exists():
        pytest.skip("ING Información Fiscal PDF not available")
    return ING_PDF_PATH


@pytest.fixture(scope="module")
def report(ing_pdf):
    """Parse the real ING Información Fiscal once for all tests."""
    return parse_ing_report(ing_pdf)


class TestFiscalYear:
    def test_year(self, report):
        assert report.fiscal_year == 2024


class TestInterest:
    def test_count(self, report):
        assert len(report.interest) == 1

    def test_interest_amount(self, report):
        i = report.interest[0]
        assert i.tx_type == TxType.INTEREST
        assert i.gross_amount == _D("200.00")
        assert i.withholding_tax == _D("38.00")
        assert i.domestic_withholding_tax == _D("38.00")
        assert i.foreign_withholding_tax == _D("0")
        assert i.net_amount_eur == _D("162.00")
        assert "ING" in i.name


class TestDividends:
    def test_count(self, report):
        assert len(report.dividends) == 12

    def test_total_gross(self, report):
        total = sum(d.gross_amount for d in report.dividends)
        assert total == _D("1384.27")

    def test_total_withholding(self, report):
        total = sum(d.withholding_tax for d in report.dividends)
        assert total == _D("263.01")

    def test_all_spanish(self, report):
        for d in report.dividends:
            assert d.country == "España"
            assert d.isin.startswith("ES")

    def test_santander_dividends(self, report):
        sant = [d for d in report.dividends if "SANTANDER" in d.name]
        assert len(sant) == 2
        assert sant[0].isin == "ES0113900J37"
        assert sant[0].gross_amount == _D("480.90")
        assert sant[1].gross_amount == _D("456.86")

    def test_all_isins_present(self, report):
        isins = {d.isin for d in report.dividends}
        expected = {
            "ES0113900J37",  # BA.SANTANDER
            "ES0130670112",  # ENDESA
            "ES0144580Y14",  # IBERDROLA
            "ES0105046009",  # AENA
            "ES0109067019",  # AMADEUS
            "ES0148396007",  # INDITEX
            "ES0173516115",  # REPSOL
        }
        assert isins == expected


class TestTransactions:
    def test_count(self, report):
        assert len(report.transactions) == 7

    def test_colonial_buys(self, report):
        colonial = [t for t in report.transactions if "COLONIAL" in t.name]
        assert len(colonial) == 3
        assert all(t.tx_type == TxType.BUY for t in colonial)
        assert all(t.isin == "ES0139140174" for t in colonial)
        assert colonial[0].trade_date == date(2024, 6, 20)
        assert colonial[0].quantity == _D("20")

    def test_iberdrola_scrip(self, report):
        ibe = [t for t in report.transactions if t.name.startswith("IBE")]
        assert len(ibe) == 3
        assert all(t.isin == "ES0144580Y14" for t in ibe)
        assert all(t.tx_type == TxType.BUY for t in ibe)

    def test_pescanova_sell(self, report):
        pesc = [t for t in report.transactions if "PESCANOVA" in t.name]
        assert len(pesc) == 1
        assert pesc[0].tx_type == TxType.SELL
        assert pesc[0].quantity == _D("4463")
        assert pesc[0].gross_amount == _D("1021.27")


class TestHoldings:
    def test_snapshot_is_marked_complete(self, report):
        assert report.portfolio_snapshot_complete is True

    def test_count(self, report):
        assert len(report.holdings) == 8

    def test_total_value(self, report):
        total = sum(h.value_dec31_eur for h in report.holdings)
        assert total == _D("66014.75")

    def test_all_have_names(self, report):
        """No holding should fall back to ISIN as name."""
        for h in report.holdings:
            assert h.name != h.isin, f"Holding {h.isin} has ISIN as name"

    def test_santander_holding(self, report):
        sant = [h for h in report.holdings if h.isin == "ES0113900J37"]
        assert len(sant) == 1
        assert sant[0].name == "BA.SANTANDER"
        assert sant[0].quantity == _D("4809")
        assert sant[0].price == _D("4.51")
        assert sant[0].value_dec31_eur == _D("21688.59")

    def test_colonial_holding(self, report):
        col = [h for h in report.holdings if h.isin == "ES0139140174"]
        assert len(col) == 1
        assert col[0].name == "COLONIAL"
        assert col[0].quantity == _D("60")

    def test_all_spanish(self, report):
        for h in report.holdings:
            assert h.country == "España"


class TestFileHash:
    def test_hash_deterministic(self, ing_pdf):
        h1 = compute_file_hash(ing_pdf)
        h2 = compute_file_hash(ing_pdf)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex
