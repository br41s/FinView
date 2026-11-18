"""Tests for the per-revision startup schema gate.

Cloud Run sets `K_REVISION` in every container, and a deploy is always a new
revision, so stamping the revision lets later cold starts skip the startup DDL
with one SELECT. Local dev, tests and CI have no `K_REVISION` and must keep
running the DDL exactly as before.
"""

import logging

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from backend import database
from backend.models import Base


def _fresh_engine(monkeypatch):
    """In-memory DB shared by every connection, so the stamp read sees create_all."""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(database, "engine", engine)
    return engine


def _stamp_rows(engine) -> list[tuple]:
    with engine.connect() as conn:
        return conn.execute(text("SELECT id, revision FROM schema_stamp")).all()


def test_without_revision_the_ddl_always_runs(monkeypatch):
    engine = _fresh_engine(monkeypatch)
    monkeypatch.delenv("K_REVISION", raising=False)

    assert database.ensure_schema(Base.metadata) is True
    assert database.ensure_schema(Base.metadata) is True

    assert "schema_stamp" in inspect(engine).get_table_names()
    assert _stamp_rows(engine) == []


def test_same_revision_runs_the_ddl_once(monkeypatch):
    engine = _fresh_engine(monkeypatch)
    monkeypatch.setenv("K_REVISION", "rev-a")

    calls = {"columns": 0, "constraints": 0}
    real_columns = database.ensure_columns
    real_constraints = database.ensure_constraints

    def counting_columns():
        calls["columns"] += 1
        real_columns()

    def counting_constraints():
        calls["constraints"] += 1
        real_constraints()

    monkeypatch.setattr(database, "ensure_columns", counting_columns)
    monkeypatch.setattr(database, "ensure_constraints", counting_constraints)

    assert database.ensure_schema(Base.metadata) is True
    assert database.ensure_schema(Base.metadata) is False

    assert _stamp_rows(engine) == [(1, "rev-a")]
    assert calls == {"columns": 1, "constraints": 1}


def test_new_revision_reruns_the_ddl_and_replaces_the_stamp(monkeypatch):
    engine = _fresh_engine(monkeypatch)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO schema_stamp (id, revision, applied_at) "
            "VALUES (1, 'rev-a', '2026-01-01 00:00:00')"
        ))
    monkeypatch.setenv("K_REVISION", "rev-b")

    assert database.ensure_schema(Base.metadata) is True

    assert _stamp_rows(engine) == [(1, "rev-b")]


def test_missing_stamp_table_is_recreated_and_stamped(monkeypatch):
    engine = _fresh_engine(monkeypatch)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE schema_stamp"))
    monkeypatch.setenv("K_REVISION", "rev-a")

    assert database.ensure_schema(Base.metadata) is True

    assert "schema_stamp" in inspect(engine).get_table_names()
    assert _stamp_rows(engine) == [(1, "rev-a")]


def test_ddl_failure_propagates_and_writes_no_stamp(monkeypatch):
    engine = _fresh_engine(monkeypatch)
    monkeypatch.setenv("K_REVISION", "rev-a")

    def boom():
        raise RuntimeError("DDL failed")

    monkeypatch.setattr(database, "ensure_columns", boom)

    with pytest.raises(RuntimeError, match="DDL failed"):
        database.ensure_schema(Base.metadata)

    # create_all already built the table, but the failed boot must leave it empty.
    assert _stamp_rows(engine) == []


def test_stamp_write_failure_only_warns(monkeypatch, caplog):
    engine = _fresh_engine(monkeypatch)
    monkeypatch.setattr(database, "engine", engine)

    with caplog.at_level(logging.WARNING, logger="backend.database"):
        database._stamp_revision("rev-a")  # table does not exist yet

    assert "Schema stamp write failed for rev-a" in caplog.text


def test_stamped_revision_is_none_without_the_table(monkeypatch):
    _fresh_engine(monkeypatch)

    assert database._stamped_revision() is None
