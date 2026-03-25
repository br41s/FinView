"""FinView FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.imports import router as imports_router
from backend.api.transactions import router as transactions_router
from backend.api.fiscal import router as fiscal_router
from backend.database import engine
from backend.models import Base

# Create tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="FinView",
    description="Personal investment dashboard with broker imports and Spanish IRPF fiscal engine",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(imports_router, prefix="/api")
app.include_router(transactions_router, prefix="/api")
app.include_router(fiscal_router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
