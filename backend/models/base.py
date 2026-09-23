"""Declarative base and the enums shared by every domain."""

from enum import Enum as PyEnum

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass


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
