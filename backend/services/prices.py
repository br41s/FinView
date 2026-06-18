"""Daily stock price fetching and caching via Yahoo Finance."""

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.models import PriceCache

logger = logging.getLogger(__name__)

# Exchange suffix → trading currency
_EXCHANGE_CURRENCY: dict[str, str] = {
    ".MC": "EUR", ".DE": "EUR", ".PA": "EUR", ".AS": "EUR",
    ".LS": "EUR", ".VI": "EUR",
    ".L": "GBP",
    ".OL": "NOK",
    ".CO": "DKK",
    ".SA": "BRL",
}


def _ticker_currency(ticker: str) -> str:
    """Determine the trading currency from the Yahoo Finance ticker suffix."""
    for suffix, currency in _EXCHANGE_CURRENCY.items():
        if ticker.endswith(suffix):
            return currency
    return "USD"  # US stocks have no suffix

# ISIN → Yahoo Finance ticker mapping for stocks that don't auto-resolve
_ISIN_TICKER_MAP: dict[str, str] = {
    # Spain
    "ES0132105018": "ACX.MC",     # Acerinox
    "ES0125220311": "ANA.MC",     # Acciona
    "ES0105027009": "LOG.MC",     # Logista
    "ES0105223004": "GEST.MC",    # Gestamp
    "ES0116870314": "NTGY.MC",    # Naturgy
    "ES0113860A34": "SAB.MC",     # Banco Sabadell
    "ES0112501012": "EBRO.MC",    # Ebro Foods
    "ES0130960018": "ENG.MC",     # Enagas
    "ES0105546008": "LDA.MC",     # Linea Directa
    "ES0180907000": "UNI.MC",     # Unicaja
    "ES0112320009": "CNTE.MC",    # Catenon
    "ES0122060314": "FCC.MC",     # FCC
    "ES0139140174": "COL.MC",     # Inmobiliaria Colonial
    "ES0178430E18": "TEF.MC",     # Telefonica
    "ES0113679I37": "BKT.MC",     # Bankinter
    "ES0105046009": "AENA.MC",    # AENA (pre-split, 1:10 hasta 2025)
    "ES0105046017": "AENA.MC",    # AENA (post-split 2025)
    "ES0109067019": "AMS.MC",     # Amadeus
    "ES0113211835": "BBVA.MC",    # BBVA
    "ES0113900J37": "SAN.MC",     # Banco Santander
    "ES0130670112": "ELE.MC",     # Endesa
    "ES0144580Y14": "IBE.MC",     # Iberdrola
    "ES0148396007": "ITX.MC",     # Inditex
    "ES0173093024": "RED.MC",     # Redeia Corporacion
    "ES0173516115": "REP.MC",     # Repsol
    "ES0105684007": "IFLEX.MC",   # Iflex (Industria de Diseno)
    "ES0169350016": "PVA.MC",     # Pescanova
    # Germany
    "DE000PAG9113": "P911.DE",    # Porsche AG
    "DE0008404005": "ALV.DE",     # Allianz
    "DE0007100000": "MBG.DE",     # Mercedes-Benz
    "DE0007236101": "SIE.DE",     # Siemens
    "DE000BASF111": "BAS.DE",     # BASF
    "DE0005190003": "BMW.DE",     # BMW
    "DE000BAY0017": "BAYN.DE",    # Bayer
    "DE0005552004": "DHL.DE",     # DHL Group
    "DE000ENAG999": "EOAN.DE",    # E.ON
    "DE0006048408": "HEN.DE",     # Henkel
    "DE000DTR0CK8": "DTG.DE",    # Daimler Truck
    # France
    "FR0000120628": "CS.PA",      # AXA
    "FR0000120172": "CA.PA",      # Carrefour
    "FR0000133308": "ORA.PA",     # Orange
    "FR0000125486": "DG.PA",      # VINCI
    "FR0013447729": "VRLA.PA",    # Verallia
    "FR0010208488": "ENGI.PA",    # Engie
    # UK
    "GB0006731235": "ABF.L",      # Associated British Foods
    "GB00BPQY8M80": "AV.L",      # Aviva
    "GB0030913577": "BT-A.L",    # BT Group
    "GB0031743007": "BRBY.L",    # Burberry
    "GB0002374006": "DGE.L",     # Diageo
    "GB0005603997": "LGEN.L",    # Legal & General
    "GB00BDR05C01": "NG.L",      # National Grid
    "GB00BH4HKS39": "VOD.L",    # Vodafone
    "GB00B1FH8J72": "SVT.L",    # Severn Trent
    "GB00B39J2M42": "UU.L",     # United Utilities
    "GB00BZ3CNK81": "TORM.CO",   # TORM (Copenhagen)
    # Singapore
    "SG1M31001969": "U11.SI",     # UOB (United Overseas Bank)
    # US
    "US62914V1061": "NIO",        # NIO Inc ADR
    "US91332U1016": "U",          # Unity Software
    "US88579Y1010": "MMM",        # 3M
    "US7134481081": "PEP",        # PepsiCo
    "US5007541064": "KHC",        # Kraft Heinz
    "US6092071058": "MDLZ",       # Mondelez
    "US3703341046": "GIS",        # General Mills
    "US4581401001": "INTC",       # Intel
    "US4404521001": "HRL",        # Hormel Foods
    "US9024941034": "TSN",        # Tyson Foods
    "US9113121068": "UPS",        # UPS
    "US50155Q1004": "KD",         # Kyndryl
    "US19260Q1076": "COIN",       # Coinbase
    "US66987V1098": "NVS",        # Novartis ADR
    "US00206R1023": "T",          # AT&T
    "US0394831020": "ADM",        # Archer Daniels Midland
    "US45841N1072": "IBKR",       # Interactive Brokers
    "US49177J1025": "KVUE",       # Kenvue
    "US5949181045": "MSFT",       # Microsoft
    "US92343V1044": "VZ",         # Verizon
    # Netherlands
    "NL0010773842": "NN.AS",      # NN Group
    "NL0000379121": "RAND.AS",    # Randstad
    # Brazil
    "BRPETRACNOR9": "PETR3.SA",   # Petrobras ORD (Bovespa)
    # Portugal
    "PTREL0AM0008": "EDPR.LS",    # Redes Energeticas
    # Austria
    "AT0000831706": "WIE.VI",     # Wienerberger
    # Canada
    "CA22717L1013": "CRON",       # Cronos
    # ETFs
    "IE00B4L5Y983": "IWDA.AS",   # iShares Core MSCI World
    "IE00BYWQWR46": "ESPO.L",    # VanEck Video Gaming
    "IE00BMW3QX54": "ROBO.L",    # L&G ROBO
}


def _resolve_ticker(isin: str, db: Session) -> str | None:
    """Resolve ISIN to Yahoo Finance ticker using mapping or DB cache."""
    if isin in _ISIN_TICKER_MAP:
        return _ISIN_TICKER_MAP[isin]

    cached = (
        db.query(PriceCache.yahoo_ticker)
        .filter(PriceCache.isin == isin, PriceCache.yahoo_ticker.isnot(None))
        .first()
    )
    return cached[0] if cached else None


def get_cached_prices(db: Session, isins: list[str]) -> dict[str, Decimal]:
    """Get today's cached prices. Returns dict[isin, price]."""
    today = date.today()
    rows = (
        db.query(PriceCache.isin, PriceCache.price)
        .filter(PriceCache.isin.in_(isins), PriceCache.fetched_date == today)
        .all()
    )
    return {r.isin: r.price for r in rows}


def fetch_and_cache_prices(
    db: Session, isins: list[str],
) -> dict[str, Decimal]:
    """Fetch current prices for ISINs, cache them, return dict[isin, price].

    Only fetches ISINs not already cached for today.
    """
    today = date.today()
    cached = get_cached_prices(db, isins)
    missing = [isin for isin in isins if isin not in cached]

    if not missing:
        return cached

    # Resolve tickers for missing ISINs
    ticker_to_isin: dict[str, str] = {}
    for isin in missing:
        ticker = _resolve_ticker(isin, db)
        if ticker:
            ticker_to_isin[ticker] = isin
        else:
            logger.warning("No Yahoo ticker for ISIN %s", isin)

    if not ticker_to_isin:
        return cached

    # Batch fetch via yfinance
    prices = _fetch_yahoo_prices(list(ticker_to_isin.keys()))

    # Determine which currencies need conversion
    non_eur_currencies: set[str] = set()
    ticker_currencies: dict[str, str] = {}
    for ticker in ticker_to_isin:
        ccy = _ticker_currency(ticker)
        ticker_currencies[ticker] = ccy
        if ccy != "EUR":
            non_eur_currencies.add(ccy)

    # Fetch forex rates for non-EUR currencies (e.g. EURUSD=X → 1 EUR = X USD)
    fx_rates: dict[str, float] = {}
    if non_eur_currencies:
        forex_tickers = [f"EUR{ccy}=X" for ccy in non_eur_currencies]
        fx_raw = _fetch_yahoo_prices(forex_tickers)
        for ft, rate in fx_raw.items():
            ccy = ft[3:6]  # e.g. "EURUSD=X" → "USD"
            fx_rates[ccy] = rate

    for ticker, price_val in prices.items():
        isin = ticker_to_isin.get(ticker)
        if not isin:
            continue

        # London Stock Exchange quotes in GBX (pence) — convert to GBP
        if ticker.endswith(".L"):
            price_val = price_val / 100.0

        # Track original currency and price
        ccy = ticker_currencies.get(ticker, "EUR")
        orig_price = Decimal(str(round(price_val, 6)))
        rate = Decimal(str(round(fx_rates[ccy], 6))) if ccy in fx_rates else None

        # Convert to EUR if needed
        if ccy != "EUR" and ccy in fx_rates:
            price_eur = price_val / fx_rates[ccy]
        elif ccy != "EUR":
            logger.warning("No FX rate for %s, skipping %s", ccy, ticker)
            continue
        else:
            price_eur = price_val

        price_dec = Decimal(str(round(price_eur, 6)))

        # Upsert cache
        existing = (
            db.query(PriceCache)
            .filter(PriceCache.isin == isin, PriceCache.fetched_date == today)
            .first()
        )
        if existing:
            existing.price = price_dec
            existing.yahoo_ticker = ticker
            existing.original_currency = ccy
            existing.original_price = orig_price
            existing.fx_rate = rate
        else:
            db.add(PriceCache(
                isin=isin,
                yahoo_ticker=ticker,
                price=price_dec,
                currency="EUR",
                original_currency=ccy,
                original_price=orig_price,
                fx_rate=rate,
                fetched_date=today,
            ))
        cached[isin] = price_dec

    db.commit()
    return cached


def _fetch_yahoo_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch latest prices from Yahoo Finance. Returns dict[ticker, price]."""
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed")
        return {}

    result: dict[str, float] = {}
    try:
        data = yf.download(
            tickers,
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if data.empty:
            return result

        # yfinance ≥0.2.x always returns MultiIndex columns (price, ticker)
        close_data = data["Close"]
        if isinstance(close_data, __import__("pandas").Series):
            # Fallback: single ticker returns a Series
            vals = close_data.dropna()
            if not vals.empty:
                result[tickers[0]] = float(vals.iloc[-1])
        elif isinstance(close_data, __import__("pandas").DataFrame):
            if close_data.columns.nlevels > 1:
                close_data = close_data.droplevel(0, axis=1)
            for ticker in tickers:
                if ticker in close_data.columns:
                    series = close_data[ticker].dropna()
                    if not series.empty:
                        result[ticker] = float(series.iloc[-1])
                elif len(tickers) == 1 and len(close_data.columns) == 1:
                    series = close_data.iloc[:, 0].dropna()
                    if not series.empty:
                        result[tickers[0]] = float(series.iloc[-1])
    except Exception:
        logger.exception("Error fetching Yahoo Finance prices")

    return result


def fetch_ticker_prices(tickers: list[str]) -> dict[str, float]:
    """Public: latest price per ticker symbol (geo-intel quote enrichment).

    Returns dict[ticker, price]; symbols absent from the result are unresolvable
    (e.g. some futures / foreign listings) and should be flagged, not dropped.
    """
    if not tickers:
        return {}
    return _fetch_yahoo_prices(list(dict.fromkeys(tickers)))


def get_currency_info(db: Session, isins: list[str]) -> dict[str, dict]:
    """Get currency info for ISINs from today's cache.

    Returns dict[isin, {currency, original_price, fx_rate}].
    Falls back to _ISIN_TICKER_MAP when cache has no original_currency.
    """
    today = date.today()
    rows = (
        db.query(
            PriceCache.isin,
            PriceCache.original_currency,
            PriceCache.original_price,
            PriceCache.fx_rate,
            PriceCache.yahoo_ticker,
        )
        .filter(PriceCache.isin.in_(isins), PriceCache.fetched_date == today)
        .all()
    )
    result: dict[str, dict] = {}
    for r in rows:
        ccy = r.original_currency
        if not ccy and r.yahoo_ticker:
            ccy = _ticker_currency(r.yahoo_ticker)
        result[r.isin] = {
            "currency": ccy or "EUR",
            "original_price": str(r.original_price) if r.original_price else None,
            "fx_rate": str(r.fx_rate) if r.fx_rate else None,
        }

    # For ISINs not in today's cache, derive from ticker map
    for isin in isins:
        if isin not in result:
            ticker = _ISIN_TICKER_MAP.get(isin)
            ccy = _ticker_currency(ticker) if ticker else "EUR"
            result[isin] = {"currency": ccy, "original_price": None, "fx_rate": None}

    return result
