"""Declarative base and the enums shared by every domain."""

from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass


class SchemaStamp(Base):
    """The Cloud Run revision whose startup last applied the schema DDL.

    One row, id=1: the revision name plus when it stamped it. Read at startup so
    later cold starts of the same revision skip ~200 Neon round-trips (6.3 s
    measured). A new deploy is a new revision, so it always runs the DDL once.
    Not user-scoped.
    """

    __tablename__ = "schema_stamp"

    id: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[str] = mapped_column(String(100), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


class Broker(PyEnum):
    BBVA = "BBVA"
    DEGIRO = "DEGIRO"
    ETORO = "ETORO"
    IBKR = "IBKR"
    ING = "ING"
    TR = "TR"


class TransactionType(PyEnum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    FEE = "FEE"
    SPINOFF = "SPINOFF"
    CORPORATE_ACTION = "CORPORATE_ACTION"
