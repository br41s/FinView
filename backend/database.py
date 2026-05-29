from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy import create_engine
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


# Annotated type aliases for FastAPI dependency injection
DbSession = Annotated[Session, Depends(get_db)]
LimitParam = Annotated[int, Query(le=1000)]
OffsetParam = Annotated[int, Query(ge=0)]
