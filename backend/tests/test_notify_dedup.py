"""Notification gating: HIGH only, deduplicated across cycles.

The options cycle re-emits the same alerts every 15 minutes for as long as they
stay true. Before this, notify_alerts pushed the full set on every cycle — the
email became ~64 messages a day of ~100 rows each. Two rules fix it: only HIGH
severity notifies (MEDIUM/LOW live in the Monitor tab), and an alert already
pushed within the TTL window is not pushed again.

The dedup lives in the DB: prod scales to zero between cron ticks, so every cycle
runs on a fresh instance and an in-memory cache never remembered anything.
"""

from datetime import datetime, timedelta, timezone
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


def filter_new_alerts(db, alerts, user_id=USER):
    out = ns.filter_new_alerts(db, user_id, alerts)
    db.commit()
    return out


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


def test_the_window_expires(db):
    a = alert()
    filter_new_alerts(db, [a])
    # Age the stored timestamp past the TTL: the alert is fresh again.
    row = db.query(OptionsAlertNotification).one()
    row.notified_at -= ns._NOTIFY_TTL + timedelta(seconds=1)
    db.commit()
    assert filter_new_alerts(db, [a]) == [a]
    assert db.query(OptionsAlertNotification).count() == 1  # updated, not duplicated


def test_dedup_survives_a_new_instance(engine):
    """Each cron tick runs on a cold instance: only what the DB holds carries over."""
    a = alert()
    first = sessionmaker(bind=engine)()
    assert filter_new_alerts(first, [a]) == [a]
    first.close()
    second = sessionmaker(bind=engine)()
    assert filter_new_alerts(second, [a]) == []
    second.close()


def test_dedup_is_per_user(db):
    a = alert()
    assert filter_new_alerts(db, [a], user_id=1) == [a]
    assert filter_new_alerts(db, [a], user_id=2) == [a]


def test_a_stored_naive_timestamp_compares_against_now(db):
    """Postgres/SQLite hand back naive datetimes; comparing must not raise."""
    db.add(OptionsAlertNotification(
        user_id=USER,
        alert_key=ns._alert_key(alert()),
        notified_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1),
    ))
    db.commit()
    assert filter_new_alerts(db, [alert()]) == []


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
        ns.notify_alerts(db, USER, [alert(severity="MEDIUM"), alert(severity="LOW", type="LOW_PUT_CALL_RATIO")])
        ntfy.assert_not_called()
        tg.assert_not_called()
        mail.assert_not_called()


def test_a_fresh_high_hits_all_three_channels(db):
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy as ntfy, p_tg as tg, p_mail as mail:
        ns.notify_alerts(db, USER, [alert(severity="HIGH")])
        ntfy.assert_called_once()
        tg.assert_called_once()
        mail.assert_called_once()


def test_the_same_high_next_cycle_sends_nothing(db):
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy as ntfy, p_tg, p_mail as mail:
        ns.notify_alerts(db, USER, [alert(severity="HIGH")])
        ns.notify_alerts(db, USER, [alert(severity="HIGH")])
        assert ntfy.call_count == 1
        assert mail.call_count == 1


def test_only_the_high_rows_reach_the_email_body(db):
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy, p_tg, p_mail as mail:
        ns.notify_alerts(db, USER, [alert(severity="HIGH", ticker="AAA"), alert(severity="MEDIUM", ticker="BBB")])
        html = mail.call_args.args[1]
        assert "AAA" in html
        assert "BBB" not in html


def test_a_new_high_alongside_an_already_sent_one_notifies_only_the_new(db):
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy, p_tg, p_mail as mail:
        ns.notify_alerts(db, USER, [alert(ticker="AAA", severity="HIGH")])
        ns.notify_alerts(db, USER, [alert(ticker="AAA", severity="HIGH"), alert(ticker="BBB", severity="HIGH")])
        html = mail.call_args.args[1]
        assert "BBB" in html
        assert "AAA" not in html
        assert mail.call_count == 2


def test_spikes_are_labelled_distinctly_on_telegram(db):
    p_ntfy, p_tg, p_mail = _channels()
    with p_ntfy, p_tg as tg, p_mail:
        ns.notify_alerts(db, USER, [alert(type="PREMIUM_SPIKE", severity="HIGH", _strike=100.0, _option_type="call")])
        assert "spike" in tg.call_args.args[0].lower()
