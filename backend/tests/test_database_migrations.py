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
