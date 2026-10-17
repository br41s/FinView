import logging
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from backend.config import settings

_logger = logging.getLogger(__name__)

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
    ("alt_investment_catalog", "nav", "NUMERIC(18, 4)"),
    ("alt_investment_catalog", "fund_size", "NUMERIC(18, 2)"),
    ("alt_investment_catalog", "data_date", "DATE"),
    ("import_records", "source_variant", "VARCHAR(20)"),
    ("import_records", "portfolio_snapshot_complete", "BOOLEAN"),
    ("import_records", "origin", "VARCHAR(20)"),
    ("tax_results", "import_id", "INTEGER"),
    ("transactions", "domestic_withholding_tax", "NUMERIC(18, 6)"),
    ("transactions", "foreign_withholding_tax", "NUMERIC(18, 6)"),
    ("data_issues", "user_id", "INTEGER"),
    ("fiscal_profiles", "prior_rcm_loss", "NUMERIC(18, 2)"),
    ("fiscal_profiles", "prior_gp_loss", "NUMERIC(18, 2)"),
    ("cross_broker_lots", "calculation_version", "VARCHAR(10)"),
    ("fifo_adjustments", "broker_gains_eur", "NUMERIC(18, 6)"),
    ("fifo_adjustments", "broker_losses_eur", "NUMERIC(18, 6)"),
    ("fifo_adjustments", "fifo_gains_eur", "NUMERIC(18, 6)"),
    ("fifo_adjustments", "fifo_losses_eur", "NUMERIC(18, 6)"),
    ("fifo_adjustments", "calculation_version", "VARCHAR(10)"),
    ("backtest_signals", "regime", "VARCHAR(12)"),
    ("backtest_signals", "regime_alignment", "VARCHAR(10)"),
    ("backtest_signals", "break_probability", "INTEGER"),
    ("backtest_signals", "alerted", "BOOLEAN"),
    ("backtest_signals", "alert_threshold", "INTEGER"),
    ("options_alerts", "regime_alignment", "VARCHAR(10)"),
    ("geo_signals", "notified_at", "TIMESTAMP"),
    ("geo_signals", "live_score", "NUMERIC(5, 2)"),
    ("geo_signals", "live_outcome", "VARCHAR(20)"),
    ("geo_signals", "live_rated_at", "TIMESTAMP"),
    ("geo_signals", "country", "VARCHAR(40)"),
    ("geo_signal_tickers", "live_change_pct", "NUMERIC(8, 3)"),
    ("geo_signal_tickers", "live_state", "VARCHAR(12)"),
    ("geo_signal_tickers", "final_state", "VARCHAR(12)"),
    ("geo_cycle_runs", "notify_failed", "INTEGER"),
    ("users", "terms_version", "VARCHAR(20)"),
    ("users", "terms_accepted_at", "TIMESTAMP"),
    ("fiscal_profiles", "health_data_consent_at", "TIMESTAMP"),
    ("segment_reports", "measure", "VARCHAR(30)"),
    ("segment_checks", "reader", "VARCHAR(20)"),
    ("ai_mention_checks", "reader", "VARCHAR(20)"),
]

# Foreign-key columns need explicit indexes: PostgreSQL indexes the *referenced*
# primary key automatically but never the referencing column, so every tenant-scoped
# join (transactions → accounts → user_id, the hottest path in the app) degrades to a
# sequential scan as the ledger grows. SQLite behaves the same way. Each entry is a
# CREATE INDEX IF NOT EXISTS applied at startup, which covers fresh installs and
# existing production tables alike.
_ADDITIVE_INDEXES: list[tuple[str, str, str]] = [
    ("data_issues", "ix_data_issues_user_id", "user_id"),
    ("accounts", "ix_accounts_user_id", "user_id"),
    ("transactions", "ix_transactions_account_id", "account_id"),
    ("transactions", "ix_transactions_import_id", "import_id"),
    ("import_records", "ix_import_records_account_id", "account_id"),
    ("tax_lots", "ix_tax_lots_buy_tx_id", "buy_tx_id"),
    ("tax_lots", "ix_tax_lots_sell_tx_id", "sell_tx_id"),
    ("tax_results", "ix_tax_results_user_id", "user_id"),
    ("tax_results", "ix_tax_results_import_id", "import_id"),
    ("cross_broker_lots", "ix_cross_broker_lots_sell_tx_id", "sell_tx_id"),
    ("portfolio_holdings", "ix_portfolio_holdings_account_id", "account_id"),
    ("portfolio_holdings", "ix_portfolio_holdings_import_id", "import_id"),
    ("option_assignments", "ix_option_assignments_import_id", "import_id"),
    ("options_agent_logs", "ix_options_agent_logs_user_id", "user_id"),
    ("unusual_activity", "ix_unusual_activity_user_id", "user_id"),
]

# Unique constraints that the model dropped but production tables may still
# carry. Each entry is matched on its exact column set (names auto-generated by
# the backend differ) and dropped idempotently. Only needed on Postgres —
# fresh SQLite tables are rebuilt from the current model without it.
_DROP_UNIQUE_CONSTRAINTS: list[tuple[str, frozenset[str]]] = [
    # tax_results once required one casilla row per (broker, year); migration
    # years legitimately need two, so the rows are now scoped by import_id.
    ("tax_results", frozenset({"user_id", "fiscal_year", "broker", "modelo", "casilla"})),
    # geo_signals was unique on the event id for all time, which contradicted a
    # pipeline that resolves a signal at +7d while the feeds keep publishing the
    # same id. The first recurrence raised IntegrityError and killed the cycle.
    # Replaced by uq_geo_sig_active_dedup below (see GeoSignal.__table_args__).
    ("geo_signals", frozenset({"user_id", "source", "external_id"})),
]

# Partial unique indexes: `create_all` never touches a table that already exists,
# and _ADDITIVE_INDEXES only emits plain indexes. Each entry is a
# CREATE UNIQUE INDEX IF NOT EXISTS with a WHERE clause -- identical syntax on
# SQLite and PostgreSQL -- applied after the obsolete constraints are dropped.
_ADDITIVE_UNIQUE_INDEXES: list[tuple[str, str, str, str]] = [
    (
        "geo_signals",
        "uq_geo_sig_active_dedup",
        "user_id, source, external_id",
        "status = 'active'",
    ),
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
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        except (OperationalError, ProgrammingError):
            # A concurrent cold start may have added it after our inspection.
            # Only suppress the race when the desired column now exists.
            if column not in {c["name"] for c in inspect(engine).get_columns(table)}:
                raise
    # Keep lookup columns usable on existing installations. Legacy issue rows
    # deliberately remain NULL and hidden until regenerated by the now-scoped
    # supervisor; inferring ownership from their contaminated payload is unsafe.
    for table, index_name, column in _ADDITIVE_INDEXES:
        if table not in tables:
            continue
        # Re-inspect per table: the ADD COLUMN pass above may have just added the
        # column this index targets. Indexing a column the table does not have
        # raises and would take startup down, so skip rather than fail — the next
        # boot indexes it once the column exists.
        if column not in {c["name"] for c in inspect(engine).get_columns(table)}:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column})"))


def ensure_constraints() -> None:
    """Reconcile unique constraints on existing tables (idempotent).

    Drops the obsolete ones and creates the partial unique indexes that replaced
    them, in that order — a table still carrying the old constraint would keep
    rejecting the rows the new index is meant to allow.

    Dropping is PostgreSQL-only: SQLite can't ALTER a constraint away. A fresh
    SQLite file is rebuilt from the model and never carries one, but a dev
    database created before the change does, so say so out loud instead of
    letting local behaviour silently diverge from production.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    is_postgres = engine.dialect.name == "postgresql"

    for table, columns in _DROP_UNIQUE_CONSTRAINTS:
        if table not in tables:
            continue
        for uc in inspector.get_unique_constraints(table):
            if frozenset(uc["column_names"]) != columns or not uc.get("name"):
                continue
            if not is_postgres:
                _logger.warning(
                    "%s still carries the obsolete unique constraint %s; SQLite cannot "
                    "drop it. Recreate the local database file to match production.",
                    table,
                    uc["name"],
                )
                continue
            with engine.begin() as conn:
                conn.execute(
                    text(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{uc["name"]}"')
                )

    for table, index_name, columns, where in _ADDITIVE_UNIQUE_INDEXES:
        if table not in tables:
            continue
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
                    f"ON {table} ({columns}) WHERE {where}"
                )
            )


# Annotated type aliases for FastAPI dependency injection
DbSession = Annotated[Session, Depends(get_db)]
LimitParam = Annotated[int, Query(le=1000)]
OffsetParam = Annotated[int, Query(ge=0)]
