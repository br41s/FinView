"""A portfolio's market value spread over the sectors and regions its issuers report.

Each position's market value is split by the share of revenue each segment of
its latest annual report earned. Shares are taken over the positive lines only:
corporate adjustments and eliminations are negative and have no sector or
region, so they are left out of the split (they still count for the add-up
check when the report is read).

Nothing is spread over positions it does not cover. A position without segment
data is its own "Sin datos" bucket at its full market value, and a position
without a price is listed apart and left out, since its value is unknown.
"""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from backend.models import SegmentCheck, SegmentReport
from backend.services.portfolio_service import Position
from backend.services.segments.classify import REGIONS, SECTORS
from backend.services.segments.refresh import OUTCOME_DETAIL

NO_DATA = "no_data"
_CENT = Decimal("0.01")

AXES = {"sector": ("business", SECTORS), "geography": ("geography", REGIONS)}


def _money(v: Decimal) -> float:
    return float(v.quantize(_CENT, rounding=ROUND_HALF_UP))


def latest_reports(db: Session, isins: list[str]) -> dict[str, SegmentReport]:
    out: dict[str, SegmentReport] = {}
    for row in db.query(SegmentReport).filter(SegmentReport.isin.in_(isins)).all():
        if row.isin not in out or row.fiscal_year > out[row.isin].fiscal_year:
            out[row.isin] = row
    return out


def shares(report: SegmentReport, axis: str) -> list[tuple[str, str, Decimal]]:
    """(label, category, share of positive revenue) for one axis of a report."""
    lines = [
        (line["label"], line["category"], Decimal(line["value"]))
        for line in json.loads(report.lines)
        if line["axis"] == axis and Decimal(line["value"]) > 0
    ]
    total = sum((v for _, _, v in lines), Decimal(0))
    return [(label, cat, v / total) for label, cat, v in lines] if total > 0 else []


def build(db: Session, positions: list[Position]) -> dict:
    isins = [p.isin for p in positions]
    reports = latest_reports(db, isins)
    checks = {c.isin: c for c in db.query(SegmentCheck).filter(SegmentCheck.isin.in_(isins)).all()}
    priced = [p for p in positions if p.market_value_eur is not None]
    known_value = sum((p.market_value_eur for p in priced), Decimal(0))

    result: dict = {
        "total_value_eur": _money(known_value),
        "unpriced": [{"isin": p.isin, "name": p.name} for p in positions if p not in priced],
        "sources": [],
    }

    for out_key, (axis, taxonomy) in AXES.items():
        buckets: dict[str, dict] = defaultdict(lambda: {"value": Decimal(0), "holdings": []})
        for p in priced:
            report = reports.get(p.isin)
            split = shares(report, axis) if report else []
            if not split:
                bucket = buckets[NO_DATA]
                bucket["value"] += p.market_value_eur
                bucket["holdings"].append(
                    {
                        "isin": p.isin,
                        "name": p.name,
                        "ticker": p.ticker,
                        "value_eur": _money(p.market_value_eur),
                        "measure": None,
                        "segments": [],
                    }
                )
                continue
            by_category: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
            for label, category, share in split:
                by_category[category].append((label, share))
            for category, parts in by_category.items():
                share = sum((s for _, s in parts), Decimal(0))
                value = p.market_value_eur * share
                bucket = buckets[category]
                bucket["value"] += value
                bucket["holdings"].append(
                    {
                        "isin": p.isin,
                        "name": p.name,
                        "ticker": p.ticker,
                        "value_eur": _money(value),
                        "measure": report.measure or "revenue",
                        "segments": [
                            {"label": label, "pct": float((s * 100).quantize(_CENT))}
                            for label, s in parts
                        ],
                    }
                )

        labels = {**taxonomy, NO_DATA: "Sin datos"}
        rows = [
            {
                "key": key,
                "label": labels.get(key, key),
                "value_eur": _money(b["value"]),
                "pct": float((b["value"] / known_value * 100).quantize(_CENT))
                if known_value > 0
                else 0.0,
                "holdings": sorted(b["holdings"], key=lambda h: -h["value_eur"]),
            }
            for key, b in buckets.items()
        ]
        # Largest first, with the two "we don't know" buckets always last.
        rows.sort(
            key=lambda r: (
                r["key"] in (NO_DATA, "unassigned"),
                r["key"] == NO_DATA,
                -r["value_eur"],
            )
        )
        result[out_key] = rows

    for p in positions:
        report, check = reports.get(p.isin), checks.get(p.isin)
        result["sources"].append(
            {
                "isin": p.isin,
                "name": p.name,
                "status": check.outcome if check else "pending",
                "detail": OUTCOME_DETAIL[check.outcome] if check else "Pendiente de consultar",
                "fiscal_year": report.fiscal_year if report else None,
                "source": report.source if report else None,
                "measure": (report.measure or "revenue") if report else None,
                "url": report.source_url if report else None,
                "axis_status": json.loads(report.axis_status) if report else None,
            }
        )
    result["pending"] = sum(1 for s in result["sources"] if s["status"] == "pending")
    return result
