"""FinView FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
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
from backend.api.zonas_clave import router as zonas_clave_router
from backend.api.alt_investments import router as alt_investments_router
from backend.config import settings
from backend.database import engine
from backend.models import Base
from backend.services.options_scheduler import shutdown_scheduler
from backend.services.rate_limit import limiter
from backend.services.zonas_clave_scheduler import shutdown_scheduler as shutdown_zc_scheduler

# Create tables on startup
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Preload Eurex RDF in background so the first European options request is fast
    import threading
    from backend.services.options_scraper import _load_eurex_rdf
    from backend.api.options import _invalidate_european_availability_cache

    # Clear any ISIN entries that may have been wrongly cached as False
    _invalidate_european_availability_cache()

    def _preload_eurex():
        if _load_eurex_rdf():
            _invalidate_european_availability_cache()

    threading.Thread(target=_preload_eurex, daemon=True, name="eurex-rdf-preload").start()

    # Sync ECB exchange rates in the background (never blocks requests)
    def _sync_fx_rates():
        try:
            from backend.services.exchange_rates import sync_rates

            sync_rates()
        except Exception as exc:  # noqa: BLE001 - background best-effort
            print(f"[ecb-sync] skipped: {exc}")

    threading.Thread(target=_sync_fx_rates, daemon=True, name="ecb-fx-sync").start()

    yield
    shutdown_scheduler()
    shutdown_zc_scheduler()


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
app.include_router(alt_investments_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
