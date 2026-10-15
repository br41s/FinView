"""IBKR sync: one year per step, a resumable run, full history, and the API.

IBKR is a fake behind httpx.MockTransport that serves one statement per
calendar year, so a run goes through the real parser and the real
`import_ibkr_report` (FIFO included) against an in-memory database.
"""

from datetime import date

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.brokers import router as brokers_router
from backend.config import settings
from backend.database import get_db
from backend.models import Base, BrokerConnection, ImportRecord, User
from backend.services import billing_service, broker_sync, data_supervisor, split_history
from backend.services import user_data
from backend.services.auth_service import create_access_token
from backend.tests.test_ibkr_flex import TOKEN, envelope, flex_xml

TODAY = date(2026, 10, 15)


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr(data_supervisor, "_try_resolve_ticker", lambda _isin: None)
    monkeypatch.setattr(split_history, "_fetch", lambda _ticker: [])
    monkeypatch.setattr(settings, "credentials_key", Fernet.generate_key().decode())


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def user(db) -> User:
    u = User(email="u@example.com", name="U", password_hash="x")
    db.add(u)
    db.commit()
    return u


def year_statement(year: int, **kwargs) -> str:
    """A small statement for one year: one EUR buy, so every year imports something."""
    trades = f"""<Trades>
  <Trade levelOfDetail="EXECUTION" assetCategory="STK" symbol="SAN" isin="ES0113900J37"
    currency="EUR" fxRateToBase="1" tradeDate="{year}0610" quantity="10" tradePrice="4"
    proceeds="-40" ibCommission="-1" />
</Trades>"""
    sections = {"Trades": trades, "FIFOPerformanceSummaryInBase": "<FIFOPerformanceSummaryInBase/>",
                "CashTransactions": "<CashTransactions/>", "OpenPositions": "<OpenPositions/>"}
    sections.update(kwargs.pop("sections", {}))
    return flex_xml(from_date=f"{year}0101", to_date=f"{year}1231", sections=sections, **kwargs)


class FakeIBKR:
    """SendRequest → ref-<year>; GetStatement(ref-<year>) → that year's statement."""

    def __init__(self, statement=year_statement):
        self.statement = statement
        self.sent: list[tuple[str, str]] = []
        self.fetched: list[str] = []
        self.send_error: dict[int, str] = {}
        self.fetch_error: dict[int, str] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if request.url.path.endswith("/SendRequest"):
            year = int(params["fd"][:4])
            self.sent.append((params["fd"], params["td"]))
            if year in self.send_error:
                return httpx.Response(200, text=envelope("Fail", self.send_error[year]))
            return httpx.Response(200, text=envelope(reference=f"ref-{year}"))
        year = int(params["q"].removeprefix("ref-"))
        self.fetched.append(params["q"])
        if year in self.fetch_error:
            return httpx.Response(200, text=envelope("Warn", self.fetch_error[year]))
        return httpx.Response(200, text=self.statement(year))

    @property
    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


def step(db, user, ibkr, today=TODAY):
    return broker_sync.sync_step(db, user, today=today, client=ibkr.client, sleep=lambda _s: None)


def run_to_end(db, user, ibkr, today=TODAY, limit=30) -> list[dict]:
    steps = []
    for _ in range(limit):
        steps.append(step(db, user, ibkr, today))
        if steps[-1]["state"] != "running":
            return steps
    raise AssertionError("sync did not finish")


def imported_years(db) -> list[int]:
    return sorted(r.fiscal_year for r in db.query(ImportRecord).all())


# ── calendar ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("today", "years"),
    [
        (date(2026, 10, 15), [2026]),
        (date(2026, 2, 10), [2025, 2026]),
        (date(2026, 3, 31), [2025, 2026]),
        (date(2026, 4, 1), [2026]),
        (date(2026, 1, 1), [2025]),  # nothing of 2026 has happened yet
    ],
)
def test_routine_years(today, years):
    assert broker_sync.routine_years(today) == years


def test_statement_period_starts_at_opening_and_ends_yesterday():
    assert broker_sync.statement_period(2026, TODAY, date(2026, 5, 4)) == (
        date(2026, 5, 4), date(2026, 10, 14)
    )
    assert broker_sync.statement_period(2024, TODAY, date(2019, 3, 12)) == (
        date(2024, 1, 1), date(2024, 12, 31)
    )


# ── runs ─────────────────────────────────────────────────────────────


def test_full_history_imports_every_year_since_opening(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=True)
    ibkr = FakeIBKR()
    steps = run_to_end(db, user, ibkr)

    assert steps[-1]["state"] == "done"
    assert imported_years(db) == list(range(2019, 2027))
    # Current year first (it reveals the opening date), then oldest to newest.
    assert [fd[:4] for fd, _ in ibkr.sent] == ["2026", *map(str, range(2019, 2026))]
    assert ibkr.sent[0] == ("20260101", "20261014")
    assert ("20190312", "20191231") in ibkr.sent  # opening year starts at the opening date
    assert steps[-1]["done"] == steps[-1]["total"] == 8

    conn = broker_sync.get_connection(db, user)
    assert conn.history_pending is False
    assert conn.account_opened_on == date(2019, 3, 12)
    assert conn.last_synced_at is not None


def test_synced_imports_do_not_spend_the_upload_allowance(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=True)
    run_to_end(db, user, FakeIBKR())
    assert len(imported_years(db)) == 8
    assert all(r.origin == broker_sync.ORIGIN for r in db.query(ImportRecord).all())
    assert billing_service.count_imports_this_month(db, user) == 0


def test_current_year_only_when_history_is_not_asked(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    run_to_end(db, user, FakeIBKR())
    assert imported_years(db) == [2026]


def test_a_routine_sync_replaces_the_year_instead_of_adding_one(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    run_to_end(db, user, FakeIBKR())
    run_to_end(db, user, FakeIBKR(lambda y: year_statement(y).replace("Test User", "Again")))
    assert imported_years(db) == [2026]


def test_a_statement_still_generating_is_collected_by_the_next_step(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    ibkr = FakeIBKR()
    ibkr.fetch_error[2026] = "1019"

    first = step(db, user, ibkr)
    assert first["state"] == "running"
    assert "generando" in first["message"]
    assert broker_sync.get_connection(db, user).pending_reference == "ref-2026"

    del ibkr.fetch_error[2026]
    second = step(db, user, ibkr)
    assert second["state"] == "done"
    assert len(ibkr.sent) == 1  # asked once, collected twice
    assert imported_years(db) == [2026]


def test_an_expired_token_stops_the_run(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=True)
    ibkr = FakeIBKR()
    ibkr.send_error[2026] = "1012"
    result = step(db, user, ibkr)

    assert result["state"] == "error"
    assert "caducado" in result["message"]
    conn = broker_sync.get_connection(db, user)
    assert conn.queue == [] and conn.pending_reference is None
    assert "caducado" in conn.last_error
    assert imported_years(db) == []


def test_a_year_ibkr_cannot_serve_is_a_gap_not_the_end(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=True)
    ibkr = FakeIBKR()
    ibkr.fetch_error[2021] = "1003"
    steps = run_to_end(db, user, ibkr)

    assert steps[-1]["state"] == "done"
    assert "2021" in steps[-1]["gaps"]
    assert imported_years(db) == [2019, 2020, 2022, 2023, 2024, 2025, 2026]


def test_a_query_problem_stops_the_run_with_the_reason(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=True)
    ibkr = FakeIBKR(lambda y: year_statement(y, sections={"OpenPositions": None}))
    result = step(db, user, ibkr)
    assert result["state"] == "error"
    assert "Open Positions" in result["message"]
    assert imported_years(db) == []


def test_missing_opening_date_is_reported_and_history_stays_pending(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=True)
    steps = run_to_end(db, user, FakeIBKR(lambda y: year_statement(y, date_opened="")))
    assert "historial" in steps[-1]["gaps"]
    assert imported_years(db) == [2026]
    assert broker_sync.get_connection(db, user).history_pending is True


def test_routine_years_before_the_account_existed_are_skipped(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    opened = lambda y: year_statement(y, date_opened='dateOpened="20260205"')  # noqa: E731
    run_to_end(db, user, FakeIBKR(opened), today=date(2026, 3, 1))  # learns the date (2025 sent)
    ibkr = FakeIBKR(opened)
    run_to_end(db, user, ibkr, today=date(2026, 3, 2))
    assert [fd for fd, _ in ibkr.sent] == ["20260205"]


def test_a_step_that_lost_its_reference_does_not_import_twice(db, user, monkeypatch):
    """Two tabs: both poll ref-2026, the second to re-lock finds it already taken."""
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    ibkr = FakeIBKR()
    real_poll = broker_sync.poll_statement

    def poll_while_another_step_wins(*args, **kwargs):
        result = real_poll(*args, **kwargs)
        conn = db.query(BrokerConnection).one()
        conn.pending_reference = None
        conn.queue = []
        db.commit()
        return result

    monkeypatch.setattr(broker_sync, "poll_statement", poll_while_another_step_wins)
    result = step(db, user, ibkr)
    assert result["state"] == "done"
    assert imported_years(db) == []


def test_a_statement_for_another_period_is_not_imported_as_the_year_asked(db, user):
    """IBKR ignoring fd/td would otherwise replace 2026 while 2021 is marked done."""
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    result = step(db, user, FakeIBKR(lambda y: year_statement(2023)))
    assert result["state"] == "error"
    assert "periodo fijo" in result["message"]
    assert imported_years(db) == []


def test_history_is_queued_even_when_the_first_year_cannot_be_parsed(db, user):
    ambiguous = """<Trades>
  <Trade levelOfDetail="EXECUTION" assetCategory="OPT" symbol="ADM P" underlyingSymbol="ADM"
    putCall="P" strike="50" multiplier="100" currency="EUR" tradeDate="20260321" quantity="1"
    tradePrice="0" proceeds="0" ibCommission="0" cost="-120" notes="A" openCloseIndicator="C" />
</Trades>"""

    def statement(year):
        return year_statement(year, sections={"Trades": ambiguous}) if year == 2026 \
            else year_statement(year)

    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=True)
    steps = run_to_end(db, user, FakeIBKR(statement))
    assert "2026" in steps[-1]["gaps"]
    assert imported_years(db) == list(range(2019, 2026))


def test_history_is_queued_even_when_the_first_import_fails(db, user, monkeypatch):
    real_import = broker_sync.import_ibkr_report

    def failing_2026(db_, report, *args, **kwargs):
        if report.fiscal_year == 2026:
            raise ValueError("fallo de importación")
        return real_import(db_, report, *args, **kwargs)

    monkeypatch.setattr(broker_sync, "import_ibkr_report", failing_2026)
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=True)
    steps = run_to_end(db, user, FakeIBKR())
    assert steps[-1]["gaps"] == {"2026": "fallo de importación"}
    assert imported_years(db) == list(range(2019, 2026))
    assert broker_sync.get_connection(db, user).history_pending is False


def test_a_run_where_nothing_arrived_is_not_a_sync(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    ibkr = FakeIBKR()
    ibkr.fetch_error[2026] = "1003"
    steps = run_to_end(db, user, ibkr)
    assert steps[-1]["state"] == "done"
    assert broker_sync.get_connection(db, user).last_synced_at is None


def test_reconnecting_forgets_the_previous_accounts_opening_date(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    run_to_end(db, user, FakeIBKR())
    assert broker_sync.get_connection(db, user).account_opened_on == date(2019, 3, 12)
    conn = broker_sync.connect(db, user, token=TOKEN, query_id="2", full_history=False)
    assert conn.account_opened_on is None
    assert conn.last_synced_at is None


def test_on_new_year_no_empty_current_year_is_requested(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=True)
    ibkr = FakeIBKR()
    run_to_end(db, user, ibkr, today=date(2026, 1, 1))
    assert all(fd <= td for fd, td in ibkr.sent)
    assert imported_years(db) == list(range(2019, 2026))


def test_a_query_delivering_csv_stops_the_run(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    result = step(db, user, FakeIBKR(lambda y: '"ClientAccountID","Symbol"\n"U1","AAPL"'))
    assert result["state"] == "error"
    assert "formato XML" in result["message"]
    assert broker_sync.get_connection(db, user).queue == []


# ── credentials and data rights ──────────────────────────────────────


def test_the_token_is_stored_encrypted(db, user):
    conn = broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    assert TOKEN not in conn.token_encrypted
    assert conn.token_hint == TOKEN[-4:]


def test_the_export_leaves_the_token_out(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    tables = {name: list(rows) for name, rows in user_data.iter_user_export(db, user)}
    (row,) = tables["broker_connections"]
    assert "token_encrypted" not in row
    assert row["token_hint"] == TOKEN[-4:]


def test_account_deletion_removes_the_connection(db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    user_data.delete_user(db, user)
    db.commit()
    assert db.query(BrokerConnection).count() == 0


# ── API ──────────────────────────────────────────────────────────────


@pytest.fixture
def api(db, user):
    app = FastAPI()
    app.include_router(brokers_router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {create_access_token(user.id, user.email)}"
    return client


def test_api_never_returns_the_token(api):
    body = {"token": TOKEN, "query_id": "987654", "full_history": True}
    response = api.put("/api/brokers/ibkr", json=body)
    assert response.status_code == 200
    assert TOKEN not in response.text
    assert response.json()["token_hint"] == TOKEN[-4:]
    assert TOKEN not in api.get("/api/brokers/ibkr").text


def test_api_stamps_the_last_sync_as_utc(api, db, user):
    """Naive and unstamped, `new Date()` in the browser would read it as local time."""
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    run_to_end(db, user, FakeIBKR())
    stamp = api.get("/api/brokers/ibkr").json()["last_synced_at"]
    assert stamp.endswith(("Z", "+00:00"))


def test_api_is_closed_without_an_encryption_key(api, monkeypatch):
    monkeypatch.setattr(settings, "credentials_key", "")
    assert api.get("/api/brokers/ibkr").json() == {"enabled": False, "connected": False,
                                                   "query_id": None, "token_hint": None,
                                                   "account_opened_on": None,
                                                   "history_pending": False,
                                                   "last_synced_at": None, "last_error": None,
                                                   "in_progress": False, "gaps": {}}
    body = {"token": TOKEN, "query_id": "1", "full_history": True}
    assert api.put("/api/brokers/ibkr", json=body).status_code == 503


def test_api_rejects_a_malformed_query_id(api):
    body = {"token": TOKEN, "query_id": "abc", "full_history": True}
    assert api.put("/api/brokers/ibkr", json=body).status_code == 422


def test_api_sync_without_connection_is_404(api):
    assert api.post("/api/brokers/ibkr/sync").status_code == 404


def test_api_sync_with_a_rotated_key_asks_to_reconnect(api, monkeypatch):
    api.put("/api/brokers/ibkr", json={"token": TOKEN, "query_id": "1", "full_history": False})
    monkeypatch.setattr(settings, "credentials_key", Fernet.generate_key().decode())
    response = api.post("/api/brokers/ibkr/sync")
    assert response.status_code == 409
    assert "Vuelve a conectar" in response.json()["detail"]


def test_api_disconnect_keeps_imported_data(api, db, user):
    broker_sync.connect(db, user, token=TOKEN, query_id="1", full_history=False)
    run_to_end(db, user, FakeIBKR())
    assert api.delete("/api/brokers/ibkr").status_code == 204
    assert db.query(BrokerConnection).count() == 0
    assert imported_years(db) == [2026]
