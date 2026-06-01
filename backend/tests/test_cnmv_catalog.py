"""Tests for the CNMV catalog: registry parsing, type mapping, search, migration."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models import AltInvestmentCatalog, AltInvestmentType, Base, User
from backend.services import cnmv_catalog as cc

# A minimal FONDREGISTRO sample: one multi-class fund + one single-class fund.
SAMPLE_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<FondRegistro>
  <FechaDatos>202601</FechaDatos>
  <Entidad>
    <Tipo>FI</Tipo>
    <NumeroRegistro>9</NumeroRegistro>
    <Denominacion>FONMARCH, FI</Denominacion>
    <ETF>NO</ETF>
    <Compartimento>
      <NumeroCompartimento>0</NumeroCompartimento>
      <Clase><NumeroClase>1</NumeroClase><DenominacionClase>CLASE A</DenominacionClase><ISIN>ES0138841038</ISIN></Clase>
      <Clase><NumeroClase>2</NumeroClase><DenominacionClase>CLASE C</DenominacionClase><ISIN>ES0138841004</ISIN></Clase>
    </Compartimento>
    <Gestora><DenominacionGestora>MARCH ASSET MANAGEMENT, S.G.I.I.C., S.A.U.</DenominacionGestora></Gestora>
  </Entidad>
  <Entidad>
    <Tipo>FI</Tipo>
    <NumeroRegistro>11</NumeroRegistro>
    <Denominacion>GESIURIS IURISFOND, FI</Denominacion>
    <ETF>NO</ETF>
    <Compartimento>
      <NumeroCompartimento>0</NumeroCompartimento>
      <Clase><NumeroClase>0</NumeroClase><DenominacionClase>CLASE 0</DenominacionClase><ISIN>ES0156322036</ISIN></Clase>
    </Compartimento>
    <Gestora><DenominacionGestora>GESIURIS ASSET MANAGEMENT</DenominacionGestora></Gestora>
  </Entidad>
</FondRegistro>"""


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ── Parser ────────────────────────────────────────────────────────────


def test_parse_registry_one_row_per_isin():
    rows = cc._parse_registry(SAMPLE_XML)
    assert len(rows) == 3  # 2 classes + 1 class
    isins = {r["isin"] for r in rows}
    assert isins == {"ES0138841038", "ES0138841004", "ES0156322036"}


def test_parse_registry_multiclass_labels_and_singleclass():
    rows = {r["isin"]: r for r in cc._parse_registry(SAMPLE_XML)}
    # multi-class fund → class appended to disambiguate
    assert rows["ES0138841038"]["name"] == "FONMARCH, FI — CLASE A"
    assert rows["ES0138841004"]["name"] == "FONMARCH, FI — CLASE C"
    # single-class fund → plain name, no suffix
    assert rows["ES0156322036"]["name"] == "GESIURIS IURISFOND, FI"
    assert rows["ES0138841038"]["manager"] == "MARCH ASSET MANAGEMENT, S.G.I.I.C., S.A.U."
    assert rows["ES0138841038"]["source"] == "CNMV_IIC"
    assert rows["ES0138841038"]["vehicle_subtype"] == "FI"


def test_map_tipo():
    assert cc._map_tipo("FI") == AltInvestmentType.OTHER.value
    assert cc._map_tipo("FII") == AltInvestmentType.REAL_ESTATE.value
    assert cc._map_tipo("FIL") == AltInvestmentType.HEDGE_FUND.value
    assert cc._map_tipo("???") == AltInvestmentType.OTHER.value


# ── Search ────────────────────────────────────────────────────────────


def _seed(db, rows):
    for r in rows:
        db.add(AltInvestmentCatalog(**r, updated_at=datetime.now(timezone.utc)))
    db.commit()


def test_search_prefix_ranks_first(db):
    _seed(db, [
        {"source": "CNMV_IIC", "external_id": "A1", "name": "FONDO MARCH GLOBAL", "type": "OTHER", "manager": "X", "isin": "A1", "vehicle_subtype": "FI"},
        {"source": "CNMV_IIC", "external_id": "B1", "name": "MARCH PATRIMONIO", "type": "OTHER", "manager": "X", "isin": "B1", "vehicle_subtype": "FI"},
    ])
    res = cc.search_catalog(db, "march")
    # "MARCH PATRIMONIO" (prefix) must outrank "FONDO MARCH GLOBAL" (substring)
    assert res[0]["name"] == "MARCH PATRIMONIO"
    assert {r["isin"] for r in res} == {"A1", "B1"}
    assert isinstance(res[0]["type"], str)  # coerced from enum for the API schema


def test_search_by_isin_exact(db):
    _seed(db, [{"source": "CNMV_IIC", "external_id": "ES0138841038", "name": "FONMARCH", "type": "OTHER", "manager": "X", "isin": "ES0138841038", "vehicle_subtype": "FI"}])
    res = cc.search_catalog(db, "es0138841038")  # case-insensitive
    assert len(res) == 1 and res[0]["isin"] == "ES0138841038"


def test_search_short_query_guard(db):
    assert cc.search_catalog(db, "a") == []
    assert cc.search_catalog(db, "") == []


def test_search_type_filter(db):
    _seed(db, [
        {"source": "CNMV_IIC", "external_id": "R1", "name": "INMO UNO", "type": "REAL_ESTATE", "manager": "X", "isin": "R1", "vehicle_subtype": "FII"},
        {"source": "CNMV_IIC", "external_id": "O1", "name": "INMO DOS FONDO", "type": "OTHER", "manager": "X", "isin": "O1", "vehicle_subtype": "FI"},
    ])
    res = cc.search_catalog(db, "inmo", type_filter="REAL_ESTATE")
    assert [r["isin"] for r in res] == ["R1"]


# ── Staleness ─────────────────────────────────────────────────────────


def test_catalog_is_stale_empty_then_fresh(db):
    assert cc.catalog_is_stale(db) is True
    _seed(db, [{"source": "CNMV_IIC", "external_id": "A1", "name": "X", "type": "OTHER", "manager": "", "isin": "A1", "vehicle_subtype": "FI"}])
    assert cc.catalog_is_stale(db) is False


def test_catalog_is_stale_old_rows(db):
    old = datetime.now(timezone.utc) - timedelta(days=30)
    db.add(AltInvestmentCatalog(source="CNMV_IIC", external_id="A1", name="X", type="OTHER", manager="", isin="A1", vehicle_subtype="FI", updated_at=old))
    db.commit()
    assert cc.catalog_is_stale(db) is True


# ── Additive migration (ensure_columns) ───────────────────────────────


def test_ensure_columns_adds_isin_to_legacy_table(monkeypatch):
    """A pre-existing alt_investments table without `isin` gets the column added."""
    import backend.database as dbmod

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE alt_investments (id INTEGER PRIMARY KEY, name TEXT)"
        ))
    monkeypatch.setattr(dbmod, "engine", engine)

    assert "isin" not in {c["name"] for c in inspect(engine).get_columns("alt_investments")}
    dbmod.ensure_columns()
    assert "isin" in {c["name"] for c in inspect(engine).get_columns("alt_investments")}
    dbmod.ensure_columns()  # idempotent — no error on second run


# ── HTTP endpoint (search response schema + isin round-trip) ──────────


def test_search_endpoint_and_isin_roundtrip():
    """Full FastAPI path: /search validates against the response schema, and a
    position created with an ISIN (the prefill path) round-trips it back."""
    from fastapi.testclient import TestClient

    from backend.api.auth import get_current_user
    from backend.app import app
    from backend.database import get_db

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        user = User(email="cnmv@test.com", name="T")
        s.add(user)
        s.add(AltInvestmentCatalog(
            source="CNMV_IIC", external_id="ES0138841038", name="FONMARCH, FI — CLASE A",
            type="OTHER", manager="MARCH ASSET MANAGEMENT", isin="ES0138841038",
            vehicle_subtype="FI", updated_at=datetime.now(timezone.utc),
        ))
        s.commit()
        uid = user.id

    def _override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: Session().get(User, uid)
    try:
        client = TestClient(app)
        r = client.get("/api/alt-investments/search", params={"q": "fonmarch"})
        assert r.status_code == 200
        body = r.json()
        assert body and body[0]["isin"] == "ES0138841038"
        assert body[0]["type"] == "OTHER"  # enum coerced to str by the schema

        # short query guard + bad type
        assert client.get("/api/alt-investments/search", params={"q": "a"}).json() == []
        assert client.get(
            "/api/alt-investments/search", params={"q": "x", "type": "BOGUS"}
        ).status_code == 400

        # create from the prefill path → ISIN round-trips
        created = client.post("/api/alt-investments/", json={
            "name": "FONMARCH, FI — CLASE A", "type": "OTHER",
            "isin": "ES0138841038", "currency": "EUR", "current_nav": 1000,
        })
        assert created.status_code == 201
        assert created.json()["isin"] == "ES0138841038"
        assert client.get("/api/alt-investments/").json()[0]["isin"] == "ES0138841038"
    finally:
        app.dependency_overrides.clear()
