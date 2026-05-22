"""Tests for import service duplicate detection and replacement logic."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, Broker, ImportRecord, TaxLot, TaxResult, Transaction, User
from backend.services.import_service import (
    _check_duplicate,
    _check_year_duplicate,
    _delete_import_data,
)


@pytest.fixture
def db():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def user_id(db) -> int:
    user = User(email="test@example.com", name="Test", password_hash="x")
    db.add(user)
    db.flush()
    return user.id


def _make_import(db, user_id, broker="TR", fiscal_year=2024, file_hash="abc123"):
    """Helper to create a minimal import record with related data."""
    from backend.models import Account, TransactionType

    # Create account
    acct = Account(broker=broker, account_id="test", name="Test", user_id=user_id)
    db.add(acct)
    db.flush()

    # Create import record
    rec = ImportRecord(
        account_id=acct.id,
        filename="test.pdf",
        file_hash=file_hash,
        broker=broker,
        fiscal_year=fiscal_year,
        record_count=2,
    )
    db.add(rec)
    db.flush()

    # Create a transaction
    tx = Transaction(
        account_id=acct.id,
        import_id=rec.id,
        type=TransactionType.DIVIDEND.value,
        trade_date=date(fiscal_year, 6, 15),
        isin="US0378331005",
        name="Apple",
        quantity=Decimal("10"),
        price=Decimal("0.96"),
        gross_amount=Decimal("9.6"),
        fees=Decimal("0"),
        net_amount_eur=Decimal("9.6"),
    )
    db.add(tx)
    db.flush()

    # Create a tax result
    tr = TaxResult(
        user_id=user_id,
        fiscal_year=fiscal_year,
        broker=broker,
        modelo=100,
        casilla=29,
        description="Dividendos",
        amount_eur=Decimal("9.6"),
    )
    db.add(tr)
    db.flush()

    return rec, tx, tr


class TestCheckDuplicate:
    def test_no_duplicate(self, db):
        assert _check_duplicate(db, "nonexistent", Broker.TR) is None

    def test_exact_hash_match(self, db, user_id):
        rec, _, _ = _make_import(db, user_id, file_hash="hash1")
        result = _check_duplicate(db, "hash1", Broker.TR)
        assert result is not None
        assert result.id == rec.id

    def test_same_hash_different_broker(self, db, user_id):
        _make_import(db, user_id, broker="TR", file_hash="hash1")
        assert _check_duplicate(db, "hash1", Broker.DEGIRO) is None


class TestCheckYearDuplicate:
    def test_no_year_duplicate(self, db):
        assert _check_year_duplicate(db, Broker.TR, 2024) is None

    def test_same_broker_year(self, db, user_id):
        rec, _, _ = _make_import(db, user_id, broker="TR", fiscal_year=2024)
        result = _check_year_duplicate(db, Broker.TR, 2024)
        assert result is not None
        assert result.id == rec.id

    def test_same_broker_different_year(self, db, user_id):
        _make_import(db, user_id, broker="TR", fiscal_year=2024)
        assert _check_year_duplicate(db, Broker.TR, 2025) is None

    def test_different_broker_same_year(self, db, user_id):
        _make_import(db, user_id, broker="TR", fiscal_year=2024)
        assert _check_year_duplicate(db, Broker.DEGIRO, 2024) is None


class TestDeleteImportData:
    def test_deletes_all_related_data(self, db, user_id):
        rec, tx, tr = _make_import(db, user_id)

        # Verify data exists
        assert db.query(ImportRecord).count() == 1
        assert db.query(Transaction).count() == 1
        assert db.query(TaxResult).count() == 1

        _delete_import_data(db, rec.id)

        # Verify all deleted
        assert db.query(ImportRecord).count() == 0
        assert db.query(Transaction).count() == 0
        assert db.query(TaxResult).count() == 0

    def test_deletes_tax_lots(self, db):
        from backend.models import Account, TransactionType

        acct = Account(broker="TR", account_id="test2", name="Test2")
        db.add(acct)
        db.flush()

        rec = ImportRecord(
            account_id=acct.id, filename="t.pdf", file_hash="h2",
            broker="TR", fiscal_year=2024, record_count=2,
        )
        db.add(rec)
        db.flush()

        buy = Transaction(
            account_id=acct.id, import_id=rec.id,
            type=TransactionType.BUY.value, trade_date=date(2024, 1, 1),
            isin="ES0130960018", name="Enagas", quantity=Decimal("10"),
            price=Decimal("15"), gross_amount=Decimal("150"),
            fees=Decimal("0"), net_amount_eur=Decimal("150"),
        )
        sell = Transaction(
            account_id=acct.id, import_id=rec.id,
            type=TransactionType.SELL.value, trade_date=date(2024, 6, 1),
            isin="ES0130960018", name="Enagas", quantity=Decimal("10"),
            price=Decimal("17"), gross_amount=Decimal("170"),
            fees=Decimal("0"), net_amount_eur=Decimal("170"),
        )
        db.add_all([buy, sell])
        db.flush()

        lot = TaxLot(
            buy_tx_id=buy.id, sell_tx_id=sell.id, isin="ES0130960018",
            quantity_bought=Decimal("10"), quantity_remaining=Decimal("0"),
            cost_basis_eur=Decimal("150"), quantity_sold=Decimal("10"),
            proceeds_eur=Decimal("170"), realized_pl_eur=Decimal("20"),
            close_date=date(2024, 6, 1),
        )
        db.add(lot)
        db.flush()

        assert db.query(TaxLot).count() == 1
        _delete_import_data(db, rec.id)
        assert db.query(TaxLot).count() == 0
        assert db.query(Transaction).count() == 0

    def test_nonexistent_import_is_noop(self, db):
        _delete_import_data(db, 9999)  # Should not raise

    def test_preserves_other_imports(self, db, user_id):
        rec1, _, _ = _make_import(db, user_id, broker="TR", file_hash="h1", fiscal_year=2024)
        _make_import(db, user_id, broker="DEGIRO", file_hash="h2", fiscal_year=2024)

        _delete_import_data(db, rec1.id)

        assert db.query(ImportRecord).count() == 1
        assert db.query(ImportRecord).first().broker == Broker.DEGIRO
