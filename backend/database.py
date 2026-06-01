from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from backend.config import settings

connect_args = {}
# pool_pre_ping stays on: Neon autosuspends idle computes, so a connection can
# be dead by the next checkout — the ping turns that into a transparent reconnect
# instead of a request error. It costs one round-trip per checkout, which is the
# right trade for correctness on serverless Postgres.
engine_kwargs: dict = {"echo": False, "pool_pre_ping": True}

if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
else:
    # Postgres/Neon: size the pool for Cloud Run request concurrency (the
    # dashboard fans out ~10 queries at once) and recycle connections before
    # Neon's idle timeout can drop them underneath us.
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    engine_kwargs["pool_recycle"] = 1800

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    **engine_kwargs,
)
SessionLocal = sessionmaker(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Minimal additive "migrations" for columns added to tables that already exist in
# production. `Base.metadata.create_all` only creates missing tables — it never
# alters existing ones — and the project has no Alembic. Each entry is an
# idempotent ADD COLUMN applied at startup only when the column is missing.
# `ADD COLUMN <name> VARCHAR(n)` is valid on both SQLite and PostgreSQL.
_ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    ("alt_investments", "isin", "VARCHAR(12)"),
]


def ensure_columns() -> None:
    """Add any missing additive columns to existing tables (idempotent)."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table, column, col_type in _ADDITIVE_COLUMNS:
        if table not in tables:
            continue  # create_all will build it fresh, already including the column
        existing = {c["name"] for c in inspector.get_columns(table)}
        if column in existing:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))


# Annotated type aliases for FastAPI dependency injection
DbSession = Annotated[Session, Depends(get_db)]
LimitParam = Annotated[int, Query(le=1000)]
OffsetParam = Annotated[int, Query(ge=0)]
