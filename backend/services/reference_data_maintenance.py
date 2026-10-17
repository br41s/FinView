"""Reference-data refreshes that must finish inside a billed HTTP request."""

import logging

from backend.database import SessionLocal

logger = logging.getLogger(__name__)


def run_reference_data_maintenance() -> None:
    """Refresh best-effort datasets without relying on post-response threads."""
    try:
        from backend.services.exchange_rates import sync_rates

        sync_rates()
    except Exception as exc:  # independent best-effort source
        logger.warning("[ecb-sync] skipped: %s", exc.__class__.__name__)

    try:
        from backend.services.fred_rates import sync_rates as sync_fred

        sync_fred()
    except Exception as exc:  # independent best-effort source
        logger.warning("[fred-sync] skipped: %s", exc.__class__.__name__)

    try:
        from backend.services.macro_context import sync_macro

        sync_macro()
    except Exception as exc:  # independent best-effort source
        logger.warning("[macro-sync] skipped: %s", exc.__class__.__name__)

    try:
        from backend.services.cnmv_catalog import catalog_is_stale, refresh_iic_catalog

        with SessionLocal() as db:
            stale = catalog_is_stale(db)
        if stale:
            refresh_iic_catalog()
    except Exception as exc:  # independent best-effort source
        logger.warning("[cnmv-catalog] skipped: %s", exc.__class__.__name__)

    try:
        from backend.services.portfolio_service import get_open_positions
        from backend.services.segments.refresh import CRON_SECONDS, refresh

        with SessionLocal() as db:
            positions = get_open_positions(db, None, skip_prices=True)
            refresh(db, {p.isin: (p.ticker, p.name) for p in positions}, CRON_SECONDS)
    except Exception as exc:  # independent best-effort source
        logger.warning("[segments] skipped: %s", exc.__class__.__name__)

    try:
        from backend.services.portfolio_service import get_open_positions
        from backend.services.segments import ai_mentions

        with SessionLocal() as db:
            positions = get_open_positions(db, None, skip_prices=True)
            holdings = {p.isin: (p.ticker, p.name) for p in positions}
            ai_mentions.refresh(db, holdings, ai_mentions.CRON_SECONDS)
    except Exception as exc:  # independent best-effort source
        logger.warning("[ai-mentions] skipped: %s", exc.__class__.__name__)
