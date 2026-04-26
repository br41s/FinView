"""APScheduler wrapper for periodic Zonas Clave recalculation — runs every 24 hours."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()
_active_jobs: dict[int, str] = {}  # user_id -> job_id


def start_user_schedule(user_id: int) -> None:
    """Start a 24-hour recalculation job for a user."""
    from backend.services.zonas_clave_analyzer import run_analysis_for_user

    job_id = f"zonas_clave_{user_id}"
    if job_id in _active_jobs.values():
        logger.info("Zonas Clave job already running for user %d", user_id)
        return

    _scheduler.add_job(
        run_analysis_for_user,
        "interval",
        hours=24,
        args=[user_id],
        id=job_id,
        replace_existing=True,
    )
    _active_jobs[user_id] = job_id

    if not _scheduler.running:
        _scheduler.start()

    logger.info("Started Zonas Clave scheduler for user %d (every 24h)", user_id)


def stop_user_schedule(user_id: int) -> None:
    """Stop the recalculation job for a user."""
    job_id = _active_jobs.pop(user_id, None)
    if job_id:
        try:
            _scheduler.remove_job(job_id)
        except Exception:
            pass
        logger.info("Stopped Zonas Clave scheduler for user %d", user_id)


def is_running(user_id: int) -> bool:
    return f"zonas_clave_{user_id}" in _active_jobs.values()


def shutdown_scheduler() -> None:
    """Graceful shutdown of all scheduled jobs."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Zonas Clave APScheduler shut down")
