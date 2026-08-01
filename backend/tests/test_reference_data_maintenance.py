"""Request-scoped reference maintenance is isolated and secret-safe."""

from unittest.mock import patch

from backend.services.reference_data_maintenance import (
    run_reference_data_maintenance,
)


def test_one_source_failure_does_not_skip_the_others(caplog):
    with (
        patch(
            "backend.services.exchange_rates.sync_rates",
            side_effect=RuntimeError("api_key=must-not-reach-logs"),
        ) as ecb,
        patch("backend.services.fred_rates.sync_rates") as fred,
        patch("backend.services.macro_context.sync_macro") as macro,
        patch("backend.services.cnmv_catalog.catalog_is_stale", return_value=False),
        patch("backend.services.reference_data_maintenance.SessionLocal"),
    ):
        run_reference_data_maintenance()

    ecb.assert_called_once_with()
    fred.assert_called_once_with()
    macro.assert_called_once_with()
    assert "must-not-reach-logs" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_fred_failure_does_not_skip_macro(caplog):
    with (
        patch("backend.services.exchange_rates.sync_rates"),
        patch(
            "backend.services.fred_rates.sync_rates",
            side_effect=RuntimeError("sensitive-url"),
        ),
        patch("backend.services.macro_context.sync_macro") as macro,
        patch("backend.services.cnmv_catalog.catalog_is_stale", return_value=False),
        patch("backend.services.reference_data_maintenance.SessionLocal"),
    ):
        run_reference_data_maintenance()

    macro.assert_called_once_with()
    assert "sensitive-url" not in caplog.text
