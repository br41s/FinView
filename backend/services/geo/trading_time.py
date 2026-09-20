"""Trading-time arithmetic for the intraday checkpoint horizons.

The +1h and +6h checkpoints are defined in *trading* time on the US regular
session (09:30–16:00 America/New_York, Monday–Friday, DST-aware). A signal born
at 03:00 UTC on a Sunday used to get a +1h checkpoint at 04:00 UTC Sunday,
which compared Friday's close with itself: 80% of the week is outside the
session, so 80% of intraday checkpoints measured nothing. The basket mixes
futures that trade ~23h with equities and ETFs that do not; the equity session
is the common denominator, and a futures move outside it is simply measured at
the next session's bar.

Exchange holidays are not modelled: a target that lands on one reads the prior
close, moves nothing, and scores NEUTRAL — which is the truth.
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)


def _session(day: datetime) -> tuple[datetime, datetime]:
    open_ = datetime.combine(day.date(), SESSION_OPEN, tzinfo=_NY)
    close = datetime.combine(day.date(), SESSION_CLOSE, tzinfo=_NY)
    return open_, close


def _next_session_open(moment: datetime) -> datetime:
    day = moment
    while True:
        day = day + timedelta(days=1)
        if day.weekday() < 5:
            return _session(day)[0]


def add_trading_time(start: datetime, delta: timedelta) -> datetime:
    """``start`` plus ``delta`` of session time, in UTC.

    Time before a session's open or after its close does not count; weekends
    do not count. A start inside a session consumes the rest of that session
    first.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    moment = start.astimezone(_NY)
    remaining = delta
    while True:
        if moment.weekday() < 5:
            open_, close = _session(moment)
            if moment < open_:
                moment = open_
            if moment < close:
                available = close - moment
                if remaining <= available:
                    return (moment + remaining).astimezone(timezone.utc)
                remaining -= available
        moment = _next_session_open(moment)

