"""The cascade deletes share one list of dependent tables; keep it complete.

``_delete_import_data``, ``delete_account_cascade`` and ``delete_all_imports``
each used to name the dependent tables by hand, so a new table needed three
edits and forgetting one left orphans behind in only that scope. They now read
``_TX_DEPENDENT_TABLES`` and ``_IMPORT_DEPENDENT_TABLES``. This test walks the
schema: any table with a foreign key to ``transactions`` or ``import_records``
must be in the matching list, or be one of the tables every caller scopes on
its own terms.
"""

from backend.models import Base, DataIssue, TaxResult, Transaction
from backend.services.import_service import _IMPORT_DEPENDENT_TABLES, _TX_DEPENDENT_TABLES

# Reference imports but are deleted by each caller with its own scope: the
# per-import legacy casilla sweep, the per-account broker fallback, the per-user
# sweep of every issue. Adding a table here is a deliberate decision.
_SCOPED_PER_CALLER = {Transaction.__table__, TaxResult.__table__, DataIssue.__table__}


def _tables_referencing(target: str) -> set:
    return {
        table
        for table in Base.metadata.sorted_tables
        if any(fk.column.table.name == target for fk in table.foreign_keys)
    }


def test_every_table_referencing_a_transaction_is_cascaded():
    listed = {model.__table__ for model in _TX_DEPENDENT_TABLES}
    assert _tables_referencing("transactions") == listed


def test_every_table_referencing_an_import_is_cascaded_or_scoped():
    listed = {model.__table__ for model in _IMPORT_DEPENDENT_TABLES}
    assert _tables_referencing("import_records") == listed | _SCOPED_PER_CALLER


def test_tx_dependents_precede_transactions_and_import_dependents_precede_imports():
    """Each listed table references the parent the list deletes it before."""
    for model in _TX_DEPENDENT_TABLES:
        cols = {c.name for c in model.__table__.columns}
        assert {"buy_tx_id", "sell_tx_id"} <= cols, model.__name__
    for model in _IMPORT_DEPENDENT_TABLES:
        assert "import_id" in model.__table__.columns, model.__name__
