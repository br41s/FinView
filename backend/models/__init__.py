"""SQLAlchemy models for FinView, one module per domain.

Everything is re-exported here so `from backend.models import X` keeps working and
`Base.metadata.create_all` sees every table.
"""

from .base import (
    Base,
    Broker,
    TransactionType,
)
from .auth import (
    SubscriptionTier,
    SubscriptionStatus,
    User,
    Account,
    BrokerConnection,
)
from .ledger import (
    Transaction,
    TaxLot,
    TaxResult,
    CrossBrokerLot,
    FIFOAdjustment,
    ImportRecord,
    OptionAssignmentRecord,
    PortfolioHolding,
    DataIssue,
)
from .market_data import (
    PriceCache,
    TickerMap,
    SplitHistoryCache,
    ExchangeRate,
    FredRate,
)
from .options import (
    AlertSeverity,
    FollowedInstrument,
    OptionsSnapshot,
    OptionsAlert,
    OptionsAlertNotification,
    UnusualActivity,
    OptionsAgentLog,
    OptionsHiddenPortfolioTicker,
)
from .zonas_clave import (
    ZonasClaveWatchlistItem,
    ZonasClaveAnalysis,
    TechnicalSignal,
)
from .backtest import (
    BacktestOutcome,
    BacktestSignal,
)
from .geo import (
    GeoDisplayCategory,
    GeoDirection,
    GeoSignalStatus,
    GeoHorizon,
    GeoSignal,
    GeoSignalTicker,
    GeoCheckpoint,
    GeoRuleStat,
    GeoRegionSample,
    GeoFlightSample,
    GeoGenerativeAnswer,
    GeoCycleRun,
)
from .alt_investments import (
    AltInvestmentType,
    AltInvestmentStatus,
    AltInvestment,
    AltInvestmentCatalog,
)
from .fiscal import (
    FiscalProfile,
    ManualSavingsIncome,
)
from .segments import (
    AiMentionCheck,
    AiMentionReport,
    ListingProfile,
    SegmentCheck,
    SegmentReport,
)

__all__ = [
    "Base",
    "Broker",
    "TransactionType",
    "SubscriptionTier",
    "SubscriptionStatus",
    "User",
    "Account",
    "BrokerConnection",
    "Transaction",
    "TaxLot",
    "TaxResult",
    "CrossBrokerLot",
    "FIFOAdjustment",
    "ImportRecord",
    "OptionAssignmentRecord",
    "PortfolioHolding",
    "DataIssue",
    "PriceCache",
    "TickerMap",
    "SplitHistoryCache",
    "ExchangeRate",
    "FredRate",
    "AlertSeverity",
    "FollowedInstrument",
    "OptionsSnapshot",
    "OptionsAlert",
    "OptionsAlertNotification",
    "UnusualActivity",
    "OptionsAgentLog",
    "OptionsHiddenPortfolioTicker",
    "ZonasClaveWatchlistItem",
    "ZonasClaveAnalysis",
    "TechnicalSignal",
    "BacktestOutcome",
    "BacktestSignal",
    "GeoDisplayCategory",
    "GeoDirection",
    "GeoSignalStatus",
    "GeoHorizon",
    "GeoSignal",
    "GeoSignalTicker",
    "GeoCheckpoint",
    "GeoRuleStat",
    "GeoRegionSample",
    "GeoFlightSample",
    "GeoGenerativeAnswer",
    "GeoCycleRun",
    "AltInvestmentType",
    "AltInvestmentStatus",
    "AltInvestment",
    "AltInvestmentCatalog",
    "FiscalProfile",
    "ManualSavingsIncome",
    "AiMentionCheck",
    "AiMentionReport",
    "ListingProfile",
    "SegmentCheck",
    "SegmentReport",
]
