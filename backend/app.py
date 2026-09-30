"""FinView FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.api.auth import router as auth_router
from backend.api.billing import router as billing_router
from backend.api.accounts import router as accounts_router
from backend.api.imports import router as imports_router
from backend.api.transactions import router as transactions_router
from backend.api.portfolio import router as portfolio_router
from backend.api.fiscal import router as fiscal_router
from backend.api.charts import router as charts_router
from backend.api.options import router as options_router
from backend.api.geo import router as geo_router
from backend.api.zonas_clave import router as zonas_clave_router
from backend.api.alt_investments import router as alt_investments_router
from backend.api.users import router as users_router
from backend.config import PRODUCTION_LIKE_ENVS, settings
from backend.database import engine, ensure_columns, ensure_constraints
from backend.models import Base
from backend.services.geo.owner import ensure_geo_owner
from backend.services.geo.scheduler import shutdown_scheduler as shutdown_geo_scheduler
from backend.services.options_scheduler import shutdown_scheduler
from backend.services.rate_limit import limiter
from backend.services.zonas_clave_scheduler import shutdown_scheduler as shutdown_zc_scheduler

# Without a root handler, module loggers fall back to Python's WARNING-level
# lastResort handler and every logger.info() in the codebase is dropped.
# Root stays at WARNING so third-party libs (httpx, apscheduler) don't get chatty.
logging.basicConfig(format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logging.getLogger("backend").setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# Create tables on startup, then apply any additive column / constraint migrations
Base.metadata.create_all(bind=engine)
ensure_columns()
ensure_constraints()


def _start_instance_background_workers() -> None:
    """Start workers only on runtimes with CPU outside HTTP requests."""
    import threading

    from backend.api.options import _invalidate_european_availability_cache
    from backend.services.geo.ais_collector import start as start_ais_collector
    from backend.services.options_scraper import _load_eurex_rdf

    _invalidate_european_availability_cache()

    def _preload_eurex():
        if _load_eurex_rdf():
            _invalidate_european_availability_cache()

    threading.Thread(target=_preload_eurex, daemon=True, name="eurex-rdf-preload").start()
    start_ais_collector()

    def _sync_fx_rates():
        try:
            from backend.services.exchange_rates import sync_rates

            sync_rates()
        except Exception as exc:  # noqa: BLE001 - background best-effort
            logger.warning("[ecb-sync] skipped: %s", exc)

    threading.Thread(target=_sync_fx_rates, daemon=True, name="ecb-fx-sync").start()

    def _sync_fred_rates():
        try:
            from backend.services.fred_rates import sync_rates as sync_fred
            from backend.services.macro_context import sync_macro

            sync_fred()
            sync_macro()
        except Exception as exc:  # noqa: BLE001 - background best-effort
            logger.warning("[fred-sync] skipped: %s", exc)

    threading.Thread(target=_sync_fred_rates, daemon=True, name="fred-rate-sync").start()

    def _refresh_cnmv_catalog():
        try:
            from backend.database import SessionLocal
            from backend.services.cnmv_catalog import catalog_is_stale, refresh_iic_catalog

            with SessionLocal() as db:
                stale = catalog_is_stale(db)
            if stale:
                refresh_iic_catalog()
        except Exception as exc:  # noqa: BLE001 - background best-effort
            logger.warning("[cnmv-catalog] skipped: %s", exc)

    threading.Thread(target=_refresh_cnmv_catalog, daemon=True, name="cnmv-catalog-refresh").start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One-off data migration: legacy options/zonas watchlists → followed_instruments.
    # Runs in lifespan (not at import) so merely importing backend.app — e.g. from
    # tests — never mutates a real database. No-op after the first boot.
    from backend.database import SessionLocal as _SessionLocal
    from backend.services.watchlist_service import migrate_legacy_watchlists

    try:
        with _SessionLocal() as _db:
            migrate_legacy_watchlists(_db)
    except Exception:
        # Concurrent cold-start race (two instances migrating at once) or a
        # transient DB error: nothing was committed, so the migration simply
        # retries on the next boot. Never take the instance down for this.
        logger.warning("watchlist migration failed — will retry next boot", exc_info=True)

    # Same category: the Ideas owner is created once and adopts the first
    # account's history on that boot. Its own error handling logs and lets the
    # next request retry through geo_owner_id.
    ensure_geo_owner()

    if settings.request_scoped_runtime:
        logger.info(
            "Request-scoped runtime enabled; skipping instance background workers"
        )
    else:
        _start_instance_background_workers()

    yield
    shutdown_scheduler()
    shutdown_zc_scheduler()
    shutdown_geo_scheduler()


app = FastAPI(
    title="FinView",
    description="Personal investment dashboard with broker imports and Spanish IRPF fiscal engine",
    version="0.2.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(billing_router, prefix="/api")
app.include_router(accounts_router, prefix="/api")
app.include_router(imports_router, prefix="/api")
app.include_router(transactions_router, prefix="/api")
app.include_router(portfolio_router, prefix="/api")
app.include_router(fiscal_router, prefix="/api")
app.include_router(charts_router, prefix="/api")
app.include_router(options_router, prefix="/api")
app.include_router(zonas_clave_router, prefix="/api")
app.include_router(geo_router, prefix="/api")
app.include_router(alt_investments_router, prefix="/api")
app.include_router(users_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/health/ready")
def readiness():
    """Confirm startup completed; startup itself already requires the database."""
    if settings.env.lower() in PRODUCTION_LIKE_ENVS and not settings.request_scoped_runtime:
        raise HTTPException(
            status_code=503,
            detail="request-scoped runtime is required in production",
        )
    return {
        "status": "ready",
        "database": "startup-ok",
        "environment": settings.env.lower(),
        "runtime": "request-scoped" if settings.request_scoped_runtime else "local",
    }
