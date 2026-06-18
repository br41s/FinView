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
TR_CSV = _FILES / "TR-Transaction-export.csv"
TR_2024_PDF = _FILES / "TR-Tax Report 2024.pdf"


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
        from backend.importers.tr import parse_tr_tax_report
        from backend.services.import_service import import_tr_report

        self._import_both(db, user_id)
        # Re-upload the DE report under a new hash (e.g. a corrected file):
        # it must replace only the DE slot, leaving ES intact → still 2 rows.
        de = parse_tr_tax_report(TR_DE_PDF)
        import_tr_report(db, de, "de-v2-hash", "de2.pdf", user_id)
        recs = db.query(ImportRecord).filter(ImportRecord.fiscal_year == 2025).all()
        assert len(recs) == 2
        assert {r.source_variant for r in recs} == {"tr_de_premigration", "es_branch"}


@pytest.mark.skipif(
    not (TR_DE_PDF.exists() and TR_ES_PDF.exists() and TR_CSV.exists()),
    reason="TR migration PDFs + transaction CSV not available in files/",
)
class TestPdfCsvComposition:
    """The CSV ledger and the PDFs compose into one accurate account: taxes
    from the PDFs, cost basis from the CSV, with no income double-counting."""

    def _import_all(self, db, user_id):
        from backend.importers.tr import compute_file_hash as ph, parse_tr_tax_report
        from backend.importers.tr_csv import compute_file_hash as ch, parse_tr_csv
        from backend.services.import_service import import_tr_csv_report, import_tr_report

        import_tr_report(db, parse_tr_tax_report(TR_DE_PDF), ph(TR_DE_PDF), "de.pdf", user_id)
        import_tr_report(db, parse_tr_tax_report(TR_ES_PDF), ph(TR_ES_PDF), "es.pdf", user_id)
        return import_tr_csv_report(db, parse_tr_csv(TR_CSV), ch(TR_CSV), "tx.csv", user_id)

    def test_single_tr_account(self, db, user_id):
        from backend.models import Account

        self._import_all(db, user_id)
        tr_accounts = db.query(Account).filter(Account.broker == Broker.TR).all()
        assert len(tr_accounts) == 1
        assert tr_accounts[0].account_id == "TR"

    def test_csv_is_ledger_only(self, db, user_id):
        """CSV imports buy/sell/spin-off, skips all dividend + interest rows."""
        from backend.models import Transaction, TransactionType

        res = self._import_all(db, user_id)
        assert res["counts"]["income_skipped"] > 0
        # Every CSV-imported transaction is a ledger type, never income.
        csv_tx = (
            db.query(Transaction)
            .filter(Transaction.import_id == res["import_id"])
            .all()
        )
        assert csv_tx  # the ledger landed
        ledger_types = {
            TransactionType.BUY, TransactionType.SELL, TransactionType.SPINOFF,
            TransactionType.BUY.value, TransactionType.SELL.value,
            TransactionType.SPINOFF.value,
        }
        assert all(t.type in ledger_types for t in csv_tx)

    def test_income_not_double_counted(self, db, user_id):
        """2025 dividend net comes from the PDFs only — the CSV must not add a
        second copy (which would roughly double it)."""
        from sqlalchemy import func
        from backend.models import Transaction, TransactionType

        self._import_all(db, user_id)
        net = (
            db.query(func.coalesce(func.sum(Transaction.net_amount_eur), 0))
            .filter(
                Transaction.type == TransactionType.DIVIDEND.value,
                func.substr(Transaction.trade_date, 1, 4) == "2025",
            )
            .scalar()
        )
        # PDF-only 2025 dividend net; doubling would push it past ~9000.
        assert Decimal("4000") < net < Decimal("7000")

    def test_positions_have_cost_basis(self, db, user_id):
        """The CSV ledger supplies cost basis for held positions, including the
        pre-migration buy of a position carried across the migration."""
        from backend.services.portfolio_service import get_open_positions

        self._import_all(db, user_id)
        positions = get_open_positions(db, user_id, skip_prices=True, aggregate=True)
        assert positions
        # Unibail (FR0013326246): bought pre-migration, held at year-end.
        uni = [p for p in positions if p.isin == "FR0013326246"]
        assert len(uni) == 1
        assert uni[0].quantity == Decimal("15")
        assert uni[0].total_cost_eur == Decimal("990")


@pytest.mark.skipif(
    not (TR_2024_PDF.exists() and TR_CSV.exists()),
    reason="TR 2024 full-year PDF + transaction CSV not available in files/",
)
class TestLegacyPdfNoLedgerDoubleCount:
    """The legacy full-year PDF is fiscal-only: its Section VI list is NOT
    stored, so it never double-counts the CSV ledger — while still
    contributing its year's casillas."""

    def _import(self, db, user_id):
        from backend.importers.tr import compute_file_hash as ph, parse_tr_tax_report
        from backend.importers.tr_csv import compute_file_hash as ch, parse_tr_csv
        from backend.services.import_service import import_tr_csv_report, import_tr_report

        import_tr_report(db, parse_tr_tax_report(TR_2024_PDF), ph(TR_2024_PDF), "2024.pdf", user_id)
        import_tr_csv_report(db, parse_tr_csv(TR_CSV), ch(TR_CSV), "tx.csv", user_id)

    def test_no_doubled_quantity(self, db, user_id):
        from backend.services.portfolio_service import get_open_positions

        self._import(db, user_id)
        positions = get_open_positions(db, user_id, skip_prices=True, aggregate=True)
        # Acerinox doubled to 400.5 when Section VI was stored on top of the CSV.
        ace = [p for p in positions if p.isin == "ES0132105018"]
        if ace:  # held position → must reflect the CSV ledger qty, not 2×
            assert ace[0].quantity == Decimal("200.272907")

    def test_2024_casillas_still_present(self, db, user_id):
        from backend.models import TaxResult

        self._import(db, user_id)
        c = {
            r.casilla: r.amount_eur
            for r in db.query(TaxResult).filter(TaxResult.fiscal_year == 2024).all()
        }
        assert c.get(29) == Decimal("5301.020528")  # dividends
        assert c.get(337) == Decimal("-2155.109352")  # losses
