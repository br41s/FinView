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
    DataIssue,
    FIFOAdjustment,
    TaxLot,
    Transaction,
    TransactionType,
    User,
)
from backend.api.fiscal import list_cross_broker_lots
from backend.services.fifo_engine import (
    recalculate_cross_broker_fifo,
    recalculate_fifo_from_year,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def user_id(db) -> int:
    user = User(email="test@example.com", name="Test", password_hash="x")
    db.add(user)
    db.flush()
    return user.id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_account(db, broker: str, user_id: int) -> Account:
    acct = Account(
        broker=broker,
        account_id=f"test-{broker}",
        name=f"Test {broker}",
        user_id=user_id,
    )
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


def _make_spinoff(
    db,
    acct: Account,
    isin: str,
    trade_date: date,
    qty: Decimal,
    import_id: int = 1,
) -> Transaction:
    tx = Transaction(
        account_id=acct.id,
        import_id=import_id,
        type=TransactionType.SPINOFF.value,
        trade_date=trade_date,
        isin=isin,
        name="SpinCo",
        quantity=qty,
        price=Decimal("0"),
        gross_amount=Decimal("0"),
        fees=Decimal("0"),
        net_amount_eur=Decimal("0"),
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

    def test_single_broker_no_lots(self, db, user_id):
        acct = _make_account(db, Broker.TR.value, user_id)
        _make_buy(db, acct, "US0378331005", date(2023, 3, 1), Decimal("10"), Decimal("150"))
        _make_sell(db, acct, "US0378331005", date(2024, 6, 1), Decimal("10"), Decimal("180"))
        _make_broker_lot(db, acct, "US0378331005", date(2023, 3, 1), date(2024, 6, 1),
                         Decimal("10"), Decimal("1500"), Decimal("1800"))

        result = recalculate_cross_broker_fifo(db, 2024, user_id=user_id)

        assert result["lots_created"] == 0
        assert result["adjustments"] == 0
        assert db.query(CrossBrokerLot).count() == 0
        assert db.query(FIFOAdjustment).count() == 0


class TestMultiBrokerSameFIFO:
    """When cross-broker FIFO matches broker reports, adjustment = 0."""

    def test_two_brokers_same_result(self, db, user_id):
        """Buy at TR (oldest), sell at TR → FIFO picks TR buy → same as broker."""
        tr_acct = _make_account(db, Broker.TR.value, user_id)
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)

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

        result = recalculate_cross_broker_fifo(db, 2024, user_id=user_id)

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

    def test_older_buy_at_different_broker(self, db, user_id):
        """Buy at DG (cheaper, older), sell at TR → broker says one thing, FIFO says another."""
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        tr_acct = _make_account(db, Broker.TR.value, user_id)

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

        result = recalculate_cross_broker_fifo(db, 2024, user_id=user_id)

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

    def test_partial_consumption(self, db, user_id):
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        tr_acct = _make_account(db, Broker.TR.value, user_id)

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

        result = recalculate_cross_broker_fifo(db, 2024, user_id=user_id)

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


class TestChronologicalLedger:
    """Historical sells consume inventory; future buys never fund earlier sells."""

    def test_prior_year_sell_consumes_oldest_buy(self, db, user_id):
        tr_acct = _make_account(db, Broker.TR.value, user_id)
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        isin = "US0000000101"

        old_buy = _make_buy(
            db, tr_acct, isin, date(2023, 1, 1), Decimal("10"), Decimal("10")
        )
        _make_sell(
            db, tr_acct, isin, date(2024, 1, 1), Decimal("10"), Decimal("20")
        )
        target_buy = _make_buy(
            db, dg_acct, isin, date(2025, 1, 1), Decimal("10"), Decimal("30")
        )
        _make_sell(
            db, dg_acct, isin, date(2025, 6, 1), Decimal("10"), Decimal("40")
        )
        _make_broker_lot(
            db,
            dg_acct,
            isin,
            date(2025, 1, 1),
            date(2025, 6, 1),
            Decimal("10"),
            Decimal("300"),
            Decimal("400"),
        )

        result = recalculate_cross_broker_fifo(db, 2025, user_id=user_id)

        assert result == {"lots_created": 1, "adjustments": 0, "isins_analyzed": 1}
        lot = db.query(CrossBrokerLot).one()
        assert lot.buy_tx_id == target_buy.id
        assert lot.buy_tx_id != old_buy.id
        assert lot.cost_basis_eur == Decimal("300")
        assert lot.realized_pl_eur == Decimal("100")

    def test_future_buy_does_not_fund_earlier_sell(self, db, user_id):
        tr_acct = _make_account(db, Broker.TR.value, user_id)
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        isin = "US0000000102"

        valid_buy = _make_buy(
            db, tr_acct, isin, date(2024, 1, 1), Decimal("5"), Decimal("10")
        )
        _make_sell(
            db, tr_acct, isin, date(2025, 1, 1), Decimal("10"), Decimal("30")
        )
        future_buy = _make_buy(
            db, dg_acct, isin, date(2025, 6, 1), Decimal("5"), Decimal("20")
        )

        result = recalculate_cross_broker_fifo(db, 2025, user_id=user_id)

        assert result["lots_created"] == 0
        assert db.query(CrossBrokerLot).count() == 0
        assert db.query(FIFOAdjustment).count() == 0

        # The future purchase remains real input but is never published as a
        # match for the earlier sale.
        assert valid_buy.id != future_buy.id

    def test_equal_net_still_adjusts_gain_and_loss_boxes(self, db, user_id):
        tr_acct = _make_account(db, Broker.TR.value, user_id)
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        isin = "US0000000103"

        _make_buy(db, tr_acct, isin, date(2023, 1, 1), Decimal("1"), Decimal("100"))
        _make_buy(db, dg_acct, isin, date(2023, 2, 1), Decimal("1"), Decimal("200"))
        _make_sell(db, dg_acct, isin, date(2024, 1, 1), Decimal("1"), Decimal("150"))
        _make_sell(db, tr_acct, isin, date(2024, 2, 1), Decimal("1"), Decimal("150"))

        # Broker boxes: +100 / -100 = 0. Cross-broker FIFO boxes: +50 / -50 = 0.
        _make_broker_lot(
            db, dg_acct, isin, date(2023, 2, 1), date(2024, 1, 1),
            Decimal("1"), Decimal("50"), Decimal("150"),
        )
        _make_broker_lot(
            db, tr_acct, isin, date(2023, 1, 1), date(2024, 2, 1),
            Decimal("1"), Decimal("250"), Decimal("150"),
        )

        result = recalculate_cross_broker_fifo(db, 2024, user_id=user_id)

        assert result["lots_created"] == 2
        assert result["adjustments"] == 1
        adjustment = db.query(FIFOAdjustment).one()
        assert adjustment.adjustment_eur == Decimal("0")
        assert adjustment.broker_gains_eur == Decimal("100")
        assert adjustment.broker_losses_eur == Decimal("-100")
        assert adjustment.fifo_gains_eur == Decimal("50")
        assert adjustment.fifo_losses_eur == Decimal("-50")
        assert adjustment.calculation_version == "2"


class TestMissingInstrumentIdentity:
    def test_empty_isin_is_not_cross_broker_matched(self, db, user_id):
        tr_acct = _make_account(db, Broker.TR.value, user_id)
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)

        alphabet = _make_buy(
            db, tr_acct, "", date(2023, 1, 1), Decimal("10"), Decimal("100")
        )
        alphabet.name = "Alphabet"
        tesla = _make_buy(
            db, dg_acct, "", date(2023, 6, 1), Decimal("10"), Decimal("200")
        )
        tesla.name = "Tesla"
        tesla_sell = _make_sell(
            db, dg_acct, "", date(2024, 1, 1), Decimal("10"), Decimal("300")
        )
        tesla_sell.name = "Tesla"

        result = recalculate_cross_broker_fifo(db, 2024, user_id=user_id)

        assert result == {"lots_created": 0, "adjustments": 0, "isins_analyzed": 0}
        assert db.query(CrossBrokerLot).count() == 0
        assert db.query(FIFOAdjustment).count() == 0


class TestHoldingPeriod:
    """Verify holding period and casilla assignment."""

    def test_less_than_one_year(self, db, user_id):
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        tr_acct = _make_account(db, Broker.TR.value, user_id)

        _make_buy(db, dg_acct, "US12345", date(2024, 1, 15), Decimal("5"), Decimal("100"))
        _make_buy(db, tr_acct, "US12345", date(2024, 3, 15), Decimal("5"), Decimal("110"))
        _make_sell(db, tr_acct, "US12345", date(2024, 6, 15), Decimal("5"), Decimal("120"))

        # Broker TaxLot (synthetic)
        _make_broker_lot(db, tr_acct, "US12345", date(2024, 3, 15), date(2024, 6, 15),
                         Decimal("5"), Decimal("550"), Decimal("600"))

        recalculate_cross_broker_fifo(db, 2024, user_id=user_id)
        lot = db.query(CrossBrokerLot).first()
        assert lot.holding_period == "<1y"
        assert lot.casilla == 332  # gain

    def test_more_than_one_year(self, db, user_id):
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        tr_acct = _make_account(db, Broker.TR.value, user_id)

        _make_buy(db, dg_acct, "US12345", date(2022, 1, 1), Decimal("5"), Decimal("100"))
        _make_buy(db, tr_acct, "US12345", date(2023, 6, 1), Decimal("5"), Decimal("110"))
        _make_sell(db, tr_acct, "US12345", date(2024, 6, 1), Decimal("5"), Decimal("120"))

        _make_broker_lot(db, tr_acct, "US12345", date(2023, 6, 1), date(2024, 6, 1),
                         Decimal("5"), Decimal("550"), Decimal("600"))

        recalculate_cross_broker_fifo(db, 2024, user_id=user_id)
        lot = db.query(CrossBrokerLot).first()
        assert lot.holding_period == ">=1y"

    def test_loss_goes_to_casilla_337(self, db, user_id):
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        tr_acct = _make_account(db, Broker.TR.value, user_id)

        _make_buy(db, dg_acct, "US12345", date(2023, 1, 1), Decimal("5"), Decimal("150"))
        _make_buy(db, tr_acct, "US12345", date(2023, 6, 1), Decimal("5"), Decimal("110"))
        _make_sell(db, tr_acct, "US12345", date(2024, 6, 1), Decimal("5"), Decimal("100"))

        _make_broker_lot(db, tr_acct, "US12345", date(2023, 6, 1), date(2024, 6, 1),
                         Decimal("5"), Decimal("550"), Decimal("500"))

        recalculate_cross_broker_fifo(db, 2024, user_id=user_id)
        lot = db.query(CrossBrokerLot).first()
        assert lot.casilla == 337  # loss


class TestCleanRecalculation:
    """Verify that recalculation clears old data before creating new."""

    def test_recalculate_clears_previous(self, db, user_id):
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        tr_acct = _make_account(db, Broker.TR.value, user_id)

        _make_buy(db, dg_acct, "US12345", date(2023, 1, 1), Decimal("10"), Decimal("50"))
        _make_buy(db, tr_acct, "US12345", date(2023, 6, 1), Decimal("10"), Decimal("70"))
        _make_sell(db, tr_acct, "US12345", date(2024, 3, 1), Decimal("10"), Decimal("80"))

        _make_broker_lot(db, tr_acct, "US12345", date(2023, 6, 1), date(2024, 3, 1),
                         Decimal("10"), Decimal("700"), Decimal("800"))

        # First run
        recalculate_cross_broker_fifo(db, 2024, user_id=user_id)
        assert db.query(CrossBrokerLot).count() == 1

        # Second run should clean and recreate
        recalculate_cross_broker_fifo(db, 2024, user_id=user_id)
        assert db.query(CrossBrokerLot).count() == 1  # not 2


class TestNoSells:
    """Year with no sells should produce nothing."""

    def test_no_sells_no_lots(self, db, user_id):
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        tr_acct = _make_account(db, Broker.TR.value, user_id)

        _make_buy(db, dg_acct, "US12345", date(2023, 1, 1), Decimal("10"), Decimal("50"))
        _make_buy(db, tr_acct, "US12345", date(2023, 6, 1), Decimal("10"), Decimal("60"))

        result = recalculate_cross_broker_fifo(db, 2024, user_id=user_id)
        assert result["lots_created"] == 0
        assert result["adjustments"] == 0


class TestUserIsolation:
    """FIFO calculations and cleanup must stay within one user's accounts."""

    def test_accounts_from_different_users_do_not_form_a_multi_broker_position(
        self, db, user_id
    ):
        other_user = User(email="other@example.com", name="Other", password_hash="x")
        db.add(other_user)
        db.flush()

        user_account = _make_account(db, Broker.TR.value, user_id)
        other_account = _make_account(db, Broker.DEGIRO.value, other_user.id)
        isin = "US0000000001"

        _make_buy(
            db, user_account, isin, date(2023, 1, 1), Decimal("10"), Decimal("100")
        )
        _make_sell(
            db, user_account, isin, date(2024, 1, 1), Decimal("10"), Decimal("120")
        )
        _make_broker_lot(
            db,
            user_account,
            isin,
            date(2023, 1, 1),
            date(2024, 1, 1),
            Decimal("10"),
            Decimal("1000"),
            Decimal("1200"),
        )
        _make_buy(
            db, other_account, isin, date(2022, 1, 1), Decimal("10"), Decimal("50")
        )

        result = recalculate_cross_broker_fifo(db, 2024, user_id=user_id)

        assert result == {"lots_created": 0, "adjustments": 0, "isins_analyzed": 0}
        assert db.query(CrossBrokerLot).count() == 0
        assert db.query(FIFOAdjustment).count() == 0

    def test_cleanup_removes_historical_mixed_user_lot_for_the_seller(
        self, db, user_id
    ):
        other_user = User(email="other@example.com", name="Other", password_hash="x")
        db.add(other_user)
        db.flush()

        user_account = _make_account(db, Broker.TR.value, user_id)
        other_account = _make_account(db, Broker.DEGIRO.value, other_user.id)
        isin = "US0000000003"
        other_buy = _make_buy(
            db, other_account, isin, date(2023, 1, 1), Decimal("10"), Decimal("50")
        )
        user_sell = _make_sell(
            db, user_account, isin, date(2024, 1, 1), Decimal("10"), Decimal("80")
        )
        db.add(
            CrossBrokerLot(
                fiscal_year=2024,
                isin=isin,
                name="Historical mixed row",
                buy_tx_id=other_buy.id,
                sell_tx_id=user_sell.id,
                buy_broker=Broker.DEGIRO.value,
                sell_broker=Broker.TR.value,
                quantity=Decimal("10"),
                cost_basis_eur=Decimal("500"),
                proceeds_eur=Decimal("800"),
                realized_pl_eur=Decimal("300"),
                holding_period=">=1y",
                casilla=332,
            )
        )
        db.flush()

        result = recalculate_cross_broker_fifo(db, 2024, user_id=user_id)

        assert result == {"lots_created": 0, "adjustments": 0, "isins_analyzed": 0}
        assert db.query(CrossBrokerLot).count() == 0

    def test_api_hides_historical_lot_with_different_buy_and_sell_owners(
        self, db, user_id
    ):
        user = db.get(User, user_id)
        other_user = User(email="other@example.com", name="Other", password_hash="x")
        db.add(other_user)
        db.flush()

        user_account = _make_account(db, Broker.TR.value, user_id)
        other_account = _make_account(db, Broker.DEGIRO.value, other_user.id)
        isin = "US0000000004"
        user_buy = _make_buy(
            db, user_account, isin, date(2023, 1, 1), Decimal("10"), Decimal("50")
        )
        other_sell = _make_sell(
            db, other_account, isin, date(2024, 1, 1), Decimal("10"), Decimal("80")
        )
        own_sell = _make_sell(
            db, user_account, isin, date(2024, 2, 1), Decimal("10"), Decimal("90")
        )
        mixed_lot = CrossBrokerLot(
            fiscal_year=2024,
            isin=isin,
            name="Historical mixed row",
            buy_tx_id=user_buy.id,
            sell_tx_id=other_sell.id,
            buy_broker=Broker.TR.value,
            sell_broker=Broker.DEGIRO.value,
            quantity=Decimal("10"),
            cost_basis_eur=Decimal("500"),
            proceeds_eur=Decimal("800"),
            realized_pl_eur=Decimal("300"),
            holding_period=">=1y",
            casilla=332,
            calculation_version="2",
        )
        owned_lot = CrossBrokerLot(
            fiscal_year=2024,
            isin=isin,
            name="Owned row",
            buy_tx_id=user_buy.id,
            sell_tx_id=own_sell.id,
            buy_broker=Broker.TR.value,
            sell_broker=Broker.TR.value,
            quantity=Decimal("10"),
            cost_basis_eur=Decimal("500"),
            proceeds_eur=Decimal("900"),
            realized_pl_eur=Decimal("400"),
            holding_period=">=1y",
            casilla=332,
            calculation_version="2",
        )
        db.add_all([mixed_lot, owned_lot])
        db.flush()

        assert list_cross_broker_lots(db, user, 2024) == [owned_lot]

    def test_recalculation_preserves_and_separates_other_user_results(
        self, db, user_id
    ):
        other_user = User(email="other@example.com", name="Other", password_hash="x")
        db.add(other_user)
        db.flush()

        user_dg = _make_account(db, Broker.DEGIRO.value, user_id)
        user_tr = _make_account(db, Broker.TR.value, user_id)
        other_dg = _make_account(db, Broker.DEGIRO.value, other_user.id)
        other_tr = _make_account(db, Broker.TR.value, other_user.id)
        isin = "US0000000002"

        _make_buy(db, user_dg, isin, date(2023, 1, 1), Decimal("10"), Decimal("50"))
        _make_buy(db, user_tr, isin, date(2023, 6, 1), Decimal("10"), Decimal("70"))
        _make_sell(db, user_tr, isin, date(2024, 3, 1), Decimal("10"), Decimal("80"))
        _make_broker_lot(
            db,
            user_tr,
            isin,
            date(2023, 6, 1),
            date(2024, 3, 1),
            Decimal("10"),
            Decimal("700"),
            Decimal("800"),
        )

        _make_buy(
            db, other_dg, isin, date(2023, 2, 1), Decimal("10"), Decimal("200")
        )
        _make_buy(
            db, other_tr, isin, date(2023, 7, 1), Decimal("10"), Decimal("230")
        )
        _make_sell(
            db, other_tr, isin, date(2024, 4, 1), Decimal("10"), Decimal("250")
        )
        _make_broker_lot(
            db,
            other_tr,
            isin,
            date(2023, 7, 1),
            date(2024, 4, 1),
            Decimal("10"),
            Decimal("2300"),
            Decimal("2500"),
        )

        other_result = recalculate_cross_broker_fifo(db, 2024, user_id=other_user.id)
        assert other_result == {"lots_created": 1, "adjustments": 1, "isins_analyzed": 1}
        other_lot = db.query(CrossBrokerLot).one()
        other_adjustment = db.query(FIFOAdjustment).one()
        assert other_lot.realized_pl_eur == Decimal("500")
        assert other_adjustment.adjustment_eur == Decimal("300")
        other_lot_id = other_lot.id
        other_adjustment_id = other_adjustment.id

        user_result = recalculate_cross_broker_fifo(db, 2024, user_id=user_id)

        assert user_result == {"lots_created": 1, "adjustments": 1, "isins_analyzed": 1}
        assert db.get(CrossBrokerLot, other_lot_id) is not None
        assert db.get(FIFOAdjustment, other_adjustment_id) is not None

        lots_with_owner = (
            db.query(CrossBrokerLot, Account.user_id)
            .join(Transaction, CrossBrokerLot.buy_tx_id == Transaction.id)
            .join(Account, Transaction.account_id == Account.id)
            .all()
        )
        lots_by_user = {owner_id: lot for lot, owner_id in lots_with_owner}
        assert set(lots_by_user) == {user_id, other_user.id}
        assert lots_by_user[user_id].realized_pl_eur == Decimal("300")
        assert lots_by_user[other_user.id].realized_pl_eur == Decimal("500")

        adjustments = {adj.user_id: adj for adj in db.query(FIFOAdjustment).all()}
        assert set(adjustments) == {user_id, other_user.id}
        assert adjustments[user_id].broker_pl_eur == Decimal("100")
        assert adjustments[user_id].adjustment_eur == Decimal("200")
        assert adjustments[other_user.id].broker_pl_eur == Decimal("200")
        assert adjustments[other_user.id].adjustment_eur == Decimal("300")

        recalculate_cross_broker_fifo(db, 2024, user_id=user_id)
        assert db.get(CrossBrokerLot, other_lot_id) is not None
        assert db.get(FIFOAdjustment, other_adjustment_id) is not None
        assert db.query(CrossBrokerLot).count() == 2
        assert db.query(FIFOAdjustment).count() == 2


class TestDownstreamInvalidation:
    def test_historical_buy_recalculates_later_sale_year(self, db, user_id):
        tr_acct = _make_account(db, Broker.TR.value, user_id)
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        isin = "US0000000201"

        old_buy = _make_buy(
            db, tr_acct, isin, date(2023, 1, 1), Decimal("10"), Decimal("50")
        )
        _make_buy(
            db, dg_acct, isin, date(2023, 6, 1), Decimal("10"), Decimal("70")
        )
        _make_sell(
            db, dg_acct, isin, date(2025, 6, 1), Decimal("10"), Decimal("80")
        )
        _make_broker_lot(
            db, dg_acct, isin, date(2023, 6, 1), date(2025, 6, 1),
            Decimal("10"), Decimal("700"), Decimal("800"),
        )

        recalculate_cross_broker_fifo(db, 2025, user_id)
        assert db.query(FIFOAdjustment).one().adjustment_eur == Decimal("200")

        old_buy.price = Decimal("60")
        old_buy.gross_amount = Decimal("600")
        old_buy.net_amount_eur = Decimal("600")
        recalculate_fifo_from_year(db, 2023, user_id)

        assert db.query(FIFOAdjustment).one().adjustment_eur == Decimal("100")

    def test_start_year_is_cleared_after_last_sale_disappears(self, db, user_id):
        tr_acct = _make_account(db, Broker.TR.value, user_id)
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        isin = "US0000000202"
        _make_buy(db, tr_acct, isin, date(2023, 1, 1), Decimal("1"), Decimal("1"))
        _make_buy(db, dg_acct, isin, date(2023, 2, 1), Decimal("1"), Decimal("2"))
        sell = _make_sell(
            db, dg_acct, isin, date(2025, 1, 1), Decimal("1"), Decimal("3")
        )
        _make_broker_lot(
            db, dg_acct, isin, date(2023, 2, 1), date(2025, 1, 1),
            Decimal("1"), Decimal("2"), Decimal("3"),
        )
        recalculate_cross_broker_fifo(db, 2025, user_id)
        assert db.query(FIFOAdjustment).count() == 1

        db.query(CrossBrokerLot).filter(CrossBrokerLot.sell_tx_id == sell.id).delete()
        db.delete(sell)
        db.flush()
        recalculate_fifo_from_year(db, 2025, user_id)

        assert db.query(CrossBrokerLot).count() == 0
        assert db.query(FIFOAdjustment).count() == 0


class TestUnknownCostBasis:
    def test_fee_only_spinoff_remains_unknown_cost(self, db, user_id):
        tr_acct = _make_account(db, Broker.TR.value, user_id)
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        isin = "US0000000300"
        _make_buy(db, tr_acct, isin, date(2023, 1, 1), Decimal("5"), Decimal("10"))
        spinoff = _make_spinoff(
            db, dg_acct, isin, date(2023, 2, 1), Decimal("5")
        )
        spinoff.fees = Decimal("5")
        spinoff.net_amount_eur = Decimal("5")
        _make_sell(db, tr_acct, isin, date(2024, 1, 1), Decimal("10"), Decimal("30"))

        result = recalculate_cross_broker_fifo(db, 2024, user_id)

        assert result["lots_created"] == 0
        assert db.query(CrossBrokerLot).count() == 0
        assert db.query(DataIssue).one().issue_type == "fifo_missing_cost_basis"

    def test_sale_before_spinoff_keeps_authoritative_fifo(self, db, user_id):
        tr_acct = _make_account(db, Broker.TR.value, user_id)
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        isin = "US0000000301"
        _make_buy(db, tr_acct, isin, date(2023, 1, 1), Decimal("5"), Decimal("10"))
        _make_buy(db, dg_acct, isin, date(2023, 2, 1), Decimal("5"), Decimal("20"))
        _make_sell(db, tr_acct, isin, date(2024, 1, 1), Decimal("5"), Decimal("30"))
        _make_spinoff(db, dg_acct, isin, date(2024, 6, 1), Decimal("5"))
        _make_broker_lot(
            db, tr_acct, isin, date(2023, 1, 1), date(2024, 1, 1),
            Decimal("5"), Decimal("50"), Decimal("150"),
        )

        result = recalculate_cross_broker_fifo(db, 2024, user_id)

        assert result["lots_created"] == 1
        assert db.query(DataIssue).count() == 0

    def test_sale_reaching_spinoff_fails_closed_and_creates_issue(self, db, user_id):
        tr_acct = _make_account(db, Broker.TR.value, user_id)
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        isin = "US0000000302"
        _make_buy(db, tr_acct, isin, date(2023, 1, 1), Decimal("5"), Decimal("10"))
        spinoff = _make_spinoff(
            db, dg_acct, isin, date(2023, 2, 1), Decimal("5")
        )
        _make_sell(db, tr_acct, isin, date(2024, 1, 1), Decimal("10"), Decimal("30"))

        result = recalculate_cross_broker_fifo(db, 2024, user_id)

        assert result["lots_created"] == 0
        assert db.query(CrossBrokerLot).count() == 0
        issue = db.query(DataIssue).one()
        assert issue.issue_type == "fifo_missing_cost_basis"
        assert issue.status == "needs_input"
        assert '"fiscal_year": 2024' in issue.resolution_data

        spinoff.price = Decimal("10")
        spinoff.gross_amount = Decimal("50")
        spinoff.net_amount_eur = Decimal("50")
        recalculate_cross_broker_fifo(db, 2024, user_id)
        db.refresh(issue)
        assert issue.status == "resolved"
        assert db.query(CrossBrokerLot).count() == 2

        spinoff.price = Decimal("0")
        spinoff.gross_amount = Decimal("0")
        spinoff.net_amount_eur = Decimal("0")
        recalculate_cross_broker_fifo(db, 2024, user_id)
        db.refresh(issue)
        assert issue.status == "needs_input"
        assert db.query(CrossBrokerLot).count() == 0

    def test_historical_unknown_consumption_does_not_block_later_known_sale(
        self, db, user_id
    ):
        tr_acct = _make_account(db, Broker.TR.value, user_id)
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        isin = "US0000000303"
        _make_buy(db, tr_acct, isin, date(2023, 1, 1), Decimal("5"), Decimal("10"))
        _make_spinoff(db, dg_acct, isin, date(2023, 2, 1), Decimal("5"))
        _make_sell(db, dg_acct, isin, date(2024, 1, 1), Decimal("10"), Decimal("20"))
        known_buy = _make_buy(
            db, tr_acct, isin, date(2025, 1, 1), Decimal("5"), Decimal("30")
        )
        _make_sell(db, dg_acct, isin, date(2025, 6, 1), Decimal("5"), Decimal("40"))

        result = recalculate_cross_broker_fifo(db, 2025, user_id)

        assert result["lots_created"] == 1
        assert db.query(CrossBrokerLot).one().buy_tx_id == known_buy.id
        assert db.query(DataIssue).count() == 0


class TestFiscalRounding:
    @pytest.mark.parametrize(
        ("sell_price", "expected_adjustment"),
        [
            (Decimal("1.004"), None),
            (Decimal("1.005"), Decimal("0.01")),
            (Decimal("0.995"), Decimal("-0.01")),
        ],
    )
    def test_half_up_cent_boundary(self, db, user_id, sell_price, expected_adjustment):
        tr_acct = _make_account(db, Broker.TR.value, user_id)
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        isin = "US0000000401"
        _make_buy(db, tr_acct, isin, date(2023, 1, 1), Decimal("1"), Decimal("1"))
        _make_buy(db, dg_acct, isin, date(2023, 2, 1), Decimal("1"), Decimal("2"))
        _make_sell(db, dg_acct, isin, date(2024, 1, 1), Decimal("1"), sell_price)
        _make_broker_lot(
            db, dg_acct, isin, date(2023, 2, 1), date(2024, 1, 1),
            Decimal("1"), sell_price, sell_price,
        )

        recalculate_cross_broker_fifo(db, 2024, user_id)

        adjustment = db.query(FIFOAdjustment).one_or_none()
        if expected_adjustment is None:
            assert adjustment is None
        else:
            assert adjustment.adjustment_eur == expected_adjustment

    def test_fractional_lots_round_after_box_aggregation(self, db, user_id):
        tr_acct = _make_account(db, Broker.TR.value, user_id)
        dg_acct = _make_account(db, Broker.DEGIRO.value, user_id)
        isin = "US0000000402"
        _make_buy(db, tr_acct, isin, date(2023, 1, 1), Decimal("1"), Decimal("1"))
        _make_buy(db, dg_acct, isin, date(2023, 1, 2), Decimal("1"), Decimal("1"))
        _make_sell(db, dg_acct, isin, date(2024, 1, 1), Decimal("2"), Decimal("1.003"))
        _make_broker_lot(
            db, dg_acct, isin, date(2023, 1, 2), date(2024, 1, 1),
            Decimal("2"), Decimal("2.006"), Decimal("2.006"),
        )

        recalculate_cross_broker_fifo(db, 2024, user_id)

        adjustment = db.query(FIFOAdjustment).one()
        assert adjustment.fifo_gains_eur == Decimal("0.01")
        assert adjustment.adjustment_eur == Decimal("0.01")
