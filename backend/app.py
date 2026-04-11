"""FinView FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.auth import router as auth_router
from backend.api.billing import router as billing_router
from backend.api.accounts import router as accounts_router
from backend.api.imports import router as imports_router
from backend.api.transactions import router as transactions_router
from backend.api.portfolio import router as portfolio_router
from backend.api.fiscal import router as fiscal_router
from backend.api.charts import router as charts_router
from backend.api.options import router as options_router
from backend.database import engine
from backend.models import Base
from backend.services.options_scheduler import shutdown_scheduler

# Create tables on startup
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Shutdown APScheduler on app exit
    shutdown_scheduler()


app = FastAPI(
    title="FinView",
    description="Personal investment dashboard with broker imports and Spanish IRPF fiscal engine",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
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


@app.get("/api/health")
def health():
    return {"status": "ok"}
