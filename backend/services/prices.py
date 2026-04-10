"""Daily stock price fetching and caching via Yahoo Finance."""

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.models import PriceCache

logger = logging.getLogger(__name__)

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
    "ES0105046009": "AENA.MC",    # AENA
    "ES0109067019": "AMS.MC",     # Amadeus
    "ES0113211835": "BBVA.MC",    # BBVA
    "ES0113900J37": "SAN.MC",     # Banco Santander
    "ES0130670112": "ELE.MC",     # Endesa
    "ES0144580Y14": "IBE.MC",     # Iberdrola
    "ES0148396007": "ITX.MC",     # Inditex
    "ES0173093024": "RED.MC",     # Redeia Corporacion
    "ES0173516115": "REP.MC",     # Repsol
    # Germany
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
    "GB00BZ3CNK81": "TRMD.OL",  # TORM
    # US
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
    "BRPETRACNOR9": "PBR",        # Petrobras ADR
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

    for ticker, price_val in prices.items():
        isin = ticker_to_isin.get(ticker)
        if not isin:
            continue
        price_dec = Decimal(str(round(price_val, 6)))

        # Upsert cache
        existing = (
            db.query(PriceCache)
            .filter(PriceCache.isin == isin, PriceCache.fetched_date == today)
            .first()
        )
        if existing:
            existing.price = price_dec
            existing.yahoo_ticker = ticker
        else:
            db.add(PriceCache(
                isin=isin,
                yahoo_ticker=ticker,
                price=price_dec,
                currency="EUR",
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

        if len(tickers) == 1:
            # Single ticker: data columns are just price columns
            last_close = data["Close"].dropna().iloc[-1] if not data["Close"].dropna().empty else None
            if last_close is not None:
                result[tickers[0]] = float(last_close)
        else:
            # Multiple tickers: MultiIndex columns (price_type, ticker)
            close_data = data["Close"]
            for ticker in tickers:
                if ticker in close_data.columns:
                    series = close_data[ticker].dropna()
                    if not series.empty:
                        result[ticker] = float(series.iloc[-1])
    except Exception:
        logger.exception("Error fetching Yahoo Finance prices")

    return result
