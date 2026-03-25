"""Pydantic schemas for API responses."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class ImportResult(BaseModel):
    status: str
    message: str | None = None
    import_id: int | None = None
    fiscal_year: int | None = None
    counts: dict[str, int] | None = None


class TransactionOut(BaseModel):
    id: int
    type: str
    trade_date: date
    isin: str | None
    name: str
    country: str | None
    quantity: Decimal
    price: Decimal
    currency: str
    gross_amount: Decimal
    fees: Decimal
    withholding_tax: Decimal
    net_amount_eur: Decimal
    casilla: int | None
    holding_period: str | None

    model_config = {"from_attributes": True}


class DividendSummary(BaseModel):
    isin: str
    name: str
    country: str | None
    total_gross_eur: Decimal
    total_withholding_eur: Decimal
    total_net_eur: Decimal
    payment_count: int


class CapitalGainOut(BaseModel):
    id: int
    isin: str
    name: str
    buy_date: date
    sell_date: date
    quantity: Decimal
    cost_basis_eur: Decimal
    proceeds_eur: Decimal
    realized_pl_eur: Decimal
    holding_period: str | None

    model_config = {"from_attributes": True}


class CasillaOut(BaseModel):
    modelo: int
    casilla: int
    description: str
    amount_eur: Decimal
    broker: str | None

    model_config = {"from_attributes": True}


class BrokerAmount(BaseModel):
    broker: str
    amount_eur: Decimal


class AggregatedCasillaOut(BaseModel):
    modelo: int
    casilla: int
    description: str
    amount_eur: Decimal
    brokers: list[BrokerAmount]


class FiscalSummary(BaseModel):
    fiscal_year: int
    total_dividends_gross: Decimal
    total_dividends_net: Decimal
    total_withholdings: Decimal
    total_gains: Decimal
    total_losses: Decimal
    net_capital_gains: Decimal
    casillas: list[AggregatedCasillaOut]


class AccountOut(BaseModel):
    id: int
    broker: str
    account_id: str
    name: str
    currency: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportRecordOut(BaseModel):
    id: int
    filename: str
    broker: str
    fiscal_year: int | None
    imported_at: datetime
    record_count: int

    model_config = {"from_attributes": True}


class DashboardStats(BaseModel):
    total_transactions: int
    total_dividends_eur: Decimal
    total_gains_eur: Decimal
    total_losses_eur: Decimal
    net_pl_eur: Decimal
    accounts: int
    imports: int
    fiscal_years: list[int]
