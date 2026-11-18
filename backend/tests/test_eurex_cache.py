"""The Eurex product cache: one day of answers, shared by every cold start.

The distinction that carries the weight here is empty-vs-failed, as in the split
cache: "Eurex does not list this symbol" is a real answer and stops the RDF
download, while a failed download must never be remembered — or one click of a
down Eurex would hide the symbol's chain for the rest of the day.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, EurexProductCache
from backend.services import eurex_cache
from backend.services import options_scraper as scraper

PRODUCT = {
    "product_isin": "DE000A1EWW08",
    "ccy": "EUR",
    "underlying_isin": "DE000BASF111",
    "sym": "BAS",
    "prev_close": 44.5,
    "options": [{
        "strike": 45.0,
        "expiration": "2026-12-18",
        "type": "CALL",
        "lastPrice": 1.2,
    }],
}


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)


def _rows(session_factory):
    with session_factory() as session:
        return session.query(EurexProductCache).all()


# ── load and store ───────────────────────────────────────────────────


def test_nothing_stored_for_the_day_is_a_miss(session_factory):
    assert eurex_cache.load("BAS", date(2026, 11, 18), session_factory) == (False, None)


def test_a_stored_product_comes_back_as_written(session_factory):
    day = date(2026, 11, 18)
    eurex_cache.store("BAS", day, PRODUCT, session_factory)

    assert eurex_cache.load("BAS", day, session_factory) == (True, PRODUCT)


def test_not_listed_is_a_real_answer_and_is_cached(session_factory):
    day = date(2026, 11, 18)
    eurex_cache.store("XXX", day, None, session_factory)

    assert eurex_cache.load("XXX", day, session_factory) == (True, None)


def test_a_row_of_another_day_is_a_miss_and_does_not_survive_a_write(session_factory):
    today = date.today()
    yesterday = today - timedelta(days=1)
    eurex_cache.store("BAS", yesterday, PRODUCT, session_factory)

    assert eurex_cache.load("BAS", today, session_factory) == (False, None)

    eurex_cache.store("BAS", today, PRODUCT, session_factory)
    rows = _rows(session_factory)
    assert [row.rdf_date for row in rows] == [today]


def test_a_second_write_wins_without_raising(session_factory):
    day = date(2026, 11, 18)
    other = {**PRODUCT, "prev_close": 46.0}
    eurex_cache.store("BAS", day, PRODUCT, session_factory)
    eurex_cache.store("BAS", day, other, session_factory)

    assert eurex_cache.load("BAS", day, session_factory) == (True, other)


def test_an_undecodable_payload_is_a_miss(session_factory):
    day = date(2026, 11, 18)
    with session_factory() as session:
        session.add(EurexProductCache(sym="BAS", rdf_date=day, product="{not json"))
        session.commit()

    assert eurex_cache.load("BAS", day, session_factory) == (False, None)


def test_a_broken_session_factory_never_raises():
    def down():
        raise RuntimeError("database is down")

    assert eurex_cache.load("BAS", date.today(), down) == (False, None)
    assert eurex_cache.store("BAS", date.today(), PRODUCT, down) is None


# ── _fetch_eurex reads and writes the cache ──────────────────────────


def test_a_cache_hit_does_not_load_the_rdf(monkeypatch):
    monkeypatch.setattr(scraper.eurex_cache, "load", lambda sym, day: (True, None))

    def must_not_load():
        raise AssertionError("a cached answer must not trigger the RDF download")

    monkeypatch.setattr(scraper, "_load_eurex_rdf", must_not_load)

    assert scraper._fetch_eurex("XXX.DE") is None


def test_a_failed_rdf_download_is_not_cached(monkeypatch):
    stored = []
    monkeypatch.setattr(scraper.eurex_cache, "load", lambda sym, day: (False, None))
    monkeypatch.setattr(scraper.eurex_cache, "store", lambda *args: stored.append(args))
    monkeypatch.setattr(scraper, "_load_eurex_rdf", lambda: False)

    assert scraper._fetch_eurex("XXX.DE") is None
    assert stored == []


def test_a_symbol_eurex_does_not_list_is_cached_as_an_answer(monkeypatch):
    day = date.today()
    stored = []
    monkeypatch.setattr(scraper.eurex_cache, "load", lambda sym, day: (False, None))
    monkeypatch.setattr(scraper.eurex_cache, "store", lambda *args: stored.append(args))
    monkeypatch.setattr(scraper, "_load_eurex_rdf", lambda: True)
    monkeypatch.setitem(scraper._EUREX_RDF_CACHE, "sym_to_code", {"OTHER": "OTHE"})
    monkeypatch.setitem(scraper._EUREX_RDF_CACHE, "products", {"OTHE": PRODUCT})

    assert scraper._fetch_eurex("XXX.DE") is None
    assert stored == [("XXX", day, None)]


def test_a_listed_symbol_is_cached_and_its_chain_returned(monkeypatch):
    day = date.today()
    stored = []
    monkeypatch.setattr(scraper.eurex_cache, "load", lambda sym, day: (False, None))
    monkeypatch.setattr(scraper.eurex_cache, "store", lambda *args: stored.append(args))
    monkeypatch.setattr(scraper, "_load_eurex_rdf", lambda: True)
    monkeypatch.setitem(scraper._EUREX_RDF_CACHE, "sym_to_code", {"BAS": "BASE"})
    monkeypatch.setitem(scraper._EUREX_RDF_CACHE, "products", {"BASE": PRODUCT})

    chain = scraper._fetch_eurex("BAS.DE")

    assert stored == [("BAS", day, PRODUCT)]
    assert chain is not None and ("calls" in chain or "puts" in chain)
