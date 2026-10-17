"""TR transaction-export CSV: scrip-dividend rights that were cashed out.

TR books a scrip dividend as an INTERMEDIATE_SECURITIES_DISTRIBUTION of rights
(a "-ANR-" line with its own ISIN) and ends it with a LIQUIDATION_DIVIDEND of
that ISIN when the rights are paid in cash. Only the distribution was imported,
as a SPINOFF, so the owner's FCC and Viscofan rights stayed open positions with
no price and no cost long after they were paid. These run on synthetic files:
the real export is not in the repo.
"""

import csv
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.importers.base import TxType
from backend.importers.tr_csv import parse_tr_csv
from backend.models import Base, DataIssue, User
from backend.services import data_supervisor, portfolio_service, split_history
from backend.services.import_service import import_tr_csv_report

HEADER = [
    "datetime", "date", "account_type", "category", "type", "asset_class", "name",
    "symbol", "shares", "price", "amount", "fee", "tax", "currency", "original_amount",
    "original_currency", "fx_rate", "description", "transaction_id", "counterparty_name",
    "counterparty_iban", "payment_reference", "mcc_code",
]

SHARES = "ES0122060314"   # FCC
RIGHTS = "ES0622060988"   # FOMENT.CON.CONTR. -ANR-


def _row(day, category, type_, isin, shares, name="X", price="", amount=""):
    return {
        "datetime": f"{day}T10:00:00.000Z", "date": day, "account_type": "DEFAULT",
        "category": category, "type": type_, "asset_class": "STOCK", "name": name,
        "symbol": isin, "shares": shares, "price": price, "amount": amount,
        "currency": "EUR",
    }


def _buy(day="2025-01-10", qty="175"):
    return _row(day, "TRADING", "BUY", SHARES, qty, "FCC", "10", f"-{int(qty) * 10}")


def _rights(day="2025-06-20", qty="175", isin=RIGHTS):
    return _row(day, "CORPORATE_ACTION", "INTERMEDIATE_SECURITIES_DISTRIBUTION", isin, qty,
                "FOMENT.CON.CONTR. -ANR-")


def _liquidation(day="2025-07-04", qty="-175", isin=RIGHTS):
    return _row(day, "CORPORATE_ACTION", "LIQUIDATION_DIVIDEND", isin, qty,
                "FOMENT.CON.CONTR. -ANR-")


def _write(tmp_path, rows):
    path = tmp_path / "tx.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER, restval="")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _spinoffs(report):
    return {
        t.isin: t.quantity for t in report.transactions if t.tx_type is TxType.SPINOFF
    }


# ── parser ───────────────────────────────────────────────────────────


def test_rights_cashed_out_in_the_same_file_are_not_a_position(tmp_path):
    report = parse_tr_csv(_write(tmp_path, [_buy(), _rights(), _liquidation()]))

    assert _spinoffs(report) == {}
    # The shares the rights came from are untouched.
    assert [t.isin for t in report.transactions if t.tx_type is TxType.BUY] == [SHARES]


def test_rights_still_open_at_export_time_stay_a_spinoff(tmp_path):
    report = parse_tr_csv(_write(tmp_path, [_buy(), _rights()]))

    assert _spinoffs(report) == {RIGHTS: Decimal("175")}


def test_a_partial_liquidation_leaves_the_rest_open(tmp_path):
    report = parse_tr_csv(_write(tmp_path, [_buy(), _rights(), _liquidation(qty="-100")]))

    assert _spinoffs(report) == {RIGHTS: Decimal("75")}


def test_a_liquidation_nets_distributions_oldest_first(tmp_path):
    rows = [_buy(), _rights("2025-06-20", "100"), _rights("2025-06-21", "75"),
            _liquidation(qty="-120")]

    report = parse_tr_csv(_write(tmp_path, rows))

    spun = [(t.trade_date.isoformat(), t.quantity)
            for t in report.transactions if t.tx_type is TxType.SPINOFF]
    assert spun == [("2025-06-21", Decimal("55"))]


def test_a_liquidation_only_nets_its_own_isin(tmp_path):
    other = "ES0684262944"   # VISCOFAN -ANR-
    rows = [_buy(), _rights(), _rights(isin=other, qty="50"), _liquidation(isin=other, qty="-50")]

    report = parse_tr_csv(_write(tmp_path, rows))

    assert _spinoffs(report) == {RIGHTS: Decimal("175")}


def test_a_liquidation_whose_rights_are_in_an_earlier_file_is_ignored(tmp_path):
    report = parse_tr_csv(_write(tmp_path, [_buy(), _liquidation()]))

    assert _spinoffs(report) == {}
    assert [t.tx_type for t in report.transactions] == [TxType.BUY]


@pytest.mark.parametrize("shares", ["", "abc", "0"])
def test_an_unreadable_liquidation_quantity_leaves_the_rights_open(tmp_path, shares):
    """Unknown is not zero the other way round either: without a quantity the
    rights stay visible (and flagged) rather than silently vanishing."""
    report = parse_tr_csv(_write(tmp_path, [_buy(), _rights(), _liquidation(qty=shares)]))

    assert _spinoffs(report) == {RIGHTS: Decimal("175")}


def test_a_liquidation_does_not_net_a_real_spin_off(tmp_path):
    spin = _row("2025-06-20", "CORPORATE_ACTION", "SPIN_OFF", RIGHTS, "175", "Spun Co")

    report = parse_tr_csv(_write(tmp_path, [_buy(), spin, _liquidation()]))

    assert _spinoffs(report) == {RIGHTS: Decimal("175")}


# ── through the import ───────────────────────────────────────────────


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(data_supervisor, "_try_resolve_ticker", lambda _isin: None)
    monkeypatch.setattr(split_history, "_fetch", lambda _ticker: [])
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_imported_cashed_out_rights_leave_no_position_and_no_warning(db, tmp_path):
    user = User(email="t@example.com", name="T", password_hash="x")
    db.add(user)
    db.flush()
    path = _write(tmp_path, [_buy(), _rights(), _liquidation()])

    import_tr_csv_report(db, parse_tr_csv(path), "h" * 64, "tx.csv", user.id)

    positions = portfolio_service.get_open_positions(db, user.id, skip_prices=True)
    assert {p.isin: p.quantity for p in positions} == {SHARES: Decimal("175")}
    assert not db.query(DataIssue).filter(
        DataIssue.isin == RIGHTS, DataIssue.issue_type == "missing_cost_basis"
    ).count()
