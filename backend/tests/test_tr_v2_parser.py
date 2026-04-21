"""Tests for the Trade Republic 2025+ Spanish-branch PDF parser.

Uses the real ES-IBAN Tax Report PDF as fixture. Expected values
are taken directly from the PDF content (page 2 summary totals).
"""

from decimal import Decimal
from pathlib import Path

import pytest

from backend.importers.tr import parse_tr_tax_report
from backend.importers.tr_v2 import is_spanish_branch_format

TR_V2_PDF = Path(__file__).resolve().parents[2] / "files" / (
    "TR-Tax report - Period ES IBAN-2025.pdf"
)

pytestmark = pytest.mark.skipif(
    not TR_V2_PDF.exists(),
    reason="TR 2025 ES-IBAN PDF not available",
)


@pytest.fixture(scope="module")
def report():
    return parse_tr_tax_report(TR_V2_PDF)


def test_format_detected():
    assert is_spanish_branch_format(TR_V2_PDF)


def test_header(report):
    assert report.fiscal_year == 2025
    assert report.period_start.isoformat() == "2025-06-19"
    assert report.period_end.isoformat() == "2025-12-31"


def test_rendimientos_totals(report):
    interest = sum(
        d.gross_amount for d in report.dividends if d.tx_type.name == "INTEREST"
    )
    dividend = sum(
        d.gross_amount for d in report.dividends if d.tx_type.name == "DIVIDEND"
    )
    assert interest == Decimal("750.14")
    assert dividend == Decimal("2487.95")


def test_capital_gains_totals(report):
    pl = sum(c.realized_pl_eur for c in report.capital_gains)
    assert pl == Decimal("-7384.99")


def test_casillas_m100(report):
    by_casilla = {c.casilla: c.amount_eur for c in report.casillas_modelo_100}
    assert by_casilla[27] == Decimal("750.14")
    assert by_casilla[29] == Decimal("2487.95")
    assert by_casilla[328] == Decimal("-7297.49")


def test_casillas_m714(report):
    by_casilla = {c.casilla: c.amount_eur for c in report.casillas_modelo_714}
    assert by_casilla[5] == Decimal("41087.67")
    assert by_casilla[6] == Decimal("10237.43")
    # G1 + G2 should sum to the combined total shown on the last G page.
    assert by_casilla[8] + by_casilla[9] == Decimal("162374.60")


def test_cdi_credit_captured(report):
    total_acreditable = sum(
        (d.double_taxation_amount or Decimal("0")) for d in report.dividends
    )
    assert total_acreditable == Decimal("84.60")


def test_transactions_empty(report):
    # Section VI (all transactions) no longer exists in the 2025 format.
    assert report.transactions == []
