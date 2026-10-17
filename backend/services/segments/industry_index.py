"""AI exposure by industry: occupation scores weighted by who each industry employs.

FinView computes this itself, with the method Felten, Raj and Seamans (2021) use
for their AI Industry Exposure: an industry's score is the average exposure of
its occupations, weighted by how many people each occupation employs in it.
Their published industry table carries no licence, so the inputs are two sources
that may be republished:

- occupation exposure: Eloundou, Manning, Mishkin and Rock, "GPTs are GPTs",
  Science 384 (2024), data under MIT. The β measure is the share of an
  occupation's tasks a language model could do at least twice as fast at the
  same quality (counting half when it needs extra software on top). Human ratings.
- employment by occupation and industry: BLS OEWS national industry-specific
  estimates, 4-digit NAICS (US government work, public domain).

The table is built offline by `scripts/build_ai_industry_exposure.py` from
pinned versions of both and committed as `data/ai_industry_exposure.json`, with
the versions inside it. Nothing here downloads anything at runtime.

A company's score is its segments' industry scores weighted by the revenue each
segment reports: the segment reader's business lines, mapped to an industry by
the shared model (`map_industries`). It describes the work done in those
industries in the US; it is not a forecast about the company.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from backend.services import llm_envelope
from backend.services.segments.classify import UNASSIGNED, ClassificationError, _strip_fence

logger = logging.getLogger(__name__)

DATA = Path(__file__).parent / "data" / "ai_industry_exposure.json"


# ── building the table (offline) ─────────────────────────────────────


def occupation_scores(rows: Iterable[dict], column: str) -> dict[str, float]:
    """6-digit SOC → score, averaging the O*NET-SOC detail codes under it.

    O*NET splits some SOC occupations ("11-1011.00" and "11-1011.03"); OEWS
    counts employment at the SOC level, so the O*NET codes are averaged.
    """
    by_soc: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_soc[row["O*NET-SOC Code"][:7]].append(float(row[column]))
    return {soc: sum(v) / len(v) for soc, v in by_soc.items()}


def score_for(code: str, scores: dict[str, float]) -> float | None:
    """An OEWS occupation's score; None when the occupation scores do not cover it.

    OEWS publishes some occupations only as an aggregate whose code ends in 0
    ("31-1120" for 31-1121 and 31-1122): those take the average of the detailed
    codes under them. Anything else without a score is left out, never guessed.
    """
    if code in scores:
        return scores[code]
    if code.endswith("0"):
        under = [v for soc, v in scores.items() if soc.startswith(code[:6])]
        if under:
            return sum(under) / len(under)
    return None


def industry_scores(oews_rows: Iterable[dict], scores: dict[str, float]) -> dict[str, dict]:
    """NAICS code → {"title", "score", "coverage"} from OEWS rows.

    `score` is the employment-weighted mean over the detailed occupations that
    have a score; `coverage` is the share of the industry's total employment
    those occupations account for. Rows whose employment OEWS suppresses ("**")
    are skipped.
    """
    acc: dict[str, dict] = defaultdict(lambda: {"title": "", "total": 0.0, "known": 0.0, "w": 0.0})
    for row in oews_rows:
        emp = row.get("TOT_EMP")
        if not isinstance(emp, (int, float)):
            continue
        ind = acc[row["NAICS"]]
        ind["title"] = row["NAICS_TITLE"]
        if row["O_GROUP"] == "total":
            ind["total"] = float(emp)
        elif row["O_GROUP"] == "detailed":
            score = score_for(row["OCC_CODE"], scores)
            if score is not None:
                ind["known"] += emp
                ind["w"] += emp * score
    return {
        code: {
            "title": ind["title"],
            "score": round(ind["w"] / ind["known"], 4),
            "coverage": round(ind["known"] / ind["total"], 4),
        }
        for code, ind in sorted(acc.items())
        if ind["known"] > 0 and ind["total"] > 0
    }


# ── reading the table ────────────────────────────────────────────────


@lru_cache(maxsize=1)
def load() -> dict:
    """The committed table: {"sources": {...}, "industries": {naics: {...}}}."""
    return json.loads(DATA.read_text(encoding="utf-8"))


def industries() -> dict[str, dict]:
    return load()["industries"]


# ── mapping segments to industries (model) ───────────────────────────


def _system() -> str:
    listing = "\n".join(f"{code}: {ind['title']}" for code, ind in industries().items())
    return (
        "You place the business segments of a listed company in US industries "
        "(NAICS, as used by the BLS). You receive segment names exactly as the annual "
        "report prints them, in any language. Answer with one JSON object and nothing "
        'else: {"<name>": "<industry code>"}. Use every name you were given as a key, '
        "spelled exactly as given, and only codes from the list below. Choose the "
        "industry whose work produces most of that segment's revenue. Use unassigned "
        "when the name alone does not tell you (Other, Corporate, Eliminations, a code "
        "you do not recognise). Do not guess.\n\n" + listing
    )


def map_industries(company: str, labels: list[str]) -> dict[str, str]:
    """{label: NAICS code or "unassigned"}. Raises ClassificationError (not cached)."""
    if not labels:
        return {}
    content, error = llm_envelope.chat(
        [
            {"role": "system", "content": _system()},
            {
                "role": "user",
                "content": json.dumps({"company": company, "segments": labels}, ensure_ascii=False),
            },
        ],
        context=f"segment industries {company}",
        timeout=45.0,
        temperature=0,
        max_tokens=1500,
        response_format={"type": "json_object"},
        reasoning=llm_envelope.NO_REASONING,
    )
    if error or content is None:
        raise ClassificationError(error or "The model returned no text")
    try:
        answer = json.loads(_strip_fence(content))
    except ValueError as exc:
        raise ClassificationError("The industry mapper did not return JSON") from exc
    if not isinstance(answer, dict):
        raise ClassificationError("The industry mapper did not return an object")
    known = industries()
    return {label: answer[label] if answer.get(label) in known else UNASSIGNED for label in labels}


# ── a company's score ────────────────────────────────────────────────


def company_exposure(lines: list[dict]) -> dict | None:
    """A segment report's business lines → its revenue-weighted industry score.

    Shares are over positive business revenue, as for sector exposure. Lines
    without an industry in the table count in the denominator of `revenue_share`
    and nowhere else, so the score is the average over the revenue it covers and
    `revenue_share` says how much that is. None without business lines, or before
    the lines are mapped.
    """
    business = [ln for ln in lines if ln["axis"] == "business" and Decimal(ln["value"]) > 0]
    if not business or any("industry" not in ln for ln in business):
        return None
    total = sum((Decimal(ln["value"]) for ln in business), Decimal(0))
    known = industries()
    parts = []
    for ln in business:
        ind = known.get(ln["industry"])
        parts.append(
            {
                "label": ln["label"],
                "industry": ln["industry"] if ind else UNASSIGNED,
                "title": ind["title"] if ind else None,
                "score": ind["score"] if ind else None,
                "share": Decimal(ln["value"]) / total,
            }
        )
    covered = sum((p["share"] for p in parts if p["score"] is not None), Decimal(0))
    score = (
        sum(
            (p["share"] * Decimal(str(p["score"])) for p in parts if p["score"] is not None),
            Decimal(0),
        )
        / covered
        if covered > 0
        else None
    )
    return {"score": score, "revenue_share": covered, "parts": parts}
