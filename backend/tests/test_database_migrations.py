"""Regression tests for FinView's additive startup migrations."""

from sqlalchemy import create_engine, inspect, text

from backend import database
from backend.models import Base


def test_ensure_columns_adds_data_issue_owner_and_index(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE data_issues (id INTEGER PRIMARY KEY)"))
    monkeypatch.setattr(database, "engine", engine)

    database.ensure_columns()
    database.ensure_columns()

    inspector = inspect(engine)
    assert "user_id" in {column["name"] for column in inspector.get_columns("data_issues")}
    assert "ix_data_issues_user_id" in {
        index["name"] for index in inspector.get_indexes("data_issues")
    }


def test_ensure_columns_adds_fifo_breakdown_and_version(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE fifo_adjustments (id INTEGER PRIMARY KEY)"
        ))
        connection.execute(text(
            "CREATE TABLE cross_broker_lots (id INTEGER PRIMARY KEY)"
        ))
    monkeypatch.setattr(database, "engine", engine)

    database.ensure_columns()
    database.ensure_columns()

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("fifo_adjustments")
    }
    assert {
        "broker_gains_eur",
        "broker_losses_eur",
        "fifo_gains_eur",
        "fifo_losses_eur",
        "calculation_version",
    } <= columns
    lot_columns = {
        column["name"]
        for column in inspect(engine).get_columns("cross_broker_lots")
    }
    assert "calculation_version" in lot_columns


def test_ensure_columns_adds_withholding_breakdown(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE transactions (id INTEGER PRIMARY KEY)"))

    monkeypatch.setattr(database, "engine", engine)

    database.ensure_columns()
    database.ensure_columns()

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("transactions")
    }
    assert {"domestic_withholding_tax", "foreign_withholding_tax"} <= columns


def test_ensure_columns_adds_portfolio_snapshot_marker(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE import_records (id INTEGER PRIMARY KEY)"
        ))
    monkeypatch.setattr(database, "engine", engine)

    database.ensure_columns()
    database.ensure_columns()

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("import_records")
    }
    assert "portfolio_snapshot_complete" in columns


def _leading_indexed_columns(inspector, table: str) -> set[str]:
    """Columns a query can seek on: leading column of any index, unique or PK."""
    covered: set[str] = set()
    for index in inspector.get_indexes(table):
        if index["column_names"]:
            covered.add(index["column_names"][0])
    for unique in inspector.get_unique_constraints(table):
        if unique["column_names"]:
            covered.add(unique["column_names"][0])
    primary = inspector.get_pk_constraint(table).get("constrained_columns") or []
    if primary:
        covered.add(primary[0])
    return covered


def test_every_foreign_key_column_is_indexed(monkeypatch):
    """No FK column may lack a leading index.

    Postgres indexes the referenced primary key but never the referencing column,
    so an unindexed FK turns every tenant-scoped join (transactions → accounts →
    user_id) into a sequential scan. This guards new models too: add a table with
    an unindexed FK and this fails until it is registered in _ADDITIVE_INDEXES.
    """
    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(database, "engine", engine)
    Base.metadata.create_all(bind=engine)
    database.ensure_columns()

    inspector = inspect(engine)
    unindexed: list[str] = []
    for table in sorted(inspector.get_table_names()):
        covered = _leading_indexed_columns(inspector, table)
        fk_columns = {
            column
            for fk in inspector.get_foreign_keys(table)
            for column in fk["constrained_columns"]
        }
        unindexed.extend(f"{table}.{column}" for column in sorted(fk_columns - covered))

    assert not unindexed, (
        "Foreign-key columns without a leading index: "
        + ", ".join(unindexed)
        + ". Register each in database._ADDITIVE_INDEXES."
    )


def test_ensure_columns_creates_indexes_on_preexisting_tables(monkeypatch):
    """Production tables already exist, so create_all skips them entirely."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE transactions (id INTEGER PRIMARY KEY, account_id INTEGER)"
        ))
    monkeypatch.setattr(database, "engine", engine)

    database.ensure_columns()
    database.ensure_columns()  # idempotent

    assert "ix_transactions_account_id" in {
        index["name"] for index in inspect(engine).get_indexes("transactions")
    }
