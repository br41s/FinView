from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import settings

engine = create_engine(settings.database_url, echo=False)
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
