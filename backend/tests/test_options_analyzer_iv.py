"""IV sanitisation in the options analyzer.

Regression origin: the options cycle had been dying on every run since June.
yfinance/MEFF return implied volatilities like 1790.38 (179,038%) for dead
near-expiry contracts; averaging them produced avg_call_iv in the tens of
millions, which overflowed OptionsSnapshot's Numeric(10, 4) and blew up the
whole cycle's db.commit(). Nothing was persisted — no snapshots, no alerts, no
cycle log — and the UI showed an empty Monitor with no error anywhere.

The numbers below are the real ones from the failing prod insert.
"""

from backend.services.options_analyzer import MAX_USABLE_IV, _usable_ivs, analyze_ticker


def opt(iv, strike=100.0, volume=0, oi=0):
    return {
        "impliedVolatility": iv,
        "strike": strike,
        "volume": volume,
        "openInterest": oi,
        "expiration": "2026-09-18",
    }


def test_normal_ivs_are_converted_to_percent():
    assert _usable_ivs([opt(0.3), opt(0.45)]) == [30.0, 45.0]


def test_the_real_prod_garbage_is_dropped():
    """1790.3792 is a verbatim value from the failing insert: 179,038% IV."""
    assert _usable_ivs([opt(1790.3792)]) == []


def test_a_dead_contract_does_not_drag_the_average():
    """One bogus reading among good ones must not vote at all — dropped, not
    clamped, or the mean still gets pulled to the ceiling."""
    ivs = _usable_ivs([opt(0.30), opt(1790.3792), opt(0.40)])
    assert ivs == [30.0, 40.0]
    assert sum(ivs) / len(ivs) == 35.0


def test_ceiling_boundary():
    assert _usable_ivs([opt(MAX_USABLE_IV)]) == [MAX_USABLE_IV * 100]
    assert _usable_ivs([opt(MAX_USABLE_IV + 0.001)]) == []


def test_zero_and_negative_ivs_are_dropped():
    assert _usable_ivs([opt(0.0), opt(-0.5)]) == []


def test_missing_or_non_numeric_ivs_are_dropped():
    assert _usable_ivs([{"strike": 1.0}, opt(None), opt("0.3"), opt(True)]) == []


def test_avg_iv_stays_inside_the_db_column_with_garbage_input():
    """Numeric(10, 4) caps at 999999.9999. This is the assertion that would have
    caught the outage."""
    calls = [opt(0.3), opt(1790.3792), opt(3860.0)]
    puts = [opt(0.35), opt(38600.0)]
    result = analyze_ticker({"ticker": "TEF.MC", "calls": calls, "puts": puts, "current_price": 3.65})
    s = result["summary"]
    assert abs(s["avg_call_iv"]) < 1_000_000
    assert abs(s["avg_put_iv"]) < 1_000_000
    assert abs(s["iv_skew"]) < 1_000_000
    # And the surviving values are the real ones, not clamped junk.
    assert s["avg_call_iv"] == 30.0
    assert s["avg_put_iv"] == 35.0


def test_a_chain_of_pure_garbage_yields_zero_not_an_explosion():
    result = analyze_ticker(
        {"ticker": "X", "calls": [opt(9999.0)], "puts": [opt(9999.0)], "current_price": 10.0}
    )
    s = result["summary"]
    assert s["avg_call_iv"] == 0
    assert s["avg_put_iv"] == 0
    assert s["iv_skew"] == 0


def test_empty_chain_is_still_handled():
    result = analyze_ticker({"ticker": "X", "calls": [], "puts": [], "current_price": 10.0})
    assert result["summary"]["avg_call_iv"] == 0
