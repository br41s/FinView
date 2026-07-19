"""Premium spike detector: baseline learning + per-ticker aggregation.

The detector shipped with no tests. It compares each contract's premium to a
rolling per-(ticker, strike) EMA baseline, but a broad move spikes every strike
at once — IWDA.AS fired 17 alerts for one event. The output is now collapsed to
one alert per ticker; the baseline is still learned per contract.
"""

import pytest

from backend.services import premium_spike
from backend.services.premium_spike import (
    MIN_SAMPLES,
    _aggregate_ticker_spikes,
    detect_spikes,
)


@pytest.fixture(autouse=True)
def _clear_baselines():
    premium_spike._baselines.clear()
    yield
    premium_spike._baselines.clear()


def chain(calls=None, puts=None):
    def opt(strike, price):
        return {"strike": strike, "lastPrice": price, "expiration": "2026-12-18", "volume": 5}
    return {
        "calls": [opt(s, p) for s, p in (calls or [])],
        "puts": [opt(s, p) for s, p in (puts or [])],
    }


def _warm(user, ticker, strike, price, opt="calls", cycles=MIN_SAMPLES):
    """Feed a flat premium enough times that the baseline is armed."""
    for _ in range(cycles):
        detect_spikes(user, ticker, chain(**{opt: [(strike, price)]}))


# ── baseline learning ────────────────────────────────────────────────


def test_first_observation_never_alerts():
    assert detect_spikes(1, "AAPL", chain(calls=[(100, 5.0)])) == []


def test_no_alert_before_min_samples_even_on_a_jump():
    # Second observation is a 10x jump but the baseline isn't armed yet.
    detect_spikes(1, "AAPL", chain(calls=[(100, 1.0)]))
    assert detect_spikes(1, "AAPL", chain(calls=[(100, 10.0)])) == []


def test_a_real_spike_fires_once_the_baseline_is_armed():
    _warm(1, "AAPL", 100, 1.0)
    out = detect_spikes(1, "AAPL", chain(calls=[(100, 20.0)]))  # 20x baseline: fires clearly
    assert len(out) == 1
    assert out[0]["type"] == "PREMIUM_SPIKE"
    assert out[0]["severity"] == "HIGH"


def test_a_premium_within_the_multiple_does_not_fire():
    _warm(1, "AAPL", 100, 1.0)
    assert detect_spikes(1, "AAPL", chain(calls=[(100, 2.0)])) == []  # 2x is below the effective bar


def test_baselines_are_isolated_per_user():
    _warm(1, "AAPL", 100, 1.0)
    # User 2 has never seen this contract → first obs, no alert.
    assert detect_spikes(2, "AAPL", chain(calls=[(100, 99.0)])) == []


# ── per-ticker aggregation (the point of this change) ────────────────


def test_many_strikes_spiking_collapse_into_one_alert():
    strikes = [136, 137, 138, 139, 140, 141, 142, 143]
    for s in strikes:
        _warm(1, "IWDA.AS", s, 1.0, opt="puts")
    out = detect_spikes(1, "IWDA.AS", chain(puts=[(s, 20.0) for s in strikes]))
    assert len(out) == 1  # one event, not eight
    assert out[0]["message"].startswith(f"{len(strikes)} contratos con spike")


def test_the_aggregate_carries_no_contract_key_so_dedup_is_per_ticker():
    from backend.services.notification_service import _alert_key

    _warm(1, "IWDA.AS", 140, 1.0, opt="puts")
    out = detect_spikes(1, "IWDA.AS", chain(puts=[(140, 20.0)]))
    assert "_strike" not in out[0]
    # Dedup key collapses to (ticker, type) — one push per ticker per window.
    assert _alert_key(out[0]) == "IWDA.AS|PREMIUM_SPIKE"


def test_the_message_keeps_the_call_put_breakdown():
    result = _aggregate_ticker_spikes(
        "X",
        [
            {"option_type": "call", "strike": 1, "premium": 3, "pct": 150},
            {"option_type": "call", "strike": 2, "premium": 3, "pct": 160},
            {"option_type": "put", "strike": 3, "premium": 3, "pct": 200},
        ],
    )
    assert "2 calls" in result["message"]
    assert "1 put" in result["message"]
    assert "+150% a +200%" in result["message"]


def test_a_single_spike_reads_naturally():
    result = _aggregate_ticker_spikes("X", [{"option_type": "call", "strike": 1, "premium": 3, "pct": 150}])
    assert "1 contrato con spike" in result["message"]
    assert "1 call" in result["message"]
    assert "+150% sobre baseline" in result["message"]  # single value, not a range


def test_no_hits_aggregates_to_nothing():
    assert _aggregate_ticker_spikes("X", []) is None
