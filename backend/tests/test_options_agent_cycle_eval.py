"""The options cycle must not evaluate backtests any more.

Each cycle used to fetch ~36 yfinance price histories (~10 s) to re-evaluate
signals the 22:15 UTC zonas-clave cron already fills once per market day.
"""

import inspect

from backend.services import options_agent


def test_run_cycle_no_longer_evaluates_backtests():
    src = inspect.getsource(options_agent.run_cycle)
    assert "evaluate_pending" not in src
    assert not hasattr(options_agent, "evaluate_pending")
