"""Session-time arithmetic: 09:30–16:00 America/New_York, DST-aware, no weekends."""

from datetime import datetime, timedelta, timezone

from backend.services.geo.trading_time import add_trading_time

UTC = timezone.utc


def test_inside_a_session_is_plain_addition():
    # Mon 2026-09-14 10:00 ET = 14:00 UTC (EDT)
    start = datetime(2026, 9, 14, 14, 0, tzinfo=UTC)
    assert add_trading_time(start, timedelta(hours=1)) == datetime(2026, 9, 14, 15, 0, tzinfo=UTC)


def test_the_close_rolls_into_the_next_session():
    # Mon 15:30 ET + 1h → 30 min today, 30 min Tue from 09:30 → Tue 10:00 ET = 14:00 UTC
    start = datetime(2026, 9, 14, 19, 30, tzinfo=UTC)
    assert add_trading_time(start, timedelta(hours=1)) == datetime(2026, 9, 15, 14, 0, tzinfo=UTC)


def test_a_weekend_start_waits_for_monday():
    start = datetime(2026, 9, 20, 3, 0, tzinfo=UTC)  # Sunday
    assert add_trading_time(start, timedelta(hours=1)) == datetime(2026, 9, 21, 14, 30, tzinfo=UTC)


def test_six_hours_spans_a_session_boundary():
    # Fri 14:00 ET + 6h → 2h Fri, 4h Mon from 09:30 → Mon 13:30 ET = 17:30 UTC
    start = datetime(2026, 9, 18, 18, 0, tzinfo=UTC)
    assert add_trading_time(start, timedelta(hours=6)) == datetime(2026, 9, 21, 17, 30, tzinfo=UTC)


def test_dst_is_honoured():
    # Mon 2026-12-14 10:00 ET is 15:00 UTC (EST)
    start = datetime(2026, 12, 14, 15, 0, tzinfo=UTC)
    assert add_trading_time(start, timedelta(hours=1)) == datetime(2026, 12, 14, 16, 0, tzinfo=UTC)


def test_naive_input_is_utc():
    assert add_trading_time(datetime(2026, 9, 14, 14, 0), timedelta(hours=1)) == datetime(
        2026, 9, 14, 15, 0, tzinfo=UTC
    )

