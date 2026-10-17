"""What each held company says about artificial intelligence in its own annual report.

No score and no probability: no published, verifiable dataset rates a company's
odds of being displaced by AI, and FinView does not advise. What is shown is
what the issuer wrote, with a link to where it wrote it:

- `mentions`, counted in code: how many times the part of the filing that was
  read names AI (`TERMS`, in the languages EU reports are filed in).
- up to three quotes the model picks from the passages that name AI, each one
  checked to appear verbatim in the filing and to name AI itself. One quote that
  does not match drops all of them and the summary with them, the same rule the
  segment reader applies to amounts.

US ISINs are read in the latest 10-K's Item 1A (Risk Factors) on EDGAR. ESEF
reports have no standard risk section, so the whole report is read and the UI
says so. Same caching contract as the segment reader (`refresh.py`): a definite
answer is cached for `RECHECK_DAYS`, a failed request or model call writes nothing.
"""

from __future__ import annotations

import codecs
import html
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import AiMentionCheck, AiMentionReport, SegmentReport
from backend.services import llm_envelope
from backend.services.llm_rules import NOT_ADVICE_RULE_ES
from backend.services.portfolio_service import Position
from backend.services.segments import esef, industry_index, sec
from backend.services.segments.classify import UNASSIGNED, ClassificationError
from backend.services.segments.exposure import latest_reports
from backend.services.segments.refresh import _already_read, _record, due_isins
from backend.services.segments.sec import SourceUnavailable

logger = logging.getLogger(__name__)

# The languages ESEF reports are filed in, plus the acronyms. Acronyms are matched
# case-sensitively and as whole words: "AI" and "IA", not "said" or "Gaia".
TERMS = re.compile(
    r"(?i:\bartificial intelligence\b|\bmachine learning\b|\blarge language models?\b"
    r"|\binteligencia artificial\b|\bintelig[êe]ncia artificial\b"
    r"|\bintelligence artificielle\b|\bintelligenza artificiale\b"
    r"|\bk[üu]nstliche[nr]? intelligenz\b|\bkunstmatige intelligentie\b)"
    r"|\b(?:Gen)?AI\b|\bIA\b|\bKI\b"
)

THEMES: dict[str, str] = {
    "competition": "Competencia y demanda",
    "products": "Productos y servicios propios",
    "operations": "Operaciones y costes",
    "regulation": "Regulación y litigios",
    "security": "Ciberseguridad y fraude",
    "other": "Otros",
}

SCOPES = {"risk_factors": "Factores de riesgo (10-K, Item 1A)", "annual_report": "Informe anual"}

OUTCOME_DETAIL = {
    "ok": "Informe anual leído",
    "no_issuer": "Sin emisor identificable en GLEIF ni en la SEC (ETF, fondo u otro producto)",
    "no_filing": "Sin informe anual publicado en EDGAR ni en filings.xbrl.org",
    "no_section": "No se encontró el apartado de factores de riesgo del informe",
    "too_large": "El informe supera el tamaño que FinView descarga",
}

REQUEST_SECONDS = 40.0
CRON_SECONDS = 120.0

# Inditex's FY2024 ESEF report is 85 MB, 59 MB of it embedded images (dropped
# while reading). Past this the report is recorded as too large, not read.
MAX_REPORT_BYTES = 150_000_000
# An Item 1A shorter than this is a cross-reference or "not applicable".
MIN_SECTION_CHARS = 2_000

# What the model sees: the passages around each mention, not the whole report.
CONTEXT_CHARS = 350
MAX_CONTEXT_CHARS = 24_000
MAX_QUOTES = 3
QUOTE_CHARS = (20, 800)
SUMMARY_CHARS = 400

_CENT = Decimal("0.01")


class AiReadError(Exception):
    """The model did not answer usably. Not cached: the next refresh retries."""


class TooLarge(Exception):
    """The report is larger than MAX_REPORT_BYTES. A fact about this filing."""


# ── reading a filing as text ─────────────────────────────────────────

_TAG = re.compile(r"<[^<>]*>")
_BLOCK = re.compile(r"(?i)^</?(?:p|div|tr|br|li|h[1-6]|table|section)\b")
_SKIP_OPEN = re.compile(r"(?i)^<(script|style)\b")
_SKIP_CLOSE = re.compile(r"(?i)^</(script|style)\b")
# Inline XBRL contexts: <xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>…
_DATE_OPEN = re.compile(r"(?i)^<(?:[\w-]+:)?(startdate|enddate)\s*>")
_DATE_CLOSE = re.compile(r"(?i)^</(?:[\w-]+:)?(?:startdate|enddate)\s*>")
_DATA_URI = re.compile(rb"[\"']data:")


class TextStream:
    """HTML or XHTML bytes in, plain text out, one line per block element.

    Fed chunk by chunk so an 85 MB report never sits in memory whole. Quoted
    `data:` URIs (embedded images) are dropped at byte level before decoding;
    tags are dropped as they complete, and a tag split between chunks is carried.

    It also keeps the inline-XBRL context periods it passes (`periods`, as (start, last
    day)), so an ESEF report says which year it covers: the listing is not always right
    (`esef.fiscal_year_end`).
    """

    def __init__(self) -> None:
        self._quote: bytes | None = None  # inside a data: URI, until this byte
        self._tail = b""  # a '"data:' marker split between chunks
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._carry = ""  # an unfinished tag
        self._skip = False  # inside <script> or <style>
        self._parts: list[str] = []
        self._date_tag: str | None = None  # just inside <startDate> or <endDate>
        self._date_text = ""  # its text so far, when a chunk ends inside it
        self._start: date | None = None
        self.periods: list[tuple[date, date]] = []

    def feed(self, chunk: bytes) -> None:
        self._text(self._decoder.decode(self._strip_data_uris(chunk)))

    def close(self) -> str:
        if self._quote is None:
            self._text(self._decoder.decode(self._tail, final=True))
        text = html.unescape("".join(self._parts))
        lines = (re.sub(r"[\s\u200b\u00ad]+", " ", line).strip() for line in text.split("\n"))
        return "\n".join(line for line in lines if line)

    def _strip_data_uris(self, chunk: bytes) -> bytes:
        buf, self._tail, out, i = self._tail + chunk, b"", [], 0
        while True:
            if self._quote is not None:
                end = buf.find(self._quote, i)
                if end < 0:
                    return b"".join(out)
                self._quote, i = None, end
            m = _DATA_URI.search(buf, i)
            if m is None:
                keep = max(i, len(buf) - 6)
                out.append(buf[i:keep])
                self._tail = buf[keep:]
                return b"".join(out)
            out.append(buf[i : m.start() + 1])
            self._quote, i = buf[m.start() : m.start() + 1], m.end()

    def _text(self, s: str) -> None:
        s, self._carry, i = self._carry + s, "", 0
        for m in _TAG.finditer(s):
            if not self._skip:
                self._parts.append(s[i : m.start()])
            tag = m.group()
            if self._date_tag and _DATE_CLOSE.match(tag):
                self._period(self._date_tag, self._date_text + s[i : m.start()])
            opened = _DATE_OPEN.match(tag)
            self._date_tag = opened.group(1).lower() if opened else None
            self._date_text = ""
            if _SKIP_OPEN.match(tag) and not tag.endswith("/>"):
                self._skip = True
            elif _SKIP_CLOSE.match(tag):
                self._skip = False
            self._parts.append("\n" if _BLOCK.match(tag) else " ")
            i = m.end()
        rest = s[i:]
        cut = rest.find("<")
        if cut >= 0:
            self._carry, rest = rest[cut:], rest[:cut]
        if self._date_tag:
            self._date_text += rest
        if not self._skip:
            self._parts.append(rest)

    def _period(self, which: str, value: str) -> None:
        try:
            day = date.fromisoformat(value.strip())
        except ValueError:
            self._start = None
            return
        if which == "startdate":
            self._start = day
        elif self._start is not None:
            self.periods.append((self._start, day))
            self._start = None


@dataclass
class Document:
    text: str
    periods: list[tuple[date, date]]  # inline-XBRL context periods, (start, last day)


def read_text(http: httpx.Client, url: str, seconds: float) -> Document | None:
    """The document at `url` as text; None on 404. Bounded in bytes and in time.

    filings.xbrl.org serves an 85 MB report in 6 to 12 s most of the time and past
    30 s some of the time, so a read may use its run's whole budget, never more.
    """
    stream, size = TextStream(), 0
    deadline = time.monotonic() + seconds
    host = url.split("/")[2]
    try:
        with http.stream("GET", url) as resp:
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                raise SourceUnavailable(f"HTTP {resp.status_code} on {host}")
            for chunk in resp.iter_bytes(1 << 16):
                size += len(chunk)
                if size > MAX_REPORT_BYTES:
                    raise TooLarge(f"{host} report over {MAX_REPORT_BYTES} bytes")
                if time.monotonic() > deadline:
                    raise SourceUnavailable(f"{host} read took over {seconds:.0f}s")
                stream.feed(chunk)
    except httpx.HTTPError as exc:
        raise SourceUnavailable(f"{type(exc).__name__} on {host}") from exc
    return Document(stream.close(), stream.periods)


def _key(line: str) -> str:
    """'ITEM 1A. RIS K FACTORS' → 'item1ariskfactors' (headings are styled letter by letter)."""
    return re.sub(r"[^a-z0-9]", "", line.lower())


_ITEM_1A = "item1ariskfactors"
_NEXT_ITEMS = ("item1bunresolvedstaffcomments", "item1ccybersecurity", "item2properties")


def risk_factors(text: str) -> str | None:
    """Item 1A of a 10-K: the longest stretch from its heading to the next item's.

    The table of contents carries the same headings a few lines apart, so the
    longest stretch is the section itself. A heading may be split over two lines
    ("Item 1A." / "Risk Factors").
    """
    lines = text.split("\n")
    keys = [_key(line) for line in lines]
    joined = [k + (keys[i + 1] if i + 1 < len(keys) else "") for i, k in enumerate(keys)]

    def is_start(i: int) -> bool:
        return keys[i] == _ITEM_1A or (keys[i] == "item1a" and joined[i] == _ITEM_1A)

    def is_end(i: int) -> bool:
        return keys[i] in _NEXT_ITEMS or (
            keys[i] in ("item1b", "item1c", "item2") and joined[i] in _NEXT_ITEMS
        )

    ends = [i for i in range(len(lines)) if is_end(i)]
    best: tuple[int, int] | None = None
    for start in (i for i in range(len(lines)) if is_start(i)):
        end = next((e for e in ends if e > start), None)
        if end is not None and (best is None or end - start > best[1] - best[0]):
            best = (start, end)
    if best is None:
        return None
    section = "\n".join(lines[best[0] + 1 : best[1]])
    return section if len(section) >= MIN_SECTION_CHARS else None


# ── counting and quoting ─────────────────────────────────────────────


def normalize(text: str) -> str:
    """One line, plain quotes and dashes: what a quote is compared against."""
    text = (
        text.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("–", "-")
        .replace("—", "-")
    )
    return re.sub(r"[\s\u200b\u00ad]+", " ", text).strip()


def count(text: str) -> tuple[int, int]:
    """(mentions of AI, words) in `text`."""
    return len(TERMS.findall(text)), len(re.findall(r"\w+", text))


def passages(text: str) -> list[str]:
    """The text around each mention, overlapping windows merged, capped in total."""
    windows: list[list[int]] = []
    for m in TERMS.finditer(text):
        start, end = max(0, m.start() - CONTEXT_CHARS), min(len(text), m.end() + CONTEXT_CHARS)
        if windows and start <= windows[-1][1]:
            windows[-1][1] = end
        else:
            windows.append([start, end])
    out, total = [], 0
    for start, end in windows:
        if total >= MAX_CONTEXT_CHARS:
            break
        out.append(text[start:end])
        total += end - start
    return out


_SYSTEM = (
    "You read passages from a listed company's annual report. Each passage mentions "
    "artificial intelligence. Answer with one JSON object and nothing else: "
    '{"quotes": [{"text": "...", "theme": "<theme key>"}], "summary": "..."}. '
    f"quotes: at most {MAX_QUOTES} passages that best show what the company says AI means "
    "for its own business. Copy each one exactly as printed in the passages: one or two "
    "complete sentences, no ellipsis, no edits, no translation. Each quote must itself "
    "name AI. "
    f"Theme keys: {', '.join(THEMES)}. "
    "summary: one sentence in Spanish, at most 300 characters, stating what the company "
    'itself says about AI and attributing it to the company ("La empresa señala que..."). '
    "If the passages use AI only as an unrelated abbreviation, answer "
    '{"quotes": [], "summary": null}. ' + NOT_ADVICE_RULE_ES
)


def ask(company: str, text: str) -> str:
    """The model's raw answer for the passages of `text` that mention AI."""
    user = f"Company: {company}\n\nPassages:\n" + "\n---\n".join(passages(text))
    content, error = llm_envelope.chat(
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        context=f"ai mentions {company}",
        timeout=45.0,
        temperature=0,
        max_tokens=2000,
        response_format={"type": "json_object"},
        reasoning=llm_envelope.NO_REASONING,
    )
    if error or content is None:
        raise AiReadError(error or "The model returned no text")
    return content


def verify(content: str, text: str) -> tuple[list[dict], str | None, str]:
    """(quotes, summary, status) from the model's answer, checked against `text`.

    Raises AiReadError when the answer is not a JSON object (not cached). A quote
    that is not in the filing word for word, or that does not itself name AI,
    rejects every quote and the summary: status "unverified".
    """
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        answer = json.loads(raw)
    except ValueError as exc:
        raise AiReadError("The AI reader did not return JSON") from exc
    if not isinstance(answer, dict):
        raise AiReadError("The AI reader did not return an object")

    items = answer.get("quotes")
    if items is None:
        items = []
    if not isinstance(items, list):
        return [], None, "unverified"
    source = normalize(text)
    quotes: list[dict] = []
    for item in items[:MAX_QUOTES]:
        quote = normalize(str(item.get("text") or "")) if isinstance(item, dict) else ""
        if not (
            QUOTE_CHARS[0] <= len(quote) <= QUOTE_CHARS[1]
            and quote in source
            and TERMS.search(quote)
        ):
            return [], None, "unverified"
        theme = item.get("theme")
        quotes.append({"text": quote, "theme": theme if theme in THEMES else "other"})
    if not quotes:
        return [], None, "none"
    summary = answer.get("summary")
    summary = summary.strip()[:SUMMARY_CHARS] if isinstance(summary, str) else None
    return quotes, summary or None, "ok"


# ── refresh ──────────────────────────────────────────────────────────


def refresh(
    db: Session, holdings: dict[str, tuple[str | None, str]], budget_seconds: float
) -> dict:
    """Read the due ISINs in `holdings` ({isin: (ticker, name)}) until the budget is spent.

    First maps any segment report's business lines that have no industry yet (one
    model call each, no download), then reads the due annual reports.
    """
    due = due_isins(db, holdings, model=AiMentionCheck)
    unmapped = unmapped_reports(db, holdings)
    if not settings.openrouter_api_key:
        return {"checked": 0, "pending": len(due) + len(unmapped)}
    deadline = time.monotonic() + budget_seconds
    checked = 0
    for report in unmapped:
        if time.monotonic() >= deadline:
            break
        try:
            _map_industries(report, holdings[report.isin][1])
            db.commit()
            checked += 1
        except ClassificationError as exc:
            db.rollback()
            logger.warning("[ai-industries] %s skipped: %s", report.isin, exc)
        except Exception:
            db.rollback()
            logger.exception("[ai-industries] %s failed", report.isin)
    cik_by_ticker: dict[str, int] | None = None
    with sec.client() as sec_http, esef.client() as esef_http:
        for isin in due:
            if time.monotonic() >= deadline:
                break
            ticker, name = holdings[isin]
            try:
                if isin.startswith("US"):
                    if cik_by_ticker is None:
                        cik_by_ticker = sec.ticker_to_cik(sec_http)
                    _check_sec(db, isin, ticker, name, sec_http, cik_by_ticker, budget_seconds)
                else:
                    _check_esef(db, isin, name, esef_http, budget_seconds)
                db.commit()
                checked += 1
            except (SourceUnavailable, AiReadError) as exc:
                # Not a fact about the issuer: leave no trace, retry next run.
                db.rollback()
                logger.warning("[ai-mentions] %s skipped: %s", isin, exc)
            except IntegrityError:
                db.rollback()
            except Exception:
                db.rollback()
                logger.exception("[ai-mentions] %s failed", isin)
    pending = len(due_isins(db, holdings, model=AiMentionCheck)) + len(
        unmapped_reports(db, holdings)
    )
    return {"checked": checked, "pending": pending}


def _business(lines: list[dict]) -> list[dict]:
    return [ln for ln in lines if ln["axis"] == "business"]


def unmapped_reports(db: Session, isins) -> list[SegmentReport]:
    """Latest segment reports whose business lines have not been given an industry.

    The segment reader writes lines without one, so a new annual report (or one read
    before this existed) is picked up here instead of waiting a year for the next.
    """
    return [
        report
        for report in latest_reports(db, sorted(set(isins))).values()
        if any("industry" not in ln for ln in _business(json.loads(report.lines)))
    ]


def _map_industries(report: SegmentReport, company: str) -> None:
    lines = json.loads(report.lines)
    labels = sorted({ln["label"] for ln in _business(lines)})
    mapping = industry_index.map_industries(company, labels)
    for ln in _business(lines):
        ln["industry"] = mapping.get(ln["label"], UNASSIGNED)
    report.lines = json.dumps(lines, ensure_ascii=False)


def _note(db: Session, isin: str, outcome: str, filing_id: str | None = None) -> None:
    _record(db, isin, outcome, filing_id, model=AiMentionCheck)


def _read(db, isin, http, url, filing_id, seconds) -> Document | None:
    try:
        return read_text(http, url, seconds)
    except TooLarge:
        _note(db, isin, "too_large", filing_id)
        return None


def _check_sec(db, isin, ticker, name, http, cik_by_ticker, seconds) -> None:
    cik = cik_by_ticker.get((ticker or "").upper())
    if cik is None:
        return _note(db, isin, "no_issuer")
    filing = sec.latest_10k(http, cik)
    if filing is None:
        return _note(db, isin, "no_filing")
    if _already_read(db, isin, filing.filing_id, model=AiMentionCheck):
        return None
    doc = _read(db, isin, http, filing.url, filing.filing_id, seconds)
    if doc is None:
        return None
    section = risk_factors(doc.text)
    if section is None:
        return _note(db, isin, "no_section", filing.filing_id)
    _store(
        db,
        isin,
        name,
        "sec",
        "risk_factors",
        filing.filing_id,
        filing.url,
        filing.period_end,
        section,
    )


def _check_esef(db, isin, name, http, seconds) -> None:
    lei = esef.isin_to_lei(http, isin)
    if lei is None:
        return _note(db, isin, "no_issuer")
    filing = esef.latest_filing(http, lei)
    if filing is None:
        return _note(db, isin, "no_filing")
    if not filing.report_url:
        return _note(db, isin, "no_section", filing.filing_id)
    if _already_read(db, isin, filing.filing_id, model=AiMentionCheck):
        return None
    doc = _read(db, isin, http, esef._BASE + filing.report_url, filing.filing_id, seconds)
    if doc is None:
        return None
    _store(
        db,
        isin,
        name,
        "esef",
        "annual_report",
        filing.filing_id,
        filing.url,
        esef.fiscal_year_end(doc.periods, filing.period_end),
        doc.text,
    )


def _store(db, isin, name, source, scope, filing_id, url, period_end: date, text: str) -> None:
    mentions, words = count(text)
    quotes, summary, status = [], None, "none"
    if mentions:
        quotes, summary, status = verify(ask(name, text), text)

    row = (
        db.query(AiMentionReport)
        .filter(AiMentionReport.isin == isin, AiMentionReport.fiscal_year == period_end.year)
        .one_or_none()
    )
    if row is None:
        row = AiMentionReport(isin=isin, fiscal_year=period_end.year)
        db.add(row)
    row.period_end = period_end
    row.source = source
    row.scope = scope
    row.filing_id = filing_id
    row.source_url = url
    row.mentions = mentions
    row.words = words
    row.quotes = json.dumps(quotes, ensure_ascii=False)
    row.quotes_status = status
    row.summary = summary
    # The count stands; rejected quotes are retried at the next recheck, not on
    # every page load: no filing id, so the same filing is read again then.
    _note(db, isin, "ok", None if status == "unverified" else filing_id)


# ── what the portfolio page shows ────────────────────────────────────


def _money(v: Decimal) -> float:
    return float(v.quantize(_CENT, rounding=ROUND_HALF_UP))


def _pct(part: Decimal, whole: Decimal) -> float:
    return float((part / whole * 100).quantize(_CENT)) if whole > 0 else 0.0


def build(db: Session, positions: list[Position]) -> dict:
    isins = [p.isin for p in positions]
    reports: dict[str, AiMentionReport] = {}
    for row in db.query(AiMentionReport).filter(AiMentionReport.isin.in_(isins)).all():
        if row.isin not in reports or row.fiscal_year > reports[row.isin].fiscal_year:
            reports[row.isin] = row
    checks = {
        c.isin: c for c in db.query(AiMentionCheck).filter(AiMentionCheck.isin.in_(isins)).all()
    }
    known_value = sum(
        (p.market_value_eur for p in positions if p.market_value_eur is not None), Decimal(0)
    )

    segments = latest_reports(db, isins)
    table = industry_index.industries()
    holdings, read_value, mention_value = [], Decimal(0), Decimal(0)
    theme_value: dict[str, Decimal] = {}
    index_value, index_weighted = Decimal(0), Decimal(0)
    industry_value: dict[str, Decimal] = {}
    for p in positions:
        report, check = reports.get(p.isin), checks.get(p.isin)
        value = p.market_value_eur
        industry, industry_detail = _industry(segments.get(p.isin))
        if industry and industry["score"] is not None and value is not None:
            covered = value * industry["revenue_share"]
            index_value += covered
            index_weighted += covered * industry["score"]
            for part in industry["parts"]:
                if part["score"] is not None:
                    code = part["industry"]
                    industry_value[code] = (
                        industry_value.get(code, Decimal(0)) + value * part["share"]
                    )
        quotes = json.loads(report.quotes) if report else []
        if report and value is not None:
            read_value += value
            if report.mentions:
                mention_value += value
            for theme in {q["theme"] for q in quotes}:
                theme_value[theme] = theme_value.get(theme, Decimal(0)) + value
        holdings.append(
            {
                "isin": p.isin,
                "name": p.name,
                "ticker": p.ticker,
                "value_eur": _money(value) if value is not None else None,
                "status": check.outcome if check else "pending",
                "detail": OUTCOME_DETAIL[check.outcome] if check else "Pendiente de consultar",
                "fiscal_year": report.fiscal_year if report else None,
                "source": report.source if report else None,
                "scope": report.scope if report else None,
                "scope_label": SCOPES[report.scope] if report else None,
                "url": report.source_url if report else None,
                "mentions": report.mentions if report else None,
                "per_10k_words": round(report.mentions / report.words * 10_000, 1)
                if report and report.words
                else None,
                "quotes": [{**q, "theme_label": THEMES[q["theme"]]} for q in quotes],
                "quotes_status": report.quotes_status if report else None,
                "summary": report.summary if report else None,
                "industry": _industry_out(industry, segments.get(p.isin)),
                "industry_detail": industry_detail,
            }
        )
    holdings.sort(key=lambda h: (h["mentions"] is None, -(h["value_eur"] or 0)))
    return {
        "total_value_eur": _money(known_value),
        "read_pct": _pct(read_value, known_value),
        "mentioning_pct": _pct(mention_value, known_value),
        "themes": sorted(
            (
                {"key": k, "label": THEMES[k], "pct": _pct(v, known_value)}
                for k, v in theme_value.items()
            ),
            key=lambda t: -t["pct"],
        ),
        "holdings": holdings,
        "pending": sum(1 for h in holdings if h["status"] == "pending"),
        "industry_index": {
            "score": float(round(index_weighted / index_value, 4)) if index_value > 0 else None,
            "value_pct": _pct(index_value, known_value),
            "industries": sorted(
                (
                    {
                        "code": code,
                        "title": table[code]["title"],
                        "score": table[code]["score"],
                        "value_pct": _pct(v, known_value),
                    }
                    for code, v in industry_value.items()
                ),
                key=lambda r: -r["value_pct"],
            ),
            "sources": industry_index.load()["sources"],
        },
    }


INDUSTRY_DETAIL = {
    "no_report": "Sin desglose de ingresos por negocio en su informe anual",
    "no_business": "El informe desglosa los ingresos por región, no por negocio",
    "unmapped": "Pendiente de asignar sus segmentos a una industria",
    "unassigned": "Ningún segmento se pudo asignar a una industria",
}


def _industry(report: SegmentReport | None) -> tuple[dict | None, str | None]:
    """(company_exposure or None, why it is missing)."""
    if report is None:
        return None, INDUSTRY_DETAIL["no_report"]
    lines = json.loads(report.lines)
    if not [ln for ln in _business(lines) if Decimal(ln["value"]) > 0]:
        return None, INDUSTRY_DETAIL["no_business"]
    out = industry_index.company_exposure(lines)
    if out is None:
        return None, INDUSTRY_DETAIL["unmapped"]
    if out["score"] is None:
        return out, INDUSTRY_DETAIL["unassigned"]
    return out, None


def _industry_out(industry: dict | None, report: SegmentReport | None) -> dict | None:
    if industry is None or industry["score"] is None:
        return None
    return {
        "score": float(round(industry["score"], 4)),
        "revenue_pct": _pct(industry["revenue_share"], Decimal(1)),
        "fiscal_year": report.fiscal_year,
        "url": report.source_url,
        "parts": [
            {
                "label": part["label"],
                "industry": part["industry"],
                "title": part["title"],
                "score": part["score"],
                "pct": _pct(part["share"], Decimal(1)),
            }
            for part in sorted(industry["parts"], key=lambda part: -part["share"])
        ],
    }
