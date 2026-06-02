"""CNMV catalog — searchable index of regulated Spanish IIC vehicles.

Powers the search bar on /alt-investments. Downloads the free CNMV "información
individual de IIC" monthly registry (FONDREGISTRO), which lists every registered
investment fund (Fondo de Inversión) with its share-class ISINs, name and
management company, and upserts it into `alt_investment_catalog`.

Design (mirrors the Eurex daily-cache + ECB FX patterns):
- The registry is downloaded at most once per refresh, never per request.
- Search (`search_catalog`) hits the local DB only — fast, no HTTP.
- Refresh is best-effort: a CNMV change degrades search gracefully, never breaks
  the page.

Coverage note: the monthly registry file is Fondos de Inversión (Tipo=FI) only.
SICAVs, real-estate IICs and hedge funds (IICIL) live in separate CNMV registries
(HTML) and are deferred to a later slice; the type mapping below is already ready
for them.
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import iterparse

import requests
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.database import SessionLocal, engine
from backend.models import AltInvestmentType, AltInvestmentCatalog

logger = logging.getLogger(__name__)

_SOURCE = "CNMV_IIC"
_DOWNLOAD_PAGE = "https://www.cnmv.es/portal/publicaciones/descarga-informacion-individual"
_HEADERS = {"User-Agent": "FinView/1.0 (personal investment dashboard)"}
_STALE_DAYS = 7

# CNMV "Tipo" code → AltInvestmentType. Funds/SICAVs aren't strictly alternative
# (→ OTHER); the genuinely alternative IIC types map to their category.
_TIPO_MAP = {
    "FI": AltInvestmentType.OTHER,      # Fondo de Inversión
    "SI": AltInvestmentType.OTHER,      # Sociedad de Inversión (SICAV)
    "SICAV": AltInvestmentType.OTHER,
    "FII": AltInvestmentType.REAL_ESTATE,   # Fondo de Inversión Inmobiliaria
    "SII": AltInvestmentType.REAL_ESTATE,   # Sociedad de Inversión Inmobiliaria
    "FIL": AltInvestmentType.HEDGE_FUND,    # Fondo de Inversión Libre
    "SIL": AltInvestmentType.HEDGE_FUND,    # Sociedad de Inversión Libre
    "IL": AltInvestmentType.HEDGE_FUND,
}


def _map_tipo(tipo: str) -> str:
    return _TIPO_MAP.get((tipo or "").strip().upper(), AltInvestmentType.OTHER).value


# ── Download ──────────────────────────────────────────────────────────────────


def _latest_zip_url(year: int) -> str | None:
    """Return the download URL of the most recent monthly file for `year`."""
    from bs4 import BeautifulSoup

    resp = requests.get(
        _DOWNLOAD_PAGE, params={"ejercicio": year}, headers=_HEADERS, timeout=60
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    zips = [a.get("href") for a in soup.find_all("a", id=True) if a["id"].endswith("lnkZip")]
    zips = [h for h in zips if h]
    return zips[-1] if zips else None  # last row = latest month


def _download_zip_members(zip_url: str) -> tuple[bytes, bytes | None]:
    """Download the monthly ZIP and return (FONDREGISTRO XML, FONDMENS XML | None).

    FONDREGISTRO (identity) is required; FONDMENS (NAV/fund size) is optional —
    enrichment degrades gracefully if it's absent. Retries once on a transient
    download error (the CNMV endpoint occasionally drops large connections).
    """
    content = b""
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            resp = requests.get(zip_url, headers=_HEADERS, timeout=120)
            resp.raise_for_status()
            content = resp.content
            break
        except requests.RequestException as exc:  # incl. ChunkedEncodingError
            last_err = exc
            logger.warning("[cnmv-catalog] download attempt %d failed: %s", attempt + 1, exc)
    if not content:
        raise last_err or RuntimeError("CNMV download failed")
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        def _member(prefix: str) -> str | None:
            return next(
                (n for n in zf.namelist()
                 if n.upper().startswith(prefix) and n.lower().endswith(".xml")),
                None,
            )

        reg = _member("FONDREGISTRO")
        if reg is None:
            raise ValueError("FONDREGISTRO XML not found in CNMV ZIP")
        mens = _member("FONDMENS")
        return zf.read(reg), (zf.read(mens) if mens else None)


# ── Parse ─────────────────────────────────────────────────────────────────────


def _parse_registry(xml_bytes: bytes) -> list[dict]:
    """Parse a FONDREGISTRO XML → one row per share-class ISIN.

    Each <Entidad> holds Tipo, Denominacion and a Gestora; share classes
    (each with its own ISIN) are nested under Compartimento/Clase. Pure function
    (no DB / network) so it can be unit-tested against a sample fixture.
    """
    rows: list[dict] = []
    for _ev, el in iterparse(io.BytesIO(xml_bytes), events=("end",)):
        if el.tag.split("}")[-1] != "Entidad":
            continue
        tipo = (el.findtext("Tipo") or "").strip()
        name = (el.findtext("Denominacion") or "").strip()
        gestora = ""
        gestora_el = el.find("Gestora")
        if gestora_el is not None:
            gestora = (gestora_el.findtext("DenominacionGestora") or "").strip()

        classes = [c for c in el.iter() if c.tag.split("}")[-1] == "Clase"]
        multi = len(classes) > 1
        for clase in classes:
            isin = (clase.findtext("ISIN") or "").strip()
            if not isin:
                continue
            label = name
            if multi:
                clase_name = (clase.findtext("DenominacionClase") or "").strip()
                if clase_name:
                    label = f"{name} — {clase_name}"
            rows.append(
                {
                    "source": _SOURCE,
                    "external_id": isin,
                    "name": label[:255],
                    "type": _map_tipo(tipo),
                    "manager": gestora[:255],
                    "isin": isin,
                    "vehicle_subtype": tipo[:20],
                }
            )
        el.clear()
    return rows


def _latest_day(container) -> Decimal | None:
    """Return the value of the highest-numbered, non-empty ``*_DiaN`` child."""
    best_n, best_val = -1, None
    if container is None:
        return None
    for child in container:
        text = (child.text or "").strip()
        if not text:
            continue
        tag = child.tag.split("}")[-1]
        try:
            n = int(tag.rsplit("Dia", 1)[-1])
        except ValueError:
            continue
        if n > best_n:
            try:
                best_val = Decimal(text)
                best_n = n
            except InvalidOperation:
                continue
    return best_val


def _mens_data_date(fecha: str | None) -> date | None:
    """FONDMENS FechaDatos is YYYYMM → last day stored as the first of that month."""
    if not fecha or len(fecha) < 6:
        return None
    try:
        return date(int(fecha[:4]), int(fecha[4:6]), 1)
    except ValueError:
        return None


def _parse_mens(xml_bytes: bytes) -> dict[str, dict]:
    """Parse a FONDMENS XML → {isin: {nav, fund_size, data_date}}.

    NAV is the share class's own latest daily VL; fund_size is the sum of the
    latest patrimonio across all share classes of the same fund (Entidad).
    Pure function (no DB / network).
    """
    out: dict[str, dict] = {}
    data_date: date | None = None
    for _ev, el in iterparse(io.BytesIO(xml_bytes), events=("end",)):
        tag = el.tag.split("}")[-1]
        if tag == "FechaDatos":  # root-level element, fires before any Entidad
            if data_date is None:
                data_date = _mens_data_date(el.text)
            continue
        if tag != "Entidad":
            continue
        classes = [c for c in el.iter() if c.tag.split("}")[-1] == "Clase"]
        per_class: list[tuple[str, Decimal | None, Decimal | None]] = []
        fund_size: Decimal | None = None
        for clase in classes:
            isin = (clase.findtext("ISIN") or "").strip()
            if not isin:
                continue
            nav = _latest_day(clase.find("VLDiario"))
            patr = _latest_day(clase.find("PatrimonioDiario"))
            per_class.append((isin, nav, patr))
            if patr is not None:
                fund_size = (fund_size or Decimal(0)) + patr
        for isin, nav, _patr in per_class:
            out[isin] = {"nav": nav, "fund_size": fund_size, "data_date": data_date}
        el.clear()
    return out


# ── Upsert ────────────────────────────────────────────────────────────────────


def _upsert_catalog(rows: list[dict]) -> int:
    if not rows:
        return 0
    now = datetime.now(timezone.utc)
    for r in rows:
        r["updated_at"] = now
    dialect = engine.dialect.name
    BATCH = 500
    n = 0
    with SessionLocal() as db:
        for i in range(0, len(rows), BATCH):
            chunk = rows[i : i + BATCH]
            if dialect in ("postgresql", "sqlite"):
                ins = pg_insert if dialect == "postgresql" else sqlite_insert
                stmt = ins(AltInvestmentCatalog).values(chunk)
                update_cols = {
                    c: stmt.excluded[c]
                    for c in ("name", "type", "manager", "isin", "vehicle_subtype",
                              "nav", "fund_size", "data_date", "updated_at")
                }
                stmt = stmt.on_conflict_do_update(
                    index_elements=["source", "external_id"], set_=update_cols
                )
            else:  # pragma: no cover - other dialects unused
                stmt = AltInvestmentCatalog.__table__.insert().values(chunk)
            db.execute(stmt)
            n += len(chunk)
        db.commit()
    return n


# ── Public API ────────────────────────────────────────────────────────────────


def refresh_iic_catalog() -> int:
    """Download the latest CNMV IIC registry and upsert it. Best-effort."""
    year = datetime.now(timezone.utc).year
    url = _latest_zip_url(year) or _latest_zip_url(year - 1)
    if not url:
        logger.warning("[cnmv-catalog] no downloadable registry found")
        return 0
    logger.info("[cnmv-catalog] downloading registry %s", url[:80])
    reg_xml, mens_xml = _download_zip_members(url)
    rows = _parse_registry(reg_xml)
    enrich = _parse_mens(mens_xml) if mens_xml else {}
    for r in rows:
        extra = enrich.get(r["isin"])
        if extra:
            r["nav"] = extra["nav"]
            r["fund_size"] = extra["fund_size"]
            r["data_date"] = extra["data_date"]
    n = _upsert_catalog(rows)
    logger.info("[cnmv-catalog] upserted %d catalog rows (%d enriched)", n, len(enrich))
    return n


def catalog_is_stale(db) -> bool:
    """True if the catalog is empty or its newest row is older than _STALE_DAYS."""
    newest = db.execute(
        select(func.max(AltInvestmentCatalog.updated_at)).where(
            AltInvestmentCatalog.source == _SOURCE
        )
    ).scalar_one_or_none()
    if newest is None:
        return True
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    return newest < datetime.now(timezone.utc) - timedelta(days=_STALE_DAYS)


_SORTS = {"name", "fund_size_desc", "nav_desc", "nav_asc"}


def search_catalog(
    db,
    q: str,
    type_filter: str | None = None,
    min_fund_size: Decimal | float | None = None,
    max_fund_size: Decimal | float | None = None,
    sort: str = "name",
    limit: int = 20,
) -> list[dict]:
    """Search/browse the catalog.

    Matches by name (substring) or exact ISIN when ``q`` has ≥2 chars. With a
    short/empty ``q`` it still browses when a filter or non-default sort is given
    (e.g. "largest funds"); otherwise returns []. Prefix-of-name ranks first
    unless an explicit ``sort`` is chosen.
    """
    q = (q or "").strip()
    Model = AltInvestmentCatalog
    sort = sort if sort in _SORTS else "name"
    has_filter = (
        type_filter is not None or min_fund_size is not None or max_fund_size is not None
    )
    browsing = len(q) < 2
    if browsing and not has_filter and sort == "name":
        return []

    stmt = select(Model).where(Model.source == _SOURCE)
    if not browsing:
        stmt = stmt.where(or_(Model.name.ilike(f"%{q}%"), Model.isin == q.upper()))
    if type_filter:
        stmt = stmt.where(Model.type == type_filter)
    if min_fund_size is not None:
        stmt = stmt.where(Model.fund_size >= Decimal(str(min_fund_size)))
    if max_fund_size is not None:
        stmt = stmt.where(Model.fund_size <= Decimal(str(max_fund_size)))

    if sort == "fund_size_desc":
        stmt = stmt.order_by(Model.fund_size.is_(None), Model.fund_size.desc(), Model.name)
    elif sort == "nav_desc":
        stmt = stmt.order_by(Model.nav.is_(None), Model.nav.desc(), Model.name)
    elif sort == "nav_asc":
        stmt = stmt.order_by(Model.nav.is_(None), Model.nav.asc(), Model.name)
    elif not browsing:  # default relevance: prefix-of-name first
        stmt = stmt.order_by(Model.name.ilike(f"{q}%").desc(), Model.name)
    else:
        stmt = stmt.order_by(Model.name)
    stmt = stmt.limit(limit)

    return [
        {
            "name": r.name,
            # `type` may load back as an enum member; the API schema expects a str.
            "type": r.type.value if hasattr(r.type, "value") else r.type,
            "manager": r.manager,
            "isin": r.isin,
            "source": r.source,
            "nav": float(r.nav) if r.nav is not None else None,
            "fund_size": float(r.fund_size) if r.fund_size is not None else None,
            "data_date": r.data_date.isoformat() if r.data_date else None,
        }
        for r in db.execute(stmt).scalars().all()
    ]
