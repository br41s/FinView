"""Regression tests for FinView's additive startup migrations."""

from sqlalchemy import create_engine, inspect, text

from backend import database


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
