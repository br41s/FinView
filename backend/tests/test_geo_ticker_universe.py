"""Freeze the geo rule ticker universe (offline).

Four symbols in `FAST_RULES` never priced on Yahoo (audit 2026-09-20): `NI=F` (404),
`LBS=F` (delisted random-length lumber), `X` (no data) and `SSNLF` (OTC grey market).
An unresolvable leg gets `price_at_signal=None` and silently leaves the auditor basket,
so a rule can sit at 0 % accuracy purely because half its basket never priced
(`fire-canada-lumber`: 0 % over 102 signals).

This test is deliberately offline — it does not ask Yahoo anything. It only makes a new
symbol a conscious decision: adding one to a rule fails here until the author also adds
it below, which is the moment to check that it actually prices.
"""

from backend.services.geo.rules import FAST_RULES

# Every distinct symbol referenced by FAST_RULES, sorted. Verified to price on Yahoo
# when added. Update deliberately — see the failure message below.
EXPECTED_SYMBOLS: frozenset[str] = frozenset(
    {
        "005930.KS", "AAL", "ALB", "ALL", "BDRY", "BHP", "CC=F", "CCJ", "CCL", "COPX",
        "CVX", "DAC", "DAL", "DBA", "EWG", "EWJ", "EWY", "EWZ", "FCX", "FXI", "GDX",
        "GLD", "HD", "HIG", "HSY", "INDA", "INTC", "ITA", "JETS", "KC=F", "LBR=F",
        "LIT", "LMT", "LOW", "MDLZ", "NOC", "PCG", "RCL", "REMX", "RIO", "RTX", "SCCO",
        "SOXX", "SOYB", "SQM", "TM", "TRV", "TSM", "TUR", "UAL", "UNG", "URA", "USO",
        "VALE", "WEAT", "WY", "XLE", "XOM", "XRT", "ZC=F", "ZIM",
    }
)

# Symbols confirmed dead on Yahoo. They must never come back.
DEAD_SYMBOLS: frozenset[str] = frozenset({"NI=F", "LBS=F", "X", "SSNLF"})


def _universe() -> frozenset[str]:
    return frozenset(t.symbol for rule in FAST_RULES for t in rule.tickers)


def test_ticker_universe_is_frozen():
    actual = _universe()
    added = sorted(actual - EXPECTED_SYMBOLS)
    removed = sorted(EXPECTED_SYMBOLS - actual)
    assert not added and not removed, (
        "The geo ticker universe changed.\n"
        f"  new symbols in FAST_RULES: {added}\n"
        f"  symbols no longer used:    {removed}\n"
        "This is not a failure to route around: before editing EXPECTED_SYMBOLS in "
        "backend/tests/test_geo_ticker_universe.py, confirm each new symbol actually "
        "prices (e.g. yf.download(sym, period='5d', interval='1d') returns rows). An "
        "unresolvable symbol yields price_at_signal=None and drops out of the auditor "
        "basket silently, dragging the rule's measured accuracy toward zero."
    )


def test_no_dead_symbols_in_rules():
    present = sorted(_universe() & DEAD_SYMBOLS)
    assert not present, (
        f"Symbols that do not price on Yahoo are back in FAST_RULES: {present}. "
        "NI=F is a 404, LBS=F is the delisted random-length lumber contract (successor: "
        "LBR=F), X returns no data and SSNLF is OTC grey-market Samsung (use 005930.KS)."
    )


def test_every_rule_has_at_least_one_ticker():
    empty = sorted(rule.id for rule in FAST_RULES if not rule.tickers)
    assert not empty, f"Rules with an empty basket can never produce a signal: {empty}"
