"""Tests for the cross-broker FIFO engine."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import (
    Account,
    Base,
    Broker,
    CrossBrokerLot,
    FIFOAdjustment,
    TaxLot,
    Transaction,
    TransactionType,
)
from backend.services.fifo_engine import recalculate_cross_broker_fifo


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_account(db, broker: str) -> Account:
    acct = Account(broker=broker, account_id=f"test-{broker}", name=f"Test {broker}")
    db.add(acct)
    db.flush()
    return acct


def _make_buy(db, acct: Account, isin: str, trade_date: date,
              qty: Decimal, price: Decimal, import_id: int = 1) -> Transaction:
    tx = Transaction(
        account_id=acct.id,
        import_id=import_id,
        type=TransactionType.BUY.value,
        trade_date=trade_date,
        isin=isin,
        name="TestStock",
        quantity=qty,
        price=price,
        gross_amount=qty * price,
        fees=Decimal("0"),
        net_amount_eur=qty * price,
    )
    db.add(tx)
    db.flush()
    return tx


def _make_sell(db, acct: Account, isin: str, trade_date: date,
               qty: Decimal, price: Decimal, import_id: int = 1) -> Transaction:
    tx = Transaction(
        account_id=acct.id,
        import_id=import_id,
        type=TransactionType.SELL.value,
        trade_date=trade_date,
        isin=isin,
        name="TestStock",
        quantity=qty,
        price=price,
        gross_amount=qty * price,
        fees=Decimal("0"),
        net_amount_eur=qty * price,
    )
    db.add(tx)
    db.flush()
    return tx


def _make_broker_lot(db, acct: Account, isin: str, buy_date: date, sell_date: date,
                     qty: Decimal, cost: Decimal, proceeds: Decimal,
                     import_id: int = 1) -> TaxLot:
    """Create a broker TaxLot with its own synthetic buy/sell transactions.

    This mirrors what the import service does: separate synthetic transactions
    created only to link to a TaxLot. Real trades are tracked separately.
    """
    synth_buy = Transaction(
        account_id=acct.id, import_id=import_id,
        type=TransactionType.BUY.value, trade_date=buy_date,
        isin=isin, name="TestStock", quantity=qty,
        price=cost / qty if qty else Decimal("0"),
        gross_amount=cost, fees=Decimal("0"), net_amount_eur=cost,
    )
    db.add(synth_buy)
    db.flush()

    synth_sell = Transaction(
        account_id=acct.id, import_id=import_id,
        type=TransactionType.SELL.value, trade_date=sell_date,
        isin=isin, name="TestStock", quantity=qty,
        price=proceeds / qty if qty else Decimal("0"),
        gross_amount=proceeds, fees=Decimal("0"), net_amount_eur=proceeds,
    )
    db.add(synth_sell)
    db.flush()

    lot = TaxLot(
        buy_tx_id=synth_buy.id, sell_tx_id=synth_sell.id,
        isin=isin, quantity_bought=qty, quantity_remaining=Decimal("0"),
        cost_basis_eur=cost, quantity_sold=qty, proceeds_eur=proceeds,
        realized_pl_eur=proceeds - cost, close_date=sell_date,
    )
    db.add(lot)
    db.flush()
    return lot


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSingleBroker:
    """When all trades are on one broker, no cross-broker lots are created."""

    def test_single_broker_no_lots(self, db):
        acct = _make_account(db, Broker.TR.value)
        _make_buy(db, acct, "US0378331005", date(2023, 3, 1), Decimal("10"), Decimal("150"))
        _make_sell(db, acct, "US0378331005", date(2024, 6, 1), Decimal("10"), Decimal("180"))
        _make_broker_lot(db, acct, "US0378331005", date(2023, 3, 1), date(2024, 6, 1),
                         Decimal("10"), Decimal("1500"), Decimal("1800"))

        result = recalculate_cross_broker_fifo(db, 2024)

        assert result["lots_created"] == 0
        assert result["adjustments"] == 0
        assert db.query(CrossBrokerLot).count() == 0
        assert db.query(FIFOAdjustment).count() == 0


class TestMultiBrokerSameFIFO:
    """When cross-broker FIFO matches broker reports, adjustment = 0."""

    def test_two_brokers_same_result(self, db):
        """Buy at TR (oldest), sell at TR → FIFO picks TR buy → same as broker."""
        tr_acct = _make_account(db, Broker.TR.value)
        dg_acct = _make_account(db, Broker.DEGIRO.value)

        # Real buys: TR first (older), DG later
        _make_buy(db, tr_acct, "US0378331005", date(2023, 1, 15),
                  Decimal("10"), Decimal("100"))
        _make_buy(db, dg_acct, "US0378331005", date(2023, 6, 15),
                  Decimal("5"), Decimal("120"))

        # Real sell at TR
        _make_sell(db, tr_acct, "US0378331005", date(2024, 3, 1),
                   Decimal("10"), Decimal("150"))

        # Broker TaxLot (separate synthetic txs): cost=1000, proceeds=1500, pl=500
        _make_broker_lot(db, tr_acct, "US0378331005", date(2023, 1, 15), date(2024, 3, 1),
                         Decimal("10"), Decimal("1000"), Decimal("1500"))

        result = recalculate_cross_broker_fifo(db, 2024)

        # FIFO should also pick TR buy (oldest) → same result → no adjustment
        assert result["isins_analyzed"] == 1
        assert result["lots_created"] == 1
        assert result["adjustments"] == 0

        lot = db.query(CrossBrokerLot).first()
        assert lot.buy_broker == Broker.TR.value
        assert lot.sell_broker == Broker.TR.value
        assert lot.realized_pl_eur == Decimal("500")


class TestMultiBrokerDifferentFIFO:
    """When cross-broker FIFO differs from broker reports → adjustment created."""

    def test_older_buy_at_different_broker(self, db):
        """Buy at DG (cheaper, older), sell at TR → broker says one thing, FIFO says another."""
        dg_acct = _make_account(db, Broker.DEGIRO.value)
        tr_acct = _make_account(db, Broker.TR.value)

        # Real buys: DG first (cheaper, older), TR later
        _make_buy(db, dg_acct, "DE000BASF111", date(2023, 2, 1),
                  Decimal("20"), Decimal("50"))  # cost=1000
        _make_buy(db, tr_acct, "DE000BASF111", date(2023, 8, 1),
                  Decimal("20"), Decimal("70"))  # cost=1400

        # Real sell at TR: 20 shares @ 80 = 1600
        _make_sell(db, tr_acct, "DE000BASF111", date(2024, 5, 15),
                   Decimal("20"), Decimal("80"))

        # Broker TaxLot says: bought at TR @70, sold @80 → pl = 200
        _make_broker_lot(db, tr_acct, "DE000BASF111", date(2023, 8, 1), date(2024, 5, 15),
                         Decimal("20"), Decimal("1400"), Decimal("1600"))

        result = recalculate_cross_broker_fifo(db, 2024)

        # FIFO should pick DG buy (older, @50) → cost=1000, proceeds=1600, pl=600
        assert result["lots_created"] == 1
        assert result["adjustments"] == 1

        lot = db.query(CrossBrokerLot).first()
        assert lot.buy_broker == Broker.DEGIRO.value
        assert lot.sell_broker == Broker.TR.value
        assert lot.cost_basis_eur == Decimal("1000")
        assert lot.proceeds_eur == Decimal("1600")
        assert lot.realized_pl_eur == Decimal("600")

        adj = db.query(FIFOAdjustment).first()
        assert adj.broker_pl_eur == Decimal("200")
        assert adj.fifo_pl_eur == Decimal("600")
        assert adj.adjustment_eur == Decimal("400")  # 600 - 200


class TestPartialLotConsumption:
    """FIFO partially consumes a buy lot across multiple sells."""

    def test_partial_consumption(self, db):
        dg_acct = _make_account(db, Broker.DEGIRO.value)
        tr_acct = _make_account(db, Broker.TR.value)

        # Real buys
        _make_buy(db, dg_acct, "US0378331005", date(2023, 1, 1),
                  Decimal("30"), Decimal("50"))
        _make_buy(db, tr_acct, "US0378331005", date(2023, 6, 1),
                  Decimal("10"), Decimal("80"))

        # Real sells
        _make_sell(db, tr_acct, "US0378331005", date(2024, 3, 1),
                   Decimal("10"), Decimal("100"))
        _make_sell(db, dg_acct, "US0378331005", date(2024, 6, 1),
                   Decimal("10"), Decimal("90"))

        # Broker TaxLots (synthetic)
        _make_broker_lot(db, tr_acct, "US0378331005", date(2023, 6, 1), date(2024, 3, 1),
                         Decimal("10"), Decimal("800"), Decimal("1000"))
        _make_broker_lot(db, dg_acct, "US0378331005", date(2024, 1, 1), date(2024, 6, 1),
                         Decimal("10"), Decimal("500"), Decimal("900"))

        result = recalculate_cross_broker_fifo(db, 2024)

        # FIFO: DG buy @50 is oldest → first 10 for TR sell, next 10 for DG sell
        # TR sell: cost=500, proceeds=1000, pl=500 (broker said 200)
        # DG sell: cost=500, proceeds=900, pl=400 (broker said 400)
        assert result["lots_created"] == 2
        lots = db.query(CrossBrokerLot).order_by(CrossBrokerLot.id).all()

        # First match: DG buy → TR sell
        assert lots[0].buy_broker == Broker.DEGIRO.value
        assert lots[0].sell_broker == Broker.TR.value
        assert lots[0].cost_basis_eur == Decimal("500")
        assert lots[0].realized_pl_eur == Decimal("500")

        # Second match: DG buy → DG sell (next 10 shares from same DG buy)
        assert lots[1].buy_broker == Broker.DEGIRO.value
        assert lots[1].sell_broker == Broker.DEGIRO.value
        assert lots[1].cost_basis_eur == Decimal("500")
        assert lots[1].realized_pl_eur == Decimal("400")


class TestHoldingPeriod:
    """Verify holding period and casilla assignment."""

    def test_less_than_one_year(self, db):
        dg_acct = _make_account(db, Broker.DEGIRO.value)
        tr_acct = _make_account(db, Broker.TR.value)

        _make_buy(db, dg_acct, "US12345", date(2024, 1, 15), Decimal("5"), Decimal("100"))
        _make_buy(db, tr_acct, "US12345", date(2024, 3, 15), Decimal("5"), Decimal("110"))
        _make_sell(db, tr_acct, "US12345", date(2024, 6, 15), Decimal("5"), Decimal("120"))

        # Broker TaxLot (synthetic)
        _make_broker_lot(db, tr_acct, "US12345", date(2024, 3, 15), date(2024, 6, 15),
                         Decimal("5"), Decimal("550"), Decimal("600"))

        recalculate_cross_broker_fifo(db, 2024)
        lot = db.query(CrossBrokerLot).first()
        assert lot.holding_period == "<1y"
        assert lot.casilla == 332  # gain

    def test_more_than_one_year(self, db):
        dg_acct = _make_account(db, Broker.DEGIRO.value)
        tr_acct = _make_account(db, Broker.TR.value)

        _make_buy(db, dg_acct, "US12345", date(2022, 1, 1), Decimal("5"), Decimal("100"))
        _make_buy(db, tr_acct, "US12345", date(2023, 6, 1), Decimal("5"), Decimal("110"))
        _make_sell(db, tr_acct, "US12345", date(2024, 6, 1), Decimal("5"), Decimal("120"))

        _make_broker_lot(db, tr_acct, "US12345", date(2023, 6, 1), date(2024, 6, 1),
                         Decimal("5"), Decimal("550"), Decimal("600"))

        recalculate_cross_broker_fifo(db, 2024)
        lot = db.query(CrossBrokerLot).first()
        assert lot.holding_period == ">=1y"

    def test_loss_goes_to_casilla_337(self, db):
        dg_acct = _make_account(db, Broker.DEGIRO.value)
        tr_acct = _make_account(db, Broker.TR.value)

        _make_buy(db, dg_acct, "US12345", date(2023, 1, 1), Decimal("5"), Decimal("150"))
        _make_buy(db, tr_acct, "US12345", date(2023, 6, 1), Decimal("5"), Decimal("110"))
        _make_sell(db, tr_acct, "US12345", date(2024, 6, 1), Decimal("5"), Decimal("100"))

        _make_broker_lot(db, tr_acct, "US12345", date(2023, 6, 1), date(2024, 6, 1),
                         Decimal("5"), Decimal("550"), Decimal("500"))

        recalculate_cross_broker_fifo(db, 2024)
        lot = db.query(CrossBrokerLot).first()
        assert lot.casilla == 337  # loss


class TestCleanRecalculation:
    """Verify that recalculation clears old data before creating new."""

    def test_recalculate_clears_previous(self, db):
        dg_acct = _make_account(db, Broker.DEGIRO.value)
        tr_acct = _make_account(db, Broker.TR.value)

        _make_buy(db, dg_acct, "US12345", date(2023, 1, 1), Decimal("10"), Decimal("50"))
        _make_buy(db, tr_acct, "US12345", date(2023, 6, 1), Decimal("10"), Decimal("70"))
        _make_sell(db, tr_acct, "US12345", date(2024, 3, 1), Decimal("10"), Decimal("80"))

        _make_broker_lot(db, tr_acct, "US12345", date(2023, 6, 1), date(2024, 3, 1),
                         Decimal("10"), Decimal("700"), Decimal("800"))

        # First run
        recalculate_cross_broker_fifo(db, 2024)
        assert db.query(CrossBrokerLot).count() == 1

        # Second run should clean and recreate
        recalculate_cross_broker_fifo(db, 2024)
        assert db.query(CrossBrokerLot).count() == 1  # not 2


class TestNoSells:
    """Year with no sells should produce nothing."""

    def test_no_sells_no_lots(self, db):
        dg_acct = _make_account(db, Broker.DEGIRO.value)
        tr_acct = _make_account(db, Broker.TR.value)

        _make_buy(db, dg_acct, "US12345", date(2023, 1, 1), Decimal("10"), Decimal("50"))
        _make_buy(db, tr_acct, "US12345", date(2023, 6, 1), Decimal("10"), Decimal("60"))

        result = recalculate_cross_broker_fifo(db, 2024)
        assert result["lots_created"] == 0
        assert result["adjustments"] == 0
