"""Premium spike detector: each contract against its own previous close.

It used to learn an in-memory EMA per (ticker, type, strike) with no expiration
in the key. A chain carries several expiries, so one cycle mixed near and far
premiums of the same strike and a far expiry's time value read as a +150%
"spike" — and prod rebuilt that baseline on every cold start. The detector is
now stateless: the source publishes each contract's previous close.
"""

from backend.services.premium_spike import (
    MIN_PREMIUM,
    _aggregate_ticker_spikes,
    detect_spikes,
)


def opt(strike, price, prev, volume=5, expiration="2026-12-18"):
    return {
        "strike": strike,
        "lastPrice": price,
        "prevClose": prev,
        "volume": volume,
        "expiration": expiration,
    }


def chain(calls=(), puts=()):
    return {"calls": list(calls), "puts": list(puts)}


# ── the rule ─────────────────────────────────────────────────────────


def test_a_premium_at_the_multiple_of_its_previous_close_fires():
    out = detect_spikes("AAPL", chain(calls=[opt(100, 2.5, 1.0)]))
    assert len(out) == 1
    assert out[0]["type"] == "PREMIUM_SPIKE"
    assert out[0]["severity"] == "HIGH"
    assert "+150%" in out[0]["message"]


def test_a_premium_below_the_multiple_does_not_fire():
    assert detect_spikes("AAPL", chain(calls=[opt(100, 2.4, 1.0)])) == []


def test_the_first_cycle_after_a_cold_start_already_judges_correctly():
    """No warm-up: the same chain gives the same answer on any instance."""
    c = chain(calls=[opt(100, 3.0, 1.0)])
    assert detect_spikes("AAPL", c) == detect_spikes("AAPL", c)
    assert len(detect_spikes("AAPL", c)) == 1


def test_expiries_of_one_strike_are_never_compared_with_each_other():
    """The old failure: near 1.0, mid 2.0, far 6.0 at K=100 read as a spike."""
    c = chain(puts=[
        opt(100, 1.0, 1.0, expiration="2026-10-16"),
        opt(100, 2.0, 2.0, expiration="2026-11-20"),
        opt(100, 6.0, 6.0, expiration="2026-12-18"),
    ])
    assert detect_spikes("DGE.L", c) == []


def test_a_contract_that_did_not_trade_this_session_is_skipped():
    assert detect_spikes("AAPL", chain(calls=[opt(100, 5.0, 1.0, volume=0)])) == []


def test_a_previous_close_below_the_minimum_is_skipped():
    tiny = MIN_PREMIUM / 2
    assert detect_spikes("AAPL", chain(calls=[opt(100, tiny * 10, tiny)])) == []


def test_eurex_settlements_carry_no_previous_close_and_never_spike():
    settlement = {"strike": 100, "lastPrice": 9.0, "volume": 0, "expiration": "2027-12-17"}
    assert detect_spikes("DGE.L", chain(calls=[settlement])) == []


# ── per-ticker aggregation ───────────────────────────────────────────


def test_many_strikes_spiking_collapse_into_one_alert():
    strikes = [136, 137, 138, 139, 140, 141, 142, 143]
    out = detect_spikes("IWDA.AS", chain(puts=[opt(s, 20.0, 1.0) for s in strikes]))
    assert len(out) == 1  # one event, not eight
    assert out[0]["message"].startswith(f"{len(strikes)} contratos con spike")


def test_the_aggregate_carries_no_contract_key_so_dedup_is_per_ticker():
    from backend.services.notification_service import _alert_key

    out = detect_spikes("IWDA.AS", chain(puts=[opt(140, 20.0, 1.0)]))
    assert "_strike" not in out[0]
    # Dedup key collapses to (ticker, type) — one push per ticker per window.
    assert _alert_key(out[0]) == "IWDA.AS|PREMIUM_SPIKE"


def test_the_message_keeps_the_call_put_breakdown():
    result = _aggregate_ticker_spikes(
        "X",
        [
            {"option_type": "call", "strike": 1, "pct": 150},
            {"option_type": "call", "strike": 2, "pct": 160},
            {"option_type": "put", "strike": 3, "pct": 200},
        ],
    )
    assert "2 calls" in result["message"]
    assert "1 put" in result["message"]
    assert "+150% a +200%" in result["message"]


def test_a_single_spike_reads_naturally():
    result = _aggregate_ticker_spikes("X", [{"option_type": "call", "strike": 1, "pct": 150}])
    assert "1 contrato con spike" in result["message"]
    assert "1 call" in result["message"]
    assert "+150% sobre el cierre anterior" in result["message"]  # single value, not a range


def test_no_hits_aggregates_to_nothing():
    assert _aggregate_ticker_spikes("X", []) is None
