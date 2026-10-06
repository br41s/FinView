"""Notification gating: HIGH only, one notification per alert episode.

The options cycle re-emits the same alerts every 15 minutes for as long as they
stay true. Before this, notify_alerts pushed the full set on every cycle — the
email became ~64 messages a day of ~100 rows each. Two rules fix it: only HIGH
severity notifies (MEDIUM/LOW live in the Monitor tab), and an alert already
pushed is not pushed again until a cycle clears it and a later one brings it back.

The dedup lives in the DB: prod scales to zero between cron ticks, so every cycle
runs on a fresh instance and an in-memory cache never remembered anything.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, OptionsAlertNotification
from backend.services import notification_service as ns

USER = 1


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def db(engine):
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _tickers(alerts):
    return {a["ticker"] for a in alerts}


def filter_new_alerts(db, alerts, user_id=USER, analyzed=None):
    """One cycle. By default it analyzed exactly the tickers its alerts are on."""
    fresh, _ = ns.filter_new_alerts(
        db, user_id, alerts, _tickers(alerts) if analyzed is None else analyzed
    )
    db.commit()
    return fresh


def notify(db, alerts, analyzed=None):
    ns.notify_alerts(db, USER, alerts, _tickers(alerts) if analyzed is None else analyzed)


def alert(ticker="TEF.MC", type="HIGH_PUT_CALL_RATIO", severity="HIGH", message="msg", **extra):
    return {"ticker": ticker, "type": type, "severity": severity, "message": message, **extra}


# ── filter_new_alerts ────────────────────────────────────────────────


def test_a_repeated_alert_is_only_fresh_once(db):
    a = alert()
    assert filter_new_alerts(db, [a]) == [a]
    assert filter_new_alerts(db, [a]) == []  # same alert next cycle → suppressed


def test_dedup_ignores_the_message_numbers(db):
    """The message carries drifting numbers; identity is ticker+type."""
    filter_new_alerts(db, [alert(message="P/C 1.51")])
    assert filter_new_alerts(db, [alert(message="P/C 1.62")]) == []


def test_different_types_on_one_ticker_are_distinct(db):
    out = filter_new_alerts(db, [alert(type="HIGH_IV"), alert(type="HIGH_PUT_CALL_RATIO")])
    assert len(out) == 2


def test_spikes_dedup_per_contract_not_per_ticker(db):
    k1 = alert(type="PREMIUM_SPIKE", _strike=2400.0, _option_type="call")
    k2 = alert(type="PREMIUM_SPIKE", _strike=2600.0, _option_type="call")
    out = filter_new_alerts(db, [k1, k2])
    assert len(out) == 2  # two contracts, two signals
    assert filter_new_alerts(db, [k1]) == []  # same contract again → suppressed


def test_the_same_alert_twice_in_one_batch_is_sent_once(db):
    assert filter_new_alerts(db, [alert(), alert()]) == [alert()]



def test_dedup_survives_a_new_instance(engine):
    """Each cron tick runs on a cold instance: only what the DB holds carries over."""
    a = alert()
    first = sessionmaker(bind=engine)()
    assert filter_new_alerts(first, [a]) == [a]
    first.close()
    second = sessionmaker(bind=engine)()
    assert filter_new_alerts(second, [a]) == []
    second.close()


# ── episodes ─────────────────────────────────────────────────────────


def test_an_alert_that_stays_true_for_days_is_sent_once(db):
    a = alert()
    assert filter_new_alerts(db, [a]) == [a]
    for _ in range(100):  # 50 hours of 30-min cycles
        assert filter_new_alerts(db, [a]) == []


def test_an_alert_that_clears_and_comes_back_is_sent_again(db):
    a = alert()
    filter_new_alerts(db, [a])
    filter_new_alerts(db, [], analyzed={"TEF.MC"})  # analyzed, alert gone: cleared
    assert filter_new_alerts(db, [a]) == [a]


def test_a_cycle_without_data_for_the_ticker_does_not_clear_it(db):
    """A failed fetch says nothing about the alert; it must not reopen the episode."""
    a = alert()
    filter_new_alerts(db, [a])
    filter_new_alerts(db, [], analyzed=set())  # TEF.MC fetched nothing
    assert filter_new_alerts(db, [a]) == []


def test_another_tickers_cycle_does_not_clear_it(db):
    a = alert()
    filter_new_alerts(db, [a])
    filter_new_alerts(db, [alert(ticker="SAN.MC")])  # TEF.MC not analyzed
    assert filter_new_alerts(db, [a]) == []


def test_one_type_clearing_leaves_the_others_open(db):
    pc, spike = alert(), alert(type="PREMIUM_SPIKE")
    filter_new_alerts(db, [pc, spike])
    filter_new_alerts(db, [spike])  # P/C cleared, spike still true
    assert filter_new_alerts(db, [pc, spike]) == [pc]


def test_the_overnight_gap_does_not_end_an_episode(db):
    """Clearing is by cycle, not by clock: 22:00 → 07:00 is still one episode."""
    a = alert()
    filter_new_alerts(db, [a])
    row = db.query(OptionsAlertNotification).one()
    row.notified_at -= timedelta(days=3)  # a long weekend
    db.commit()
    assert filter_new_alerts(db, [a]) == []


def test_clearing_is_reported(db):
    filter_new_alerts(db, [alert()])
    _, cleared = ns.filter_new_alerts(db, USER, [], {"TEF.MC"})
    assert cleared == 1


def test_dedup_is_per_user(db):
    a = alert()
    assert filter_new_alerts(db, [a], user_id=1) == [a]
    assert filter_new_alerts(db, [a], user_id=2) == [a]



# ── notify_alerts gating ─────────────────────────────────────────────


def _channels():
    return (
        patch.object(ns, "send_ntfy", return_value=True),
        patch.object(ns, "send_telegram", return_value=True),
        patch.object(ns, "send_email", return_value=True),
    )


def test_medium_and_low_never_notify(db):
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy as ntfy, p_tg as tg, p_mail as mail:
        notify(db, [alert(severity="MEDIUM"), alert(severity="LOW", type="LOW_PUT_CALL_RATIO")])
        ntfy.assert_not_called()
        tg.assert_not_called()
        mail.assert_not_called()


def test_a_fresh_high_hits_all_three_channels(db):
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy as ntfy, p_tg as tg, p_mail as mail:
        notify(db, [alert(severity="HIGH")])
        ntfy.assert_called_once()
        tg.assert_called_once()
        mail.assert_called_once()


def test_the_same_high_next_cycle_sends_nothing(db):
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy as ntfy, p_tg, p_mail as mail:
        notify(db, [alert(severity="HIGH")])
        notify(db, [alert(severity="HIGH")])
        assert ntfy.call_count == 1
        assert mail.call_count == 1


def test_only_the_high_rows_reach_the_email_body(db):
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy, p_tg, p_mail as mail:
        notify(db, [alert(severity="HIGH", ticker="AAA"), alert(severity="MEDIUM", ticker="BBB")])
        html = mail.call_args.args[1]
        assert "AAA" in html
        assert "BBB" not in html


def test_a_new_high_alongside_an_already_sent_one_notifies_only_the_new(db):
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy, p_tg, p_mail as mail:
        notify(db, [alert(ticker="AAA", severity="HIGH")])
        notify(db, [alert(ticker="AAA", severity="HIGH"), alert(ticker="BBB", severity="HIGH")])
        html = mail.call_args.args[1]
        assert "BBB" in html
        assert "AAA" not in html
        assert mail.call_count == 2


def test_spikes_are_labelled_distinctly_on_telegram(db):
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy, p_tg as tg, p_mail:
        notify(db, [alert(type="PREMIUM_SPIKE", severity="HIGH", _strike=100.0, _option_type="call")])
        assert "⚡" in tg.call_args.args[0]


# ── Telegram Markdown ────────────────────────────────────────────────


def _balanced_markdown(text: str) -> bool:
    """Legacy Markdown: every unescaped * _ ` must close, or Telegram 400s."""
    unescaped = text
    for ch in "*_`[":
        unescaped = unescaped.replace(f"\\{ch}", "")
    return all(unescaped.count(ch) % 2 == 0 for ch in "*_`")


def test_a_put_call_alert_is_valid_telegram_markdown(db):
    """HIGH_PUT_CALL_RATIO's underscores opened an italic that never closed."""
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy, p_tg as tg, p_mail:
        notify(db, [
            alert(ticker="TEF.MC", message="P/C ratio alto: 1.62 — sentimiento bajista"),
            alert(ticker="DGE.L", type="PREMIUM_SPIKE", message="3 contratos con spike (3 puts), +160%"),
        ])
        text = tg.call_args.args[0]
        assert "HIGH_PUT_CALL_RATIO" not in text  # the message names the alert already
        assert _balanced_markdown(text)


def test_markdown_specials_in_a_message_are_escaped():
    line = ns._telegram_line(alert(ticker="X_Y", message="a*b_c`d[e"))
    assert _balanced_markdown(line)
    assert "a\\*b\\_c\\`d\\[e" in line


# ── observability ────────────────────────────────────────────────────


def test_each_cycle_logs_what_it_sent_and_held_back(db, caplog):
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy, p_tg, p_mail, caplog.at_level("INFO", logger=ns.logger.name):
        notify(db, [alert(ticker="AAA")])
        notify(db, [alert(ticker="AAA"), alert(ticker="BBB")])
        notify(db, [alert(ticker="AAA", severity="MEDIUM")])
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("options notify")]
    assert lines == [
        "options notify: user=1 high=1 sent=1 suppressed=0 cleared=0 ['AAA|HIGH_PUT_CALL_RATIO']",
        "options notify: user=1 high=2 sent=1 suppressed=1 cleared=0 ['BBB|HIGH_PUT_CALL_RATIO']",
        "options notify: user=1 high=0 sent=0 suppressed=0 cleared=1 []",
    ]
