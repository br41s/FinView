"""Tests for import service duplicate detection and replacement logic."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, Broker, ImportRecord, TaxLot, TaxResult, Transaction, User
from backend.services.import_service import (
    _check_duplicate,
    _check_year_duplicate,
    _delete_import_data,
)

_FILES = Path(__file__).resolve().parents[2] / "files"
TR_DE_PDF = _FILES / "TR-Tax report - Period DE IBAN-2025.pdf"
TR_ES_PDF = _FILES / "TR-Tax report - Period ES IBAN-2025.pdf"


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


def _make_import(db, user_id, broker="TR", fiscal_year=2024, file_hash="abc123", source_variant=None):
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
        source_variant=source_variant,
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


class TestCheckYearDuplicateVariant:
    """Variant-aware year key: complementary same-year TR reports coexist."""

    def test_variant_filter_isolates_slot(self, db, user_id):
        _make_import(
            db, user_id, broker="TR", fiscal_year=2025,
            file_hash="h_de", source_variant="tr_de_premigration",
        )
        # The post-migration variant is a different slot → no duplicate.
        assert _check_year_duplicate(db, Broker.TR, 2025, "es_branch") is None
        # The same variant is found → replaces itself.
        same = _check_year_duplicate(db, Broker.TR, 2025, "tr_de_premigration")
        assert same is not None

    def test_no_variant_matches_any(self, db, user_id):
        """Legacy call (no variant) keeps matching any same-year row."""
        _make_import(
            db, user_id, broker="TR", fiscal_year=2025,
            file_hash="h_de", source_variant="tr_de_premigration",
        )
        assert _check_year_duplicate(db, Broker.TR, 2025) is not None


@pytest.mark.skipif(
    not (TR_DE_PDF.exists() and TR_ES_PDF.exists()),
    reason="TR DE/ES IBAN migration-year PDFs not available in files/",
)
class TestMigrationYearCoexistence:
    """End-to-end: the two FY2025 TR reports (pre/post migration) import
    side by side and their casillas aggregate instead of overwriting."""

    def _import_both(self, db, user_id):
        from backend.importers.tr import compute_file_hash, parse_tr_tax_report
        from backend.services.import_service import import_tr_report

        de = parse_tr_tax_report(TR_DE_PDF)
        es = parse_tr_tax_report(TR_ES_PDF)
        r_de = import_tr_report(db, de, compute_file_hash(TR_DE_PDF), "de.pdf", user_id)
        r_es = import_tr_report(db, es, compute_file_hash(TR_ES_PDF), "es.pdf", user_id)
        return r_de, r_es

    def test_both_imports_survive(self, db, user_id):
        self._import_both(db, user_id)
        recs = db.query(ImportRecord).filter(ImportRecord.fiscal_year == 2025).all()
        assert len(recs) == 2
        variants = {r.source_variant for r in recs}
        assert variants == {"tr_de_premigration", "es_branch"}

    def test_no_replacement_reported(self, db, user_id):
        r_de, r_es = self._import_both(db, user_id)
        assert r_de["status"] == "success"
        assert r_es["status"] == "success"  # did NOT replace the DE report

    def test_casilla_29_aggregates(self, db, user_id):
        self._import_both(db, user_id)
        rows = (
            db.query(TaxResult)
            .filter(TaxResult.fiscal_year == 2025, TaxResult.casilla == 29)
            .all()
        )
        # DE 4103.886846 + ES 2487.95
        total = sum(r.amount_eur for r in rows)
        assert abs(total - Decimal("6591.836846")) < Decimal("0.01")

    def test_pre_migration_has_no_section_vi(self, db, user_id):
        """DE report contributes fiscal figures only — its raw Section VI
        buy/sell history is not imported (only the one realized-gain pair)."""
        from backend.importers.tr import parse_tr_tax_report

        de = parse_tr_tax_report(TR_DE_PDF)
        assert de.transactions == []
        assert de.source_variant == "tr_de_premigration"

    def test_reimport_de_replaces_own_slot(self, db, user_id):
        from backend.importers.tr import compute_file_hash, parse_tr_tax_report
        from backend.services.import_service import import_tr_report

        self._import_both(db, user_id)
        # Re-upload the DE report under a new hash (e.g. a corrected file):
        # it must replace only the DE slot, leaving ES intact → still 2 rows.
        de = parse_tr_tax_report(TR_DE_PDF)
        import_tr_report(db, de, "de-v2-hash", "de2.pdf", user_id)
        recs = db.query(ImportRecord).filter(ImportRecord.fiscal_year == 2025).all()
        assert len(recs) == 2
        assert {r.source_variant for r in recs} == {"tr_de_premigration", "es_branch"}
