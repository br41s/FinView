"""DEGIRO year-end holdings are persisted as a portfolio snapshot.

Before, the annual report's "Certificado de Beneficiario" was parsed and only
counted. It is now stored like ING/BBVA holdings, with
``portfolio_snapshot_complete`` true only when the certificate is present and
every ISIN printed in it was parsed: a complete snapshot closes whatever it
omits, so a row the regex could not read must not count as "not held".
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.importers import dg
from backend.importers.base import DGAnnualReport, ParsedPortfolioHolding
from backend.models import (
    Base,
    ImportRecord,
    PortfolioHolding,
    Transaction,
    TransactionType,
    User,
)
from backend.services import data_supervisor, portfolio_service, split_history
from backend.services.import_service import _delete_import_data, import_dg_report

_FILES = Path(__file__).resolve().parents[2] / "files"
ENAGAS = "ES0130960018"
REPSOL = "ES0173516115"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Imports run the data supervisor; keep its Yahoo lookups off the network."""
    monkeypatch.setattr(data_supervisor, "_try_resolve_ticker", lambda _isin: None)
    monkeypatch.setattr(split_history, "_fetch", lambda _ticker: [])


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def user_id(db) -> int:
    user = User(email="dg@example.com", name="DG", password_hash="x")
    db.add(user)
    db.flush()
    return user.id


# ── Parser: when is the certificate complete? ─────────────────────────


def _parse_text(monkeypatch, text: str):
    monkeypatch.setattr(dg, "_extract_text", lambda _path: (text, text))
    return dg.parse_dg_annual_report(Path("dg.pdf"))


def test_no_certificate_is_not_a_snapshot(monkeypatch):
    report = _parse_text(monkeypatch, "Informe Anual 2025\n")

    assert report.holdings == []
    assert report.portfolio_snapshot_complete is False


def test_certificate_with_every_row_parsed_is_complete(monkeypatch):
    report = _parse_text(
        monkeypatch,
        "Informe Anual 2025\nCertificado de Beneficiario\n"
        f"Enagas SA {ENAGAS} Stock XMAD 10 EUR 17,50 175,00\n",
    )

    assert [h.isin for h in report.holdings] == [ENAGAS]
    assert report.portfolio_snapshot_complete is True


def test_certificate_with_an_unreadable_row_is_partial(monkeypatch):
    """Repsol's line does not match the row pattern; its ISIN is still printed."""
    report = _parse_text(
        monkeypatch,
        "Informe Anual 2025\nCertificado de Beneficiario\n"
        f"Enagas SA {ENAGAS} Stock XMAD 10 EUR 17,50 175,00\n"
        f"Repsol SA {REPSOL} Stock XMAD diez EUR 12,00 120,00\n",
    )

    assert [h.isin for h in report.holdings] == [ENAGAS]
    assert report.portfolio_snapshot_complete is False


# ── Importer: rows are stored, replaced and deleted with the import ───


def _holding(isin: str, qty: str) -> ParsedPortfolioHolding:
    return ParsedPortfolioHolding(
        isin=isin, name=isin, currency="EUR", asset_type="Stock", country="España",
        casilla_714=0, quantity=Decimal(qty), avg_q4_balance=Decimal("0"),
        value_dec31_eur=Decimal(qty) * 10, fiscal_valuation=Decimal(qty) * 10,
        price=Decimal("10"), exchange="XMAD",
    )


def _report(year: int, holdings, complete: bool) -> DGAnnualReport:
    return DGAnnualReport(
        fiscal_year=year, holdings=holdings, portfolio_snapshot_complete=complete,
    )


def _rows(db) -> list[tuple[str, Decimal]]:
    return sorted((h.isin, h.quantity) for h in db.query(PortfolioHolding).all())


def test_import_stores_the_certificate_with_its_marker(db, user_id):
    result = import_dg_report(
        db, _report(2025, [_holding(ENAGAS, "10")], True), "a" * 64, "dg-2025.pdf", user_id
    )

    assert result["counts"]["holdings"] == 1
    assert _rows(db) == [(ENAGAS, Decimal("10"))]
    record = db.query(ImportRecord).one()
    assert record.portfolio_snapshot_complete is True
    assert db.query(PortfolioHolding).one().import_id == record.id


def test_reimporting_the_year_replaces_its_rows(db, user_id):
    import_dg_report(
        db, _report(2025, [_holding(ENAGAS, "10")], True), "a" * 64, "v1.pdf", user_id
    )
    result = import_dg_report(
        db, _report(2025, [_holding(REPSOL, "4")], True), "b" * 64, "v2.pdf", user_id
    )

    assert result["status"] == "replaced"
    assert _rows(db) == [(REPSOL, Decimal("4"))]


def test_deleting_the_import_deletes_its_rows(db, user_id):
    result = import_dg_report(
        db, _report(2025, [_holding(ENAGAS, "10")], True), "a" * 64, "dg.pdf", user_id
    )

    _delete_import_data(db, result["import_id"])

    assert _rows(db) == []


def test_complete_certificate_closes_what_it_omits_partial_does_not(db, user_id):
    """End to end through the loader: the marker decides the authority."""
    first = import_dg_report(
        db, _report(2024, [], False), "c" * 64, "dg-2024.pdf", user_id
    )
    account_id = db.get(ImportRecord, first["import_id"]).account_id
    for isin in (ENAGAS, REPSOL):
        db.add(Transaction(
            account_id=account_id, type=TransactionType.BUY.value, trade_date=date(2024, 3, 1),
            isin=isin, name=isin, quantity=Decimal("10"), price=Decimal("10"), currency="EUR",
            exchange_rate=Decimal("1"), gross_amount=Decimal("100"), fees=Decimal("0"),
            withholding_tax=Decimal("0"), net_amount_eur=Decimal("100"),
        ))
    db.commit()

    import_dg_report(db, _report(2025, [_holding(ENAGAS, "10")], False), "d" * 64, "p.pdf", user_id)
    held = {p.isin for p in portfolio_service.get_open_positions(db, user_id, skip_prices=True)}
    assert held == {ENAGAS, REPSOL}

    import_dg_report(db, _report(2025, [_holding(ENAGAS, "10")], True), "e" * 64, "c.pdf", user_id)
    held = {p.isin for p in portfolio_service.get_open_positions(db, user_id, skip_prices=True)}
    assert held == {ENAGAS}


# ── Real reports ──────────────────────────────────────────────────────


@pytest.fixture
def real_reports():
    paths = [_FILES / f"DG-Informe Anual {y}.pdf" for y in (2024, 2025)]
    if not all(p.exists() for p in paths):
        pytest.skip("real DEGIRO annual reports not in files/")
    return [dg.parse_dg_annual_report(p) for p in paths]


def test_real_certificates_agree_with_the_ledger(db, user_id, real_reports):
    """Both real certificates are complete, and persisting them changes nothing:
    every open DEGIRO position keeps its quantity and a known cost."""
    for i, report in enumerate(real_reports):
        assert report.portfolio_snapshot_complete is True
        import_dg_report(db, report, f"{i}" * 64, f"dg-{report.fiscal_year}.pdf", user_id)

    latest = real_reports[-1]
    certified = {h.isin: h.quantity for h in latest.holdings if h.quantity > 0}
    positions = portfolio_service.get_open_positions(
        db, user_id, skip_prices=True, aggregate=False
    )

    assert {p.isin: p.quantity for p in positions} == certified
    assert all(p.total_cost_eur is not None for p in positions)
