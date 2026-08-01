"""Reference-data refreshes that must finish inside a billed HTTP request."""

import logging

from backend.database import SessionLocal

logger = logging.getLogger(__name__)


def run_reference_data_maintenance() -> None:
    """Refresh best-effort datasets without relying on post-response threads."""
    try:
        from backend.services.exchange_rates import sync_rates

        sync_rates()
    except Exception as exc:  # noqa: BLE001 - independent best-effort source
        logger.warning("[ecb-sync] skipped: %s", exc.__class__.__name__)

    try:
        from backend.services.fred_rates import sync_rates as sync_fred

        sync_fred()
    except Exception as exc:  # noqa: BLE001 - independent best-effort source
        logger.warning("[fred-sync] skipped: %s", exc.__class__.__name__)

    try:
        from backend.services.macro_context import sync_macro

        sync_macro()
    except Exception as exc:  # noqa: BLE001 - independent best-effort source
        logger.warning("[macro-sync] skipped: %s", exc.__class__.__name__)

    try:
        from backend.services.cnmv_catalog import catalog_is_stale, refresh_iic_catalog

        with SessionLocal() as db:
            stale = catalog_is_stale(db)
        if stale:
            refresh_iic_catalog()
    except Exception as exc:  # noqa: BLE001 - independent best-effort source
        logger.warning("[cnmv-catalog] skipped: %s", exc.__class__.__name__)
