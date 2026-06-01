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
from datetime import datetime, timedelta, timezone
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


def _download_registry_xml(zip_url: str) -> bytes:
    """Download the monthly ZIP and return the FONDREGISTRO XML bytes."""
    resp = requests.get(zip_url, headers=_HEADERS, timeout=120)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        member = next(
            (n for n in zf.namelist() if n.upper().startswith("FONDREGISTRO") and n.lower().endswith(".xml")),
            None,
        )
        if member is None:
            raise ValueError("FONDREGISTRO XML not found in CNMV ZIP")
        return zf.read(member)


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
                    for c in ("name", "type", "manager", "isin", "vehicle_subtype", "updated_at")
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
    rows = _parse_registry(_download_registry_xml(url))
    n = _upsert_catalog(rows)
    logger.info("[cnmv-catalog] upserted %d catalog rows", n)
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


def search_catalog(db, q: str, type_filter: str | None = None, limit: int = 20) -> list[dict]:
    """Search the catalog by name (substring) or exact ISIN. Prefix matches rank first."""
    q = (q or "").strip()
    if len(q) < 2:
        return []
    pattern = f"%{q}%"
    prefix = f"{q}%"
    upper_q = q.upper()

    stmt = select(AltInvestmentCatalog).where(
        AltInvestmentCatalog.source == _SOURCE,
        or_(
            AltInvestmentCatalog.name.ilike(pattern),
            AltInvestmentCatalog.isin == upper_q,
        ),
    )
    if type_filter:
        stmt = stmt.where(AltInvestmentCatalog.type == type_filter)
    # Prefix-of-name matches first, then the rest, alphabetically.
    stmt = stmt.order_by(
        AltInvestmentCatalog.name.ilike(prefix).desc(), AltInvestmentCatalog.name
    ).limit(limit)

    return [
        {
            "name": r.name,
            # `type` may load back as an enum member; the API schema expects a str.
            "type": r.type.value if hasattr(r.type, "value") else r.type,
            "manager": r.manager,
            "isin": r.isin,
            "source": r.source,
        }
        for r in db.execute(stmt).scalars().all()
    ]
