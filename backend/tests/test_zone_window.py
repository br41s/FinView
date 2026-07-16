"""Tests for the zone-detection lookback window.

The download window (20y) and the pivot-detection window (10y) are deliberately
different: the extra history exists so the chart's MAX scope has decades to
render, while zones should only be built from levels that still act as S/R.
"""

import pandas as pd

from backend.services.zonas_clave_analyzer import _MIN_BARS, zone_window


def frame(years: float, bars_per_year: int = 252) -> pd.DataFrame:
    n = max(int(years * bars_per_year), 1)
    idx = pd.date_range(end="2026-07-16", periods=n, freq="B")
    return pd.DataFrame({"Close": range(n), "Volume": range(n)}, index=idx)


def test_trims_twenty_years_down_to_ten():
    df = frame(20)
    out = zone_window(df, years=10)
    assert len(out) < len(df)
    # Business days over 10y ≈ 2609; allow slack for the calendar.
    assert 2400 < len(out) < 2700
    # Trims from the old end — the most recent bar must survive.
    assert out.index.max() == df.index.max()


def test_keeps_everything_when_history_is_shorter_than_the_window():
    df = frame(3)
    out = zone_window(df, years=10)
    assert len(out) == len(df)


def test_recent_ipo_is_not_trimmed_to_nothing():
    df = frame(0.5)
    out = zone_window(df, years=10)
    assert len(out) == len(df)


def test_falls_back_to_the_full_frame_rather_than_starve_pivot_detection():
    """A thinly traded ticker can span 20 years with few bars: trimming to the
    last 10 leaves fewer than pivot detection needs. Stale levels beat none."""
    sparse = pd.DataFrame(
        {"Close": range(30), "Volume": range(30)},
        index=pd.date_range(end="2026-07-16", periods=30, freq="200D"),
    )
    trimmed_count = len(sparse[sparse.index >= sparse.index.max() - pd.DateOffset(years=10)])
    assert trimmed_count < _MIN_BARS  # precondition: the trim really does starve it
    assert len(zone_window(sparse, years=10)) == 30


def test_non_datetime_index_degrades_to_current_behaviour():
    """An unexpected index shape must not silently drop every bar."""
    df = pd.DataFrame({"Close": range(300), "Volume": range(300)})
    out = zone_window(df, years=10)
    assert len(out) == 300


def test_empty_or_none_frames_pass_through():
    assert zone_window(None) is None
    empty = pd.DataFrame()
    assert zone_window(empty).empty


def test_zero_years_disables_trimming():
    df = frame(20)
    assert len(zone_window(df, years=0)) == len(df)


def test_median_volume_is_measured_over_the_trimmed_window():
    """Zone strength scores volume against the median. Measuring it over 20y when
    zones only span 10y would score today's zones against a decade-old volume
    regime — the exact skew the split was meant to remove."""
    idx = pd.date_range(end="2026-07-16", periods=20 * 252, freq="B")
    # Old half traded thin, recent half traded heavy.
    volumes = [10] * (len(idx) // 2) + [1000] * (len(idx) - len(idx) // 2)
    df = pd.DataFrame({"Close": range(len(idx)), "Volume": volumes}, index=idx)
    assert df["Volume"].median() < 1000  # whole-frame median is dragged down
    assert zone_window(df, years=10)["Volume"].median() == 1000


def test_trimmed_window_still_clears_the_pivot_minimum():
    out = zone_window(frame(20), years=10)
    assert len(out) >= _MIN_BARS
