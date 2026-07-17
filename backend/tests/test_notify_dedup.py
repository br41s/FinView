"""Notification gating: HIGH only, deduplicated across cycles.

The options cycle re-emits the same alerts every 15 minutes for as long as they
stay true. Before this, notify_alerts pushed the full set on every cycle — the
email became ~64 messages a day of ~100 rows each. Two rules fix it: only HIGH
severity notifies (MEDIUM/LOW live in the Monitor tab), and an alert already
pushed within the TTL window is not pushed again.
"""

from unittest.mock import patch

import pytest

from backend.services import notification_service as ns
from backend.services.notification_service import filter_new_alerts, notify_alerts


@pytest.fixture(autouse=True)
def _clear_dedup():
    ns._NOTIFIED.clear()
    yield
    ns._NOTIFIED.clear()


def alert(ticker="TEF.MC", type="HIGH_PUT_CALL_RATIO", severity="HIGH", message="msg", **extra):
    return {"ticker": ticker, "type": type, "severity": severity, "message": message, **extra}


# ── filter_new_alerts ────────────────────────────────────────────────


def test_a_repeated_alert_is_only_fresh_once():
    a = alert()
    assert filter_new_alerts([a]) == [a]
    assert filter_new_alerts([a]) == []  # same alert next cycle → suppressed


def test_dedup_ignores_the_message_numbers():
    """The message carries drifting numbers; identity is ticker+type."""
    filter_new_alerts([alert(message="P/C 1.51")])
    assert filter_new_alerts([alert(message="P/C 1.62")]) == []


def test_different_types_on_one_ticker_are_distinct():
    out = filter_new_alerts([alert(type="HIGH_IV"), alert(type="HIGH_PUT_CALL_RATIO")])
    assert len(out) == 2


def test_spikes_dedup_per_contract_not_per_ticker():
    k1 = alert(type="PREMIUM_SPIKE", _strike=2400.0, _option_type="call")
    k2 = alert(type="PREMIUM_SPIKE", _strike=2600.0, _option_type="call")
    out = filter_new_alerts([k1, k2])
    assert len(out) == 2  # two contracts, two signals
    assert filter_new_alerts([k1]) == []  # same contract again → suppressed


def test_the_window_expires(monkeypatch):
    a = alert()
    filter_new_alerts([a])
    # Jump past the TTL: the alert is fresh again.
    later = ns.time.time() + ns._NOTIFY_TTL + 1
    monkeypatch.setattr(ns.time, "time", lambda: later)
    assert filter_new_alerts([a]) == [a]


# ── notify_alerts gating ─────────────────────────────────────────────


def _channels():
    return (
        patch.object(ns, "send_ntfy", return_value=True),
        patch.object(ns, "send_telegram", return_value=True),
        patch.object(ns, "send_email", return_value=True),
    )


def test_medium_and_low_never_notify():
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy as ntfy, p_tg as tg, p_mail as mail:
        notify_alerts([alert(severity="MEDIUM"), alert(severity="LOW", type="LOW_PUT_CALL_RATIO")])
        ntfy.assert_not_called()
        tg.assert_not_called()
        mail.assert_not_called()


def test_a_fresh_high_hits_all_three_channels():
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy as ntfy, p_tg as tg, p_mail as mail:
        notify_alerts([alert(severity="HIGH")])
        ntfy.assert_called_once()
        tg.assert_called_once()
        mail.assert_called_once()


def test_the_same_high_next_cycle_sends_nothing():
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy as ntfy, p_tg, p_mail as mail:
        notify_alerts([alert(severity="HIGH")])
        notify_alerts([alert(severity="HIGH")])
        assert ntfy.call_count == 1
        assert mail.call_count == 1


def test_only_the_high_rows_reach_the_email_body():
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy, p_tg, p_mail as mail:
        notify_alerts([alert(severity="HIGH", ticker="AAA"), alert(severity="MEDIUM", ticker="BBB")])
        html = mail.call_args.args[1]
        assert "AAA" in html
        assert "BBB" not in html


def test_a_new_high_alongside_an_already_sent_one_notifies_only_the_new():
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy, p_tg, p_mail as mail:
        notify_alerts([alert(ticker="AAA", severity="HIGH")])
        notify_alerts([alert(ticker="AAA", severity="HIGH"), alert(ticker="BBB", severity="HIGH")])
        html = mail.call_args.args[1]
        assert "BBB" in html
        assert "AAA" not in html
        assert mail.call_count == 2


def test_spikes_are_labelled_distinctly_on_telegram():
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy, p_tg as tg, p_mail:
        notify_alerts([alert(type="PREMIUM_SPIKE", severity="HIGH", _strike=100.0, _option_type="call")])
        assert "spike" in tg.call_args.args[0].lower()
