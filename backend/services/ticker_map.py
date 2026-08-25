"""ISIN → Yahoo Finance ticker resolution.

Two sources, in one place so every caller sees the same answer.

`CURATED` is hand-maintained: securities Yahoo does not resolve from their ISIN,
plus the corporate actions where several ISINs share one ticker (AENA pre- and
post-split, for example) — a fact a symbol lookup cannot discover.

`ticker_map` rows are what the app has learned since. Before this existed, a
ticker the data supervisor resolved via yfinance went into a DataIssue
description and nowhere else: nothing read it back, so the price stayed "—", the
same lookup ran again on the next import, and split detection — which walks the
curated map — never saw the security at all.

Precedence is `manual > CURATED > yfinance`. A learned lookup must not quietly
override curated knowledge about a corporate action; a human correction must
override both, or an ISIN we curated wrongly could never be fixed without a
deploy.
"""

import logging

from sqlalchemy.orm import Session

from backend.models import TickerMap

logger = logging.getLogger(__name__)

MANUAL = "manual"
YFINANCE = "yfinance"


CURATED: dict[str, str] = {
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


def effective_map(db: Session) -> dict[str, str]:
    """Every ISIN→ticker this installation knows, curated and learned merged.

    One query. Callers that need to look at more than a couple of ISINs — split
    detection, the portfolio ticker merge — should use this rather than calling
    `resolve` in a loop.
    """
    rows = db.query(TickerMap.isin, TickerMap.yahoo_ticker, TickerMap.source).all()
    learned = {r.isin: r.yahoo_ticker for r in rows if r.source != MANUAL}
    manual = {r.isin: r.yahoo_ticker for r in rows if r.source == MANUAL}
    return {**learned, **CURATED, **manual}


def resolve(db: Session, isin: str) -> str | None:
    """The ticker for one ISIN, or None when nothing knows it."""
    row = (
        db.query(TickerMap.yahoo_ticker, TickerMap.source)
        .filter(TickerMap.isin == isin)
        .first()
    )
    if row and row.source == MANUAL:
        return row.yahoo_ticker
    if isin in CURATED:
        return CURATED[isin]
    return row.yahoo_ticker if row else None


def remember(
    db: Session,
    isin: str,
    ticker: str,
    *,
    source: str = YFINANCE,
    name: str | None = None,
) -> TickerMap:
    """Persist a resolution so the next import does not look it up again.

    Does not commit — the caller owns the transaction, so a resolution lands or
    rolls back with whatever else it was part of.
    """
    row = db.query(TickerMap).filter(TickerMap.isin == isin).first()
    if row is None:
        row = TickerMap(isin=isin, yahoo_ticker=ticker, source=source, name=name)
        db.add(row)
        logger.info("Learned ticker %s for ISIN %s (%s)", ticker, isin, source)
        return row

    # A manual correction is not overwritten by a later automatic lookup.
    if row.source == MANUAL and source != MANUAL:
        return row

    if row.yahoo_ticker != ticker:
        logger.info(
            "Ticker for ISIN %s changed %s → %s (%s)", isin, row.yahoo_ticker, ticker, source
        )
    row.yahoo_ticker = ticker
    row.source = source
    if name:
        row.name = name
    return row
