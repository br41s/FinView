"""Everything FinView holds about one user: export it, or erase it.

GDPR arts. 15 and 20 (access, portability) and art. 17 (erasure) need the same
answer to one question — "which rows belong to this user?". Answering it twice,
in two hand-written table lists, is how an export ends up omitting a table that
the delete also forgets. So ownership is derived once, from the schema:

  a table is user-owned when it has a `user_id` column, or a foreign key into a
  table that is user-owned.

Every other table must be named in `GLOBAL_TABLES` (shared caches and reference
data). `test_user_data.py` fails when a new table is neither, so adding a table
forces the decision instead of silently leaving data behind after a deletion.
"""

from collections.abc import Iterator

from sqlalchemy import ColumnElement, Table, false, or_, select
from sqlalchemy.orm import Session

from backend.models import Base, User
from backend.services.db_locks import lock_fifo_recalculation

# Shared caches and reference data: no row describes a user.
GLOBAL_TABLES = frozenset({
    "alt_investment_catalog",
    "exchange_rates",
    "fred_rates",
    "geo_flight_samples",
    "geo_generative_answers",
    "geo_region_samples",
    "geo_rule_stats",
    "price_cache",
    "split_history_cache",
    "ticker_map",
})

_USERS = User.__table__

# Never leaves the database, not even to its owner: a hash is only useful to
# someone trying to crack it, and a broker token in an export file is a live
# credential sitting in someone's downloads folder.
_NEVER_EXPORTED = frozenset({"password_hash", "token_encrypted"})


def _owned_parents(table: Table) -> list[tuple[ColumnElement, Table]]:
    """(fk column, parent table) for each foreign key into another owned table."""
    return [
        (fk.parent, fk.column.table)
        for fk in table.foreign_keys
        if fk.column.table not in (_USERS, table) and is_user_owned(fk.column.table)
    ]


def is_user_owned(table: Table) -> bool:
    if table is _USERS or table.name in GLOBAL_TABLES:
        return False
    return "user_id" in table.c or bool(_owned_parents(table))


def owned_tables() -> list[Table]:
    """User-owned tables, parents before children (foreign-key order)."""
    return [t for t in Base.metadata.sorted_tables if is_user_owned(t)]


def _owned_rows(table: Table, user_id: int) -> ColumnElement[bool]:
    """Predicate selecting the rows of `table` that belong to `user_id`."""
    if "user_id" in table.c and not table.c.user_id.nullable:
        return table.c.user_id == user_id
    # Nullable or absent user_id: also follow the foreign keys, so a legacy row
    # with user_id NULL is still reached through the account or import it hangs off.
    clauses: list[ColumnElement[bool]] = []
    if "user_id" in table.c:
        clauses.append(table.c.user_id == user_id)
    for fk_column, parent in _owned_parents(table):
        parent_pk = next(iter(parent.primary_key.columns))
        clauses.append(fk_column.in_(select(parent_pk).where(_owned_rows(parent, user_id))))
    return or_(*clauses) if clauses else false()


def iter_user_export(db: Session, user: User) -> Iterator[tuple[str, Iterator[dict]]]:
    """Yield (table name, row iterator) for the account and every user-owned table.

    Rows are fetched in batches and handed over lazily so the endpoint can
    stream them: options snapshots are never pruned and can run to hundreds of
    thousands of rows, on an instance with 1 GiB.
    """
    profile = {c.name: getattr(user, c.name) for c in _USERS.c if c.name not in _NEVER_EXPORTED}
    yield "users", iter([profile])
    for table in owned_tables():
        columns = [c for c in table.c if c.name not in _NEVER_EXPORTED]
        query = (
            select(*columns)
            .where(_owned_rows(table, user.id))
            .execution_options(yield_per=1000)
        )
        yield table.name, (dict(row) for row in db.execute(query).mappings())


def delete_user(db: Session, user: User) -> None:
    """Erase the account and every row that belongs to it. Does not commit.

    Children first, so no foreign key is ever left pointing at a deleted row.
    The FIFO lock keeps an import or recalculation for the same user from
    writing ledger rows while they are being removed.
    """
    lock_fifo_recalculation(db, user.id)
    for table in reversed(owned_tables()):
        db.execute(table.delete().where(_owned_rows(table, user.id)))
    db.execute(_USERS.delete().where(_USERS.c.id == user.id))
    db.expunge(user)
