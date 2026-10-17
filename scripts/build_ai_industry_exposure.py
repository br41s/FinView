"""Build backend/services/segments/data/ai_industry_exposure.json from pinned sources.

    python scripts/build_ai_industry_exposure.py

Downloads the Eloundou et al. occupation scores at a fixed commit and one BLS OEWS
release, computes each industry's score with `industry_index.industry_scores`, and
writes the table with both versions recorded in it. Run it again only to move to a
new release: bump OEWS_RELEASE (and OEWS_URL), or ELOUNDOU_COMMIT, and commit the
regenerated JSON together with the change. See `.claude/rules/segments.md`.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import httpx
import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.segments.industry_index import DATA, industry_scores, occupation_scores

ELOUNDOU_REPO = "https://github.com/openai/GPTs-are-GPTs"
ELOUNDOU_COMMIT = "0471612fef3cc22b74fb884d27bff9dbd3770582"
ELOUNDOU_RAW = f"https://raw.githubusercontent.com/openai/GPTs-are-GPTs/{ELOUNDOU_COMMIT}"
ELOUNDOU_COLUMN = "human_rating_beta"

OEWS_RELEASE = "May 2025"
OEWS_URL = "https://www.bls.gov/oes/special-requests/oesm25in4.zip"
OEWS_MEMBER = "oesm25in4/nat4d_M2025_dl.xlsx"

# BLS refuses requests without a contact in the User-Agent, like SEC.
HEADERS = {"User-Agent": "FinView data build hola@biglobster.top"}


def main() -> None:
    with httpx.Client(headers=HEADERS, timeout=120.0, follow_redirects=True) as http:
        occ_csv = http.get(f"{ELOUNDOU_RAW}/data/occ_level.csv").raise_for_status().text
        licence = http.get(f"{ELOUNDOU_RAW}/LICENSE").raise_for_status().text
        oews_zip = http.get(OEWS_URL).raise_for_status().content

    scores = occupation_scores(csv.DictReader(io.StringIO(occ_csv)), ELOUNDOU_COLUMN)
    with tempfile.TemporaryDirectory() as tmp:
        path = zipfile.ZipFile(io.BytesIO(oews_zip)).extract(OEWS_MEMBER, tmp)
        sheet = openpyxl.load_workbook(path, read_only=True).active
        rows = sheet.iter_rows(values_only=True)
        header = next(rows)
        table = industry_scores((dict(zip(header, r, strict=True)) for r in rows), scores)

    out = {
        "sources": {
            "method": {
                "citation": "Felten, Raj & Seamans (2021), Strategic Management Journal 42(12)",
                "doi": "10.1002/smj.3286",
            },
            "occupations": {
                "citation": "Eloundou, Manning, Mishkin & Rock (2024), GPTs are GPTs: "
                "Labor market impact potential of LLMs, Science 384(6702):1306-1308",
                "doi": "10.1126/science.adj0998",
                "url": f"{ELOUNDOU_REPO}/tree/{ELOUNDOU_COMMIT}",
                "commit": ELOUNDOU_COMMIT,
                "column": ELOUNDOU_COLUMN,
                "license": "MIT",
            },
            "employment": {
                "citation": "BLS Occupational Employment and Wage Statistics, national "
                "industry-specific estimates, 4-digit NAICS",
                "release": OEWS_RELEASE,
                "url": OEWS_URL,
                "license": "Public domain (US government work)",
            },
            "built": date.today().isoformat(),
        },
        "industries": table,
    }
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (DATA.parent / "LICENSE-GPTs-are-GPTs.txt").write_text(licence, encoding="utf-8")
    print(f"{len(table)} industries → {DATA}")


if __name__ == "__main__":
    main()
