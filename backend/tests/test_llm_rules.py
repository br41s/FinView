"""Every prompt whose output a user reads carries the not-advice rule.

FinView shows data and does not advise. The rule existed in one of five prompts:
the per-ticker report asked the model for position sizing, and the options chat —
which is handed the user's own positions — had no rule at all. A notice in the
UI does not undo a model that writes "compra X", so the constraint has to be in
the prompt, and a new prompt must not be able to ship without it.
"""

import inspect

import pytest

from backend.api import options as options_api
from backend.services import options_agent, zone_scorer
from backend.services.geo import analyst
from backend.services.llm_rules import NOT_ADVICE_RULE_EN, NOT_ADVICE_RULE_ES


def test_the_cycle_report_prompt_carries_the_rule():
    assert NOT_ADVICE_RULE_ES in options_agent._CLAUDE_SYSTEM


def test_the_per_ticker_report_prompt_carries_the_rule():
    assert NOT_ADVICE_RULE_ES in options_agent._CLAUDE_TICKER_SYSTEM


def test_the_zone_scorer_prompt_carries_the_rule():
    assert NOT_ADVICE_RULE_ES in zone_scorer._SYSTEM


@pytest.mark.parametrize(
    "builder, rule",
    [
        # Built inside the function from request data, so the source is the
        # stable thing to assert on.
        (options_api.ask_agent, "NOT_ADVICE_RULE_ES"),
        (analyst._llm_analyze, "NOT_ADVICE_RULE_EN"),
        (analyst._llm_generate, "NOT_ADVICE_RULE_EN"),
    ],
)
def test_prompts_built_per_request_include_the_rule(builder, rule):
    assert rule in inspect.getsource(builder)


@pytest.mark.parametrize("rule", [NOT_ADVICE_RULE_ES, NOT_ADVICE_RULE_EN])
def test_the_rule_forbids_the_three_things_that_make_advice(rule):
    """Buy/sell calls, sizing, and telling the reader what to do."""
    text = rule.lower()
    assert any(word in text for word in ("comprar", "buy"))
    assert any(word in text for word in ("vender", "sell"))
    assert any(word in text for word in ("tamaño", "size"))


@pytest.mark.parametrize(
    "phrase",
    [
        "Top Picks",  # a selection to invest in, by name
        "oportunidades accionables",
        "tamaño según volatilidad",  # asked the model for position sizing
        "Tamaño de posición sugerido",
    ],
)
def test_report_templates_do_not_ask_for_recommendations(phrase):
    templates = (
        options_agent._CLAUDE_SYSTEM
        + options_agent._CLAUDE_USER_TEMPLATE
        + options_agent._CLAUDE_TICKER_SYSTEM
        + options_agent._CLAUDE_TICKER_TEMPLATE
    )
    assert phrase not in templates


def test_report_headings_keep_the_format_the_frontend_splits_on():
    """AnalysisTab and OpcionesTab split on `## N.` — a rename must keep it."""
    for n in range(1, 8):
        assert f"## {n}. " in options_agent._CLAUDE_USER_TEMPLATE
    for n in range(1, 6):
        assert f"## {n}. " in options_agent._CLAUDE_TICKER_TEMPLATE
