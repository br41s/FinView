"""Cloud Run request billing must not rely on work after HTTP responses."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import backend.api.geo as geo_api
import backend.api.portfolio as portfolio_api
import backend.api.zonas_clave as zonas_api
import backend.app as app_module
from backend.config import settings


def _user(user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=user_id)


def test_geo_cycle_runs_inline(monkeypatch):
    monkeypatch.setattr(settings, "request_scoped_runtime", True)
    with patch(
        "backend.services.geo.orchestrator.run_cycle_for_user",
        return_value=SimpleNamespace(events=4, new_signals=2, notified=1),
    ) as run_cycle:
        result = geo_api.trigger_run(_user(11))

    assert result.status == "completed"
    assert (result.events, result.new_signals, result.notified) == (4, 2, 1)
    run_cycle.assert_called_once_with(11)


def test_geo_cycle_reports_inline_failure(monkeypatch):
    monkeypatch.setattr(settings, "request_scoped_runtime", True)
    with (
        patch(
            "backend.services.geo.orchestrator.run_cycle_for_user",
            return_value=None,
        ),
        pytest.raises(HTTPException) as exc,
    ):
        geo_api.trigger_run(_user(11))

    assert exc.value.status_code == 500


def test_zonas_cycle_runs_inline(monkeypatch):
    monkeypatch.setattr(settings, "request_scoped_runtime", True)
    with patch(
        "backend.services.zonas_clave_analyzer.run_analysis_for_user",
        return_value={"analyzed": 2},
    ) as run_analysis:
        result = zonas_api.trigger_all(_user(12))

    assert result == {"status": "completed", "analyzed": 2}
    run_analysis.assert_called_once_with(12)


def test_daily_zonas_cron_runs_reference_maintenance_once(monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "right")
    request = SimpleNamespace(headers={"x-cron-key": "right"})
    db = MagicMock()
    db.query.return_value.all.return_value = []

    with patch(
        "backend.services.reference_data_maintenance.run_reference_data_maintenance"
    ) as maintain:
        result = zonas_api.cron_run(request, db)

    maintain.assert_called_once_with()
    assert result["users"] == 0


def test_price_warmup_runs_inline(monkeypatch):
    monkeypatch.setattr(settings, "request_scoped_runtime", True)

    def finish(user_id: int) -> None:
        portfolio_api._warming.discard(user_id)

    with patch.object(
        portfolio_api, "_warm_prices", side_effect=finish
    ) as warm:
        result = portfolio_api.warm_prices(_user(13))

    assert result == {"status": "warmed"}
    warm.assert_called_once_with(13)
    assert 13 not in portfolio_api._warming


@pytest.mark.parametrize(
    "start_scheduler",
    [geo_api.start_scheduler, zonas_api.start_scheduler],
)
def test_in_process_schedulers_are_rejected(monkeypatch, start_scheduler):
    monkeypatch.setattr(settings, "request_scoped_runtime", True)

    with pytest.raises(HTTPException) as exc:
        start_scheduler(_user())

    assert exc.value.status_code == 409


def test_readiness_confirms_request_scoped_startup_without_querying_database(
    monkeypatch,
):
    monkeypatch.setattr(settings, "request_scoped_runtime", True)
    with patch.object(app_module.engine, "connect") as connect:
        result = app_module.readiness()

    assert result == {
        "status": "ready",
        "database": "startup-ok",
        "environment": settings.env.lower(),
        "runtime": "request-scoped",
    }
    connect.assert_not_called()


def test_readiness_rejects_non_request_scoped_production(monkeypatch):
    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "request_scoped_runtime", False)

    with pytest.raises(HTTPException) as exc:
        app_module.readiness()

    assert exc.value.status_code == 503
