"""Regression tests for transaction-scoped financial mutation locks."""

from types import SimpleNamespace
from unittest.mock import Mock

from backend.services import db_locks
from backend.services.db_locks import _lock_key, advisory_xact_lock, lock_import_slot


def _session(dialect_name: str) -> Mock:
    db = Mock()
    db.get_bind.return_value = SimpleNamespace(
        dialect=SimpleNamespace(name=dialect_name)
    )
    return db


def test_advisory_key_is_stable_and_namespaced():
    assert _lock_key("fifo", 1) == _lock_key("fifo", 1)
    assert _lock_key("fifo", 1) != _lock_key("import", 1)
    assert _lock_key("fifo", 1) != _lock_key("fifo", 2)


def test_postgres_uses_transaction_scoped_advisory_lock():
    db = _session("postgresql")

    advisory_xact_lock(db, "fifo", 7)

    statement, params = db.execute.call_args.args
    assert "pg_advisory_xact_lock" in str(statement)
    assert params == {"lock_key": _lock_key("fifo", 7)}


def test_non_postgres_does_not_execute_advisory_sql():
    db = _session("sqlite")

    lock_import_slot(db, 3, "TR", 2024, "statement-hash")

    db.execute.assert_not_called()


def test_import_lock_order_covers_account_file_slot_and_fifo(monkeypatch):
    acquired = []
    monkeypatch.setattr(
        db_locks,
        "advisory_xact_lock",
        lambda db, namespace, *parts: acquired.append((namespace, parts)),
    )

    lock_import_slot(Mock(), 3, "TR", 2024, "statement-hash")

    assert acquired == [
        ("import-account", (3, "TR")),
        ("import-file", ("TR", "statement-hash")),
        ("import-slot", (3, "TR", 2024)),
        ("fifo-recalculation", (3,)),
    ]
