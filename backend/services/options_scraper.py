"""Options data scraper — Yahoo Finance + MEFF (Spanish exchange) + Eurex (European)."""

import io
import logging
import math
import re
import time
import zipfile
from datetime import date, datetime
from xml.etree.ElementTree import iterparse

import numpy as np
import requests
import yfinance as yf
from bs4 import BeautifulSoup

from backend.services import ticker_map

logger = logging.getLogger(__name__)

MAX_EXPIRATIONS = 3  # ~6 weeks of data

# MEFF (Spanish exchange) — direct HTML scraping, no proxy needed
_MEFF_BASE = "https://www.meff.es/ing/Financial-Derivatives/Spreadsheet/"
_MEFF_SLUGS: dict[str, str] = {
    # IBEX-35 blue chips (original 11)
    "TEF": "TEF_Telefonica",
    "BBVA": "BBVA_BBVA",
    "SAN": "SAN_B__Santander",
    "IBE": "IBE_Iberdrola",
    "ITX": "ITX_Inditex",
    "REP": "REP_Repsol",
    "FER": "FER_Ferrovial",
    "RED": "RED_REDEIA",
    "NTGY": "NTGY_Naturgy",
    "AENA": "AENA_AENA",
    "ACX": "ACX_Acerinox",
    # Extended MEFF coverage (verified May 2026)
    "AMS": "AMS_Amadeus",
    "ANA": "ANA_Acciona",
    "BKT": "BKT_Bankinter",
    "CABK": "CABK_CaixaBank",
    "CIE": "CIE_CIE_Automotive",
    "CLNX": "CLNX_Cellnex",
    "COL": "COL_Inmocolonial",
    "ELE": "ELE_Endesa",
    "ENG": "ENG_Enagas",
    "GRF": "GRF_Grifols",
    "IAG": "IAG_IAG",
    "IDR": "IDR_Indra",
    "MAP": "MAP_MAPFRE",
    "MEL": "MEL_Melia",
    "MRL": "MRL_Merlin",
    "PHM": "PHM_PharmaMar",
    "SAB": "SAB_Sabadell",
    "SLR": "SLR_Solaria",
    "VIS": "VIS_Viscofan",
}
# data-tipo codes: O{C=Call|P=Put}A{YYYYMMDD}
_TIPO_RE = re.compile(r"^O(C|P)A(\d{8})$")

_SQRT_2PI = math.sqrt(2 * math.pi)

_ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{10}$')
_ISIN_CACHE: dict[str, str] = {}  # ISIN → resolved ticker symbol

# 5-minute in-memory cache for options chains: ticker → (data, unix_ts)
_OPTIONS_CACHE: dict[str, tuple[dict, float]] = {}
_OPTIONS_TTL = 300.0  # seconds

# Per-expiry chain cache: "TICKER:YYYY-MM-DD" → (data, unix_ts)
_EXPIRY_CACHE: dict[str, tuple[dict, float]] = {}

# Expirations-list cache: ticker → (list[str], unix_ts)
_EXPIRATIONS_CACHE: dict[str, tuple[list, float]] = {}

# Eurex RDF (Reference Data File) daily cache — refreshed once per trading day
_EUREX_RDF_CACHE: dict = {
    "date": None,      # str YYYY-MM-DD of last successful load
    "products": {},    # product_code → {underlying_isin, sym, prev_close, options:[]}
    "isin_to_code": {},  # underlying ISIN → Eurex product code
    "sym_to_code": {},   # underlying symbol → Eurex product code (e.g. "BAS" → "BASE")
}
_EUREX_RDF_PAGE = "https://www.eurex.com/ex-en/data/trading-files/rdf-files"
_FIXML_NS = "{http://www.fixprotocol.org/FIXML-5-0-SP2}"
# Exchange suffixes that Eurex covers (excluding .MC which MEFF handles)
_EUREX_SUFFIXES = {".DE", ".PA", ".AS", ".L", ".MI", ".SW", ".ZU", ".BR",
                   ".VI", ".OL", ".ST", ".CO", ".HE", ".LS", ".PR"}


# ── Math helpers ─────────────────────────────────────────────────────


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _safe_int(val, default: int = 0) -> int:
    """Convert to int, handling NaN, Inf, and None."""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return int(f)
    except (ValueError, TypeError):
        return default


def _safe_float(val, default: float = 0.0) -> float:
    """Convert to float, handling NaN, Inf, and None."""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


# ── ISIN resolution ──────────────────────────────────────────────────


def _resolve_isin(isin: str) -> str | None:
    """Resolve an ISIN to a ticker symbol. Curated map first, then Yahoo search; cached.

    The curated map is where corporate actions are known (AENA's pre/post-split
    ISINs share one ticker on purpose); a raw Yahoo search does not know that.
    """
    if isin in _ISIN_CACHE:
        return _ISIN_CACHE[isin]
    curated = ticker_map.CURATED.get(isin)
    if curated:
        _ISIN_CACHE[isin] = curated
        return curated
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={isin}&quotesCount=1&newsCount=0"
        resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            quotes = resp.json().get("quotes", [])
            if quotes:
                symbol = quotes[0].get("symbol")
                if symbol:
                    _ISIN_CACHE[isin] = symbol
                    logger.info("ISIN %s resolved to ticker %s", isin, symbol)
                    return symbol
    except Exception:
        logger.warning("ISIN resolution failed for %s", isin)
    return None


def _as_ticker(identifier: str) -> str | None:
    """The symbol to ask the sources for, or None when there is none.

    A watchlist row can hold an ISIN: a portfolio position nothing knows a
    ticker for is followed by its ISIN. One that resolves is fetched as its
    ticker. One that does not — a bond, a subscription right — has no chain,
    and must not reach a source as if it were a symbol. yfinance reads a
    12-character ISIN-shaped string as an ISIN, looks it up itself and raises
    ValueError when it finds nothing: three ERROR tracebacks per agent cycle in
    prod, for a bond and two rights that had been synced from the portfolio.
    """
    if not _ISIN_RE.match(identifier):
        return identifier
    resolved = _resolve_isin(identifier)
    if resolved is None:
        logger.info("ISIN %s did not resolve to a ticker: no options chain fetched", identifier)
    return resolved


# ── Eurex RDF (European exchange) ────────────────────────────────────


def _get_eurex_rdf_url() -> str | None:
    """Scrape the Eurex RDF files page and return the latest XEUR zip URL."""
    try:
        r = requests.get(_EUREX_RDF_PAGE, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a"):
            href = a.get("href", "")
            if "RDF-File-XEUR" in href and href.endswith(".zip"):
                return "https://www.eurex.com" + href
    except Exception:
        logger.warning("Failed to fetch Eurex RDF page")
    return None


def _parse_eurex_rdf(content: bytes) -> tuple[dict, dict, dict]:
    """Stream-parse a zipped FIXML RDF file.

    Returns (products, isin_to_code, sym_to_code).
    Only OSTK (options on single stocks) products are kept.
    """
    products: dict = {}
    isin_to_code: dict = {}
    sym_to_code: dict = {}

    current_product: str | None = None
    in_secdef = False
    secdef_settlement = 0.0
    secdef_delta = 0.0

    z = zipfile.ZipFile(io.BytesIO(content))
    filename = z.namelist()[0]
    ns = _FIXML_NS

    with z.open(filename) as f:
        for event, elem in iterparse(f, events=("start", "end")):
            tag = elem.tag[len(ns):] if elem.tag.startswith(ns) else elem.tag

            if event == "start":
                if tag == "MktDef":
                    if elem.get("ParentMktSegmID") == "OSTK":
                        code = elem.get("MktSeg", "")
                        if code:
                            current_product = code
                            products[code] = {
                                "product_isin": elem.get("Sym", ""),
                                "ccy": elem.get("Ccy", "EUR"),
                                "underlying_isin": None,
                                "sym": None,
                                "prev_close": None,
                                "options": [],
                            }
                    else:
                        current_product = None

                elif tag == "SecDef" and current_product:
                    in_secdef = True
                    try:
                        secdef_settlement = float(elem.get("PriSetPx") or 0)
                    except ValueError:
                        secdef_settlement = 0.0
                    try:
                        secdef_delta = float(elem.get("PxDelta") or 0)
                    except ValueError:
                        secdef_delta = 0.0

            elif event == "end":
                if tag == "Undly" and current_product and current_product in products:
                    isin = elem.get("ID", "")
                    sym = elem.get("Sym", "")
                    prev_close_str = elem.get("PrevClsPx")
                    products[current_product]["underlying_isin"] = isin
                    products[current_product]["sym"] = sym
                    if prev_close_str:
                        try:
                            products[current_product]["prev_close"] = float(prev_close_str)
                        except ValueError:
                            pass
                    if isin:
                        isin_to_code[isin] = current_product
                    if sym:
                        sym_to_code[sym] = current_product

                elif tag == "Instrmt" and in_secdef and current_product:
                    if elem.get("SecTyp") == "OPT":
                        try:
                            strike = float(elem.get("StrkPx", "0") or "0")
                        except ValueError:
                            strike = 0.0
                        mat_dt = elem.get("MatDt", "")
                        put_call = elem.get("PutCall", "")  # "1"=CALL, "0"=PUT
                        try:
                            mult = int(elem.get("Mult", "100") or "100")
                        except ValueError:
                            mult = 100
                        products[current_product]["options"].append({
                            "strike": strike,
                            "expiration": mat_dt,
                            "type": "CALL" if put_call == "1" else "PUT",
                            "lastPrice": secdef_settlement,
                            "bid": secdef_settlement,
                            "ask": secdef_settlement,
                            "volume": 0,
                            "openInterest": 0,
                            "impliedVolatility": 0.0,
                            "daysToExpiry": 0,
                            "multiplier": mult,
                            "delta": secdef_delta,
                        })

                elif tag == "SecDef":
                    in_secdef = False

                elem.clear()

    return products, isin_to_code, sym_to_code


def _load_eurex_rdf() -> bool:
    """Download and parse the latest Eurex XEUR RDF file. Cached for the trading day."""
    today = date.today().isoformat()
    if _EUREX_RDF_CACHE["date"] == today and _EUREX_RDF_CACHE["products"]:
        return True

    url = _get_eurex_rdf_url()
    if not url:
        logger.warning("Could not find Eurex RDF URL")
        return False

    try:
        logger.info("Downloading Eurex RDF from %s", url)
        r = requests.get(url, timeout=90, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            logger.warning("Eurex RDF download failed: HTTP %s", r.status_code)
            return False

        products, isin_to_code, sym_to_code = _parse_eurex_rdf(r.content)
        _EUREX_RDF_CACHE["date"] = today
        _EUREX_RDF_CACHE["products"] = products
        _EUREX_RDF_CACHE["isin_to_code"] = isin_to_code
        _EUREX_RDF_CACHE["sym_to_code"] = sym_to_code
        logger.info("Eurex RDF loaded: %d OSTK products", len(products))
        return True
    except Exception:
        logger.exception("Eurex RDF parse failed")
        return False


def _fetch_eurex(ticker: str) -> dict | None:
    """Return options chain for a European ticker using Eurex daily settlement data."""
    if not _load_eurex_rdf():
        return None

    # Resolve ticker → Eurex product code
    # Try stripping the exchange suffix (e.g., "BAS.DE" → "BAS")
    sym = ticker.split(".")[0].upper()
    code = _EUREX_RDF_CACHE["sym_to_code"].get(sym)
    if not code:
        logger.debug("No Eurex product found for ticker %s (sym=%s)", ticker, sym)
        return None

    product = _EUREX_RDF_CACHE["products"].get(code)
    if not product or not product["options"]:
        return None

    underlying_price = product.get("prev_close") or 0.0
    if underlying_price <= 0:
        # Fallback: get current price from yfinance
        try:
            info = yf.Ticker(ticker).info or {}
            underlying_price = float(
                info.get("currentPrice") or info.get("regularMarketPrice") or 0
            )
        except Exception:
            pass

    today_dt = datetime.now()
    calls, puts = [], []
    expirations_seen: set[str] = set()

    for opt in product["options"]:
        exp_str = opt["expiration"]
        try:
            exp_dt = datetime.strptime(exp_str, "%Y-%m-%d")
            days = max((exp_dt - today_dt).days, 1)
        except ValueError:
            days = 1

        expirations_seen.add(exp_str)

        # Calculate IV from settlement price
        iv = 0.0
        if underlying_price > 0 and opt["lastPrice"] > 0:
            iv = _solve_iv(underlying_price, opt["strike"], days / 365.0,
                           opt["lastPrice"], opt["type"])

        entry = {**opt, "daysToExpiry": days, "impliedVolatility": iv}
        (calls if opt["type"] == "CALL" else puts).append(entry)

    if not calls and not puts:
        return None

    total_call_vol = sum(c.get("volume", 0) for c in calls)
    total_put_vol = sum(p.get("volume", 0) for p in puts)
    pcr = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else 0

    return {
        "ticker": ticker,
        "current_price": underlying_price,
        "timestamp": datetime.now().isoformat(),
        "stock_data": {},
        "historical_volatility": None,
        "expirations_analyzed": sorted(expirations_seen),
        "calls": calls,
        "puts": puts,
        "calls_count": len(calls),
        "puts_count": len(puts),
        "put_call_ratio": pcr,
        "status": "success",
        "source": "eurex",
    }


# ── Public API ───────────────────────────────────────────────────────


def fetch_options(ticker: str) -> dict | None:
    """Fetch options chain for a ticker. Returns structured options data or None.

    If *ticker* looks like an ISIN (e.g. ES0178430E18), it is first resolved
    to the proper exchange symbol (e.g. TEF.MC) via Yahoo Finance search;
    one that resolves to nothing has no chain. Results are cached in memory
    for 5 minutes.
    """
    ticker = _as_ticker(ticker)
    if ticker is None:
        return None

    cache_key = ticker.upper()
    cached = _OPTIONS_CACHE.get(cache_key)
    if cached and time.time() - cached[1] < _OPTIONS_TTL:
        return cached[0]

    if ticker.endswith(".MC"):
        data = _fetch_meff(ticker)
        if data:
            _OPTIONS_CACHE[cache_key] = (data, time.time())
            return data

    result = _fetch_yahoo(ticker)

    # Yahoo Finance has no European options data — fall back to Eurex RDF
    yahoo_empty = result is None or (result.get("calls_count", 0) == 0 and result.get("puts_count", 0) == 0)
    if yahoo_empty and any(ticker.upper().endswith(s.upper()) for s in _EUREX_SUFFIXES):
        eurex_result = _fetch_eurex(ticker)
        if eurex_result:
            result = eurex_result

    if result:
        _OPTIONS_CACHE[cache_key] = (result, time.time())
    return result


def fetch_expirations(ticker: str) -> list[str]:
    """Return available option expiration dates for a ticker.

    For Yahoo tickers this is a cheap metadata call (no chain data fetched).
    For MEFF/Eurex the full cached result is used to extract unique dates.
    """
    ticker = _as_ticker(ticker)
    if ticker is None:
        return []

    cache_key = ticker.upper()
    cached = _EXPIRATIONS_CACHE.get(cache_key)
    if cached and time.time() - cached[1] < _OPTIONS_TTL:
        return cached[0]

    expirations: list[str] = []
    try:
        if ticker.endswith(".MC") or any(ticker.upper().endswith(s.upper()) for s in _EUREX_SUFFIXES):
            # For MEFF/Eurex: reuse the full fetch (already cached) and extract unique dates
            data = fetch_options(ticker)
            if data:
                seen: set[str] = set()
                for c in data.get("calls", []) + data.get("puts", []):
                    if c.get("expiration"):
                        seen.add(c["expiration"])
                expirations = sorted(seen)
        else:
            yf_ticker = yf.Ticker(ticker)
            expirations = list(yf_ticker.options or [])
    except Exception:
        logger.exception("fetch_expirations failed for %s", ticker)

    _EXPIRATIONS_CACHE[cache_key] = (expirations, time.time())
    return expirations


def fetch_options_for_expiry(ticker: str, expiration: str) -> dict | None:
    """Fetch chain data for a single expiration date.

    For Yahoo: fetches only that one expiry (fast).
    For MEFF/Eurex: reuses the full cached fetch and filters to the requested date.
    """
    ticker = _as_ticker(ticker)
    if ticker is None:
        return None

    cache_key = f"{ticker.upper()}:{expiration}"
    cached = _EXPIRY_CACHE.get(cache_key)
    if cached and time.time() - cached[1] < _OPTIONS_TTL:
        return cached[0]

    result: dict | None = None
    try:
        if ticker.endswith(".MC") or any(ticker.upper().endswith(s.upper()) for s in _EUREX_SUFFIXES):
            full = fetch_options(ticker)
            if full:
                calls = [c for c in full.get("calls", []) if c.get("expiration") == expiration]
                puts = [p for p in full.get("puts", []) if p.get("expiration") == expiration]
                result = {**full, "calls": calls, "puts": puts,
                          "calls_count": len(calls), "puts_count": len(puts)}
        else:
            result = _fetch_yahoo(ticker, expiration=expiration)
            if result is None or (result.get("calls_count", 0) == 0 and result.get("puts_count", 0) == 0):
                if any(ticker.upper().endswith(s.upper()) for s in _EUREX_SUFFIXES):
                    eurex = _fetch_eurex(ticker)
                    if eurex:
                        calls = [c for c in eurex.get("calls", []) if c.get("expiration") == expiration]
                        puts = [p for p in eurex.get("puts", []) if p.get("expiration") == expiration]
                        result = {**eurex, "calls": calls, "puts": puts,
                                  "calls_count": len(calls), "puts_count": len(puts)}
    except Exception:
        logger.exception("fetch_options_for_expiry failed for %s / %s", ticker, expiration)

    if result:
        _EXPIRY_CACHE[cache_key] = (result, time.time())
    return result


# ── Yahoo Finance ────────────────────────────────────────────────────


def _compute_hv(history) -> float | None:
    """30-day annualised historical volatility from price history."""
    if len(history) < 5:
        return None
    returns = np.log(history["Close"] / history["Close"].shift(1)).dropna()
    hv = float(returns.std() * np.sqrt(252) * 100)
    return hv if not np.isnan(hv) else None


def _get_current_price(info: dict, history) -> float | None:
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price is None and not history.empty:
        price = float(history["Close"].iloc[-1])
    return float(price) if price else None


def _build_yahoo_chain(ticker_obj, expirations: list[str]) -> tuple[list[dict], list[dict]]:
    """Fetch and flatten calls/puts for all expirations."""
    calls, puts = [], []
    for exp in expirations:
        chain = ticker_obj.option_chain(exp)
        exp_date = datetime.strptime(exp, "%Y-%m-%d")
        days_to_exp = max((exp_date - datetime.now()).days, 1)
        for _, row in chain.calls.iterrows():
            calls.append(_yahoo_row_to_dict(row, days_to_exp, exp, "CALL"))
        for _, row in chain.puts.iterrows():
            puts.append(_yahoo_row_to_dict(row, days_to_exp, exp, "PUT"))
    return calls, puts


def _fetch_yahoo(ticker: str, expiration: str | None = None) -> dict | None:
    """Fetch options data from Yahoo Finance.

    If *expiration* is given (YYYY-MM-DD), only that single expiry is fetched.
    Otherwise the first MAX_EXPIRATIONS dates are used (agent-cycle default).
    """
    try:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info or {}
        history = yf_ticker.history(period="30d")

        current_price = _get_current_price(info, history)
        if not current_price:
            logger.warning("No price for %s", ticker)
            return None

        hv = _compute_hv(history)
        if expiration:
            expirations = [expiration] if expiration in (yf_ticker.options or []) else []
        else:
            expirations = yf_ticker.options[:MAX_EXPIRATIONS] if yf_ticker.options else []
        calls, puts = _build_yahoo_chain(yf_ticker, expirations)

        total_call_vol = sum(c.get("volume", 0) or 0 for c in calls)
        total_put_vol = sum(p.get("volume", 0) or 0 for p in puts)
        pcr = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else 0

        return {
            "ticker": ticker,
            "current_price": current_price,
            "timestamp": datetime.now().isoformat(),
            "stock_data": {
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
            },
            "historical_volatility": hv,
            "expirations_analyzed": expirations,
            "calls": calls,
            "puts": puts,
            "calls_count": len(calls),
            "puts_count": len(puts),
            "put_call_ratio": pcr,
            "status": "success",
            "source": "yahoo",
        }
    except Exception:
        logger.exception("Yahoo fetch failed for %s", ticker)
        return None


def _yahoo_row_to_dict(row, days_to_exp: int, expiration: str, opt_type: str) -> dict:
    return {
        "strike": _safe_float(row.get("strike", 0)),
        "bid": _safe_float(row.get("bid", 0)),
        "ask": _safe_float(row.get("ask", 0)),
        "lastPrice": _safe_float(row.get("lastPrice", 0)),
        "volume": _safe_int(row.get("volume", 0)),
        "openInterest": _safe_int(row.get("openInterest", 0)),
        "impliedVolatility": _safe_float(row.get("impliedVolatility", 0)),
        "daysToExpiry": days_to_exp,
        "expiration": expiration,
        "type": opt_type,
    }


# ── MEFF (Spanish Exchange) ──────────────────────────────────────────


def _get_meff_price(soup, ticker: str) -> float | None:
    """Extract underlying price from MEFF SPOT table, falling back to yfinance."""
    for caption in soup.find_all("caption"):
        if "SPOT" in caption.text.upper():
            table = caption.find_parent("table")
            if table:
                rows = table.find_all("tr")
                if len(rows) >= 2:
                    first_td = rows[1].find("td")
                    if first_td:
                        try:
                            return float(first_td.text.strip().replace(",", "."))
                        except ValueError:
                            pass
    info = (yf.Ticker(ticker).info or {})
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    return float(price) if price else None


def _parse_meff_tables(tables, current_price: float) -> tuple[list[dict], list[dict]]:
    """Parse MEFF tblOpciones rows using data-tipo attribute."""
    calls: list[dict] = []
    puts: list[dict] = []
    for table in tables:
        for row in table.find_all("tr"):
            tipo = row.get("data-tipo", "")
            m = _TIPO_RE.match(tipo)
            if not m:
                continue
            opt_type = "CALL" if m.group(1) == "C" else "PUT"
            expiry_dt = datetime.strptime(m.group(2), "%Y%m%d")
            days = max((expiry_dt - datetime.now()).days, 1)
            expiry_iso = expiry_dt.strftime("%Y-%m-%d")
            cols = [td.text.strip() for td in row.find_all("td")]
            opt = _parse_meff_row(cols, current_price, opt_type, expiry_iso, days)
            if opt:
                (calls if opt_type == "CALL" else puts).append(opt)
    return calls, puts


def _fetch_meff_soup(ticker: str) -> tuple | None:
    """Fetch and parse MEFF page. Returns (soup, [table]) or None."""
    base = ticker.replace(".MC", "")
    slug = _MEFF_SLUGS.get(base)
    if not slug:
        return None
    url = f"{_MEFF_BASE}{slug}"
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", id="tblOpciones")
    return (soup, [table]) if table else None


def _fetch_meff(ticker: str) -> dict | None:
    """Scrape options data for .MC tickers via MEFF website."""
    try:
        raw = _fetch_meff_soup(ticker)
        if not raw:
            return None
        soup, tables = raw

        current_price = _get_meff_price(soup, ticker)
        if not current_price:
            return None

        calls, puts = _parse_meff_tables(tables, current_price)
        all_options = calls + puts
        if not all_options:
            return None

        total_call_vol = sum(c.get("volume", 0) for c in calls)
        total_put_vol = sum(p.get("volume", 0) for p in puts)
        pcr = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else 0

        # Compute HV via yfinance history on the underlying (MEFF has no HV data)
        try:
            hv_history = yf.Ticker(ticker).history(period="60d")
            meff_hv = _compute_hv(hv_history)
        except Exception:
            meff_hv = None

        return {
            "ticker": ticker,
            "current_price": float(current_price),
            "timestamp": datetime.now().isoformat(),
            "stock_data": {},
            "historical_volatility": meff_hv,
            "expirations_analyzed": [],
            "calls": calls,
            "puts": puts,
            "calls_count": len(calls),
            "puts_count": len(puts),
            "put_call_ratio": pcr,
            "status": "success",
            "source": "meff",
        }
    except Exception:
        logger.exception("MEFF fetch failed for %s", ticker)
        return None


def _meff_cell(val: str) -> float:
    """Parse a MEFF cell: '-' or empty → 0.0."""
    if not val or val == "-":
        return 0.0
    try:
        return float(val.replace(",", "."))
    except ValueError:
        return 0.0


def _parse_meff_row(
    cols: list[str],
    underlying_price: float,
    opt_type: str,
    expiration: str,
    days_to_exp: int,
) -> dict | None:
    """Parse a MEFF tblOpciones row into an option dict.

    Column layout: Strike | BidOrd BidVol BidPrice | AskPrice AskVol AskOrd |
                   Last | Vol | Open | High | Low | Prev
    """
    if len(cols) < 13:
        return None
    strike = _meff_cell(cols[0])
    if not strike:
        return None
    bid = _meff_cell(cols[3])
    ask = _meff_cell(cols[4])
    last = _meff_cell(cols[7])
    volume = int(_meff_cell(cols[8]))
    mid = (bid + ask) / 2 if bid and ask else bid or ask or last
    iv = _solve_iv(underlying_price, strike, days_to_exp / 365.0, mid, opt_type) if mid > 0 else 0.0
    return {
        "strike": strike,
        "bid": bid,
        "ask": ask,
        "lastPrice": last,
        "volume": volume,
        "openInterest": 0,
        "impliedVolatility": iv,
        "daysToExpiry": days_to_exp,
        "expiration": expiration,
        "type": opt_type,
    }


def _solve_iv(
    spot: float,
    strike_price: float,
    time_to_exp: float,
    market_price: float,
    opt_type: str,
    risk_free: float = 0.053,
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float:
    """Newton-Raphson implied volatility solver."""
    if market_price <= 0 or time_to_exp <= 0:
        return 0.0

    sigma = 0.3
    for _ in range(max_iter):
        d1 = (
            math.log(spot / strike_price) + (risk_free + 0.5 * sigma**2) * time_to_exp
        ) / (sigma * math.sqrt(time_to_exp))
        d2 = d1 - sigma * math.sqrt(time_to_exp)

        if opt_type == "CALL":
            price = spot * _norm_cdf(d1) - strike_price * math.exp(-risk_free * time_to_exp) * _norm_cdf(d2)
        else:
            price = strike_price * math.exp(-risk_free * time_to_exp) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)

        vega = spot * _norm_pdf(d1) * math.sqrt(time_to_exp)
        if vega < 1e-10:
            break

        sigma -= (price - market_price) / vega
        if abs(price - market_price) < tol:
            break
        if sigma <= 0:
            sigma = 0.01

    return round(max(sigma, 0), 4)
