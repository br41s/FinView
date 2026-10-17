"""Map the segment names a company reports onto FinView's sectors and regions.

Companies name their own segments ("iPhone", "Redes", "IEI"), so placing them
in a sector or a region is the one judgment step in this pipeline. It is done by
the shared model in one call per report, and its answer is constrained to the
keys below: anything else becomes "unassigned". The original label is stored
next to the category, so every placement can be checked against the report.

The sector list is FinView's own: GICS is licensed by MSCI and S&P and cannot
be reproduced here.
"""

from __future__ import annotations

import json
import logging

from backend.services import llm_envelope

logger = logging.getLogger(__name__)

UNASSIGNED = "unassigned"

SECTORS: dict[str, str] = {
    "energy": "Energía",
    "materials": "Materiales",
    "industrials": "Industria",
    "consumer_discretionary": "Consumo discrecional",
    "consumer_staples": "Consumo básico",
    "health": "Salud",
    "financials": "Finanzas",
    "technology": "Tecnología",
    "communication": "Comunicaciones",
    "utilities": "Suministros (utilities)",
    "real_estate": "Inmobiliario",
    UNASSIGNED: "Sin clasificar",
}

REGIONS: dict[str, str] = {
    "spain": "España",
    "europe": "Europa (sin España)",
    "north_america": "Norteamérica",
    "latin_america": "Latinoamérica",
    "asia_pacific": "Asia-Pacífico",
    "middle_east_africa": "Oriente Medio y África",
    "multi_region": "Varias regiones",
    UNASSIGNED: "Sin asignar",
}

_SYSTEM = (
    "You classify the reporting segments of a listed company. You receive the "
    "segment names exactly as the annual report prints them, in any language. "
    "Answer with one JSON object and nothing else: "
    '{"business": {"<name>": "<sector key>"}, "geography": {"<name>": "<region key>"}}. '
    "Use every name you were given as a key, spelled exactly as given. "
    f"Sector keys: {', '.join(k for k in SECTORS if k != UNASSIGNED)}. "
    f"Region keys: {', '.join(k for k in REGIONS if k != UNASSIGNED)}. "
    "Use multi_region for a name that spans several regions (Americas, International, "
    "Rest of world). Use unassigned when the name alone does not tell you "
    "(Other, Corporate, Eliminations, a code you do not recognise). Do not guess."
)


class ClassificationError(Exception):
    """The model did not answer usably. Not cached: the next refresh retries."""


def classify(company: str, business: list[str], geography: list[str]) -> dict[str, dict[str, str]]:
    """Return {"business": {label: sector}, "geography": {label: region}}."""
    if not business and not geography:
        return {"business": {}, "geography": {}}
    user = json.dumps(
        {"company": company, "business": business, "geography": geography}, ensure_ascii=False
    )
    content, error = llm_envelope.chat(
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        context=f"segment classifier {company}",
        timeout=45.0,
        temperature=0,
        max_tokens=2000,
        response_format={"type": "json_object"},
        reasoning=llm_envelope.NO_REASONING,
    )
    if error:
        raise ClassificationError(error)
    return {
        "business": _constrain(content, "business", business, SECTORS),
        "geography": _constrain(content, "geography", geography, REGIONS),
    }


def _constrain(content: str, axis: str, labels: list[str], keys: dict[str, str]) -> dict[str, str]:
    try:
        answer = json.loads(_strip_fence(content)).get(axis) or {}
    except (ValueError, AttributeError) as exc:
        raise ClassificationError("The classifier did not return a JSON object") from exc
    if not isinstance(answer, dict):
        raise ClassificationError(f"The classifier's {axis} map is not an object")
    return {
        label: answer.get(label) if answer.get(label) in keys else UNASSIGNED for label in labels
    }


def _strip_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    return text
